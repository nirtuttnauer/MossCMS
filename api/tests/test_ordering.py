import base64
import random
from datetime import date

import pytest
from sqlalchemy import event, inspect, select, text

from app.indexing import SORT_PREFIX_BYTES, order_keys
from app.models import EntryFieldIndex
from conftest import define, entry, gql
from test_schema_cache import token


FIELDS = [
    {"name": "title", "type": "text"},
    {"name": "price", "type": "number"},
    {"name": "enabled", "type": "boolean"},
    {"name": "date", "type": "date"},
    {"name": "category", "type": "enum", "options": ["news", "guide"]},
    {"name": "body", "type": "richText"},
    {"name": "secret", "type": "text", "private": True},
    {"name": "translated", "type": "text", "localized": True},
    {"name": "nested", "type": "object", "fields": [{"name": "title", "type": "text"}]},
]


def pages(client, headers, field, direction="ASC", delivery=False, first=2, type_key="article", filters=None):
    query = "query($type:String,$field:String!,$direction:OrderDirection!,$after:String,$first:Int!,$filters:JSON){entries(typeKey:$type,orderBy:{field:$field,direction:$direction},first:$first,after:$after,filters:$filters){nodes{id data} total endCursor hasNextPage}}"
    after, results, totals = None, [], []
    for _ in range(20):
        result = gql(
            client,
            headers,
            query,
            {
                "type": type_key,
                "field": field,
                "direction": direction,
                "after": after,
                "first": first,
                "filters": filters,
            },
            delivery=delivery,
        )
        assert not result.get("errors"), result
        page = result["data"]["entries"]
        results.extend(page["nodes"])
        totals.append(page["total"])
        if not page["hasNextPage"]:
            assert all(total == len(results) for total in totals)
            return results
        assert after != page["endCursor"]
        after = page["endCursor"]
    pytest.fail("Cursor did not terminate")


def test_numeric_keys_preserve_exact_order_and_equal_values():
    values = [
        -1e308,
        -(10**300),
        -(2**53) - 1,
        -(2**53),
        -1.5,
        -1,
        -0.1,
        -5e-324,
        -0.0,
        0,
        5e-324,
        0.1,
        1,
        1.0,
        1.5,
        2**53,
        2**53 + 1,
        10**300,
        1e308,
    ]
    generator = random.Random(20261012)
    values += [generator.uniform(-1e100, 1e100) for _ in range(100)]
    assert sorted(values, key=lambda value: order_keys(value)["sort_key"]) == sorted(values)
    assert order_keys(1)["sort_key"] == order_keys(1.0)["sort_key"]
    assert order_keys(-0.0)["sort_key"] == order_keys(0)["sort_key"]
    assert all(len(order_keys(value)["sort_key"]) <= SORT_PREFIX_BYTES for value in values)


@pytest.mark.parametrize("direction", ["ASC", "DESC"])
@pytest.mark.parametrize(
    "field,values",
    [
        ("price", [10, 2, 9007199254740993, 9007199254740992, -3, None]),
        ("enabled", [True, False, True, None, False]),
        ("date", ["20261201", "2026-01-02", "2026-W10-1", None]),
        ("title", ["שלום", "Z", "a", "😀", None]),
        ("category", ["news", "guide", None, "news"]),
        ("body", ["z", "a", "Prefix\0body", None]),
    ],
)
def test_scalar_ordering_and_null_tail(client, admin, direction, field, values):
    define(client, admin, fields=FIELDS)
    records = []
    for i, value in enumerate(values):
        data = {field: value} if value is not None else {}
        if field != "title":
            data["title"] = f"Entry {i}"
        if not data:
            data = {"body": "Missing title"}
        saved = entry(client, admin, f"row-{i}", data=data, status="published")
        assert not saved.get("errors"), saved
        records.append((saved["data"]["saveEntry"]["id"], value))
    actual = pages(client, token(client, admin), field, direction, True)
    key = (lambda value: date.fromisoformat(value).toordinal()) if field == "date" else (lambda value: value)
    nonnull = sorted(
        [(id, value) for id, value in records if value is not None],
        key=lambda row: (key(row[1]), row[0]),
        reverse=direction == "DESC",
    )
    missing = sorted([(id, value) for id, value in records if value is None], reverse=direction == "DESC")
    assert [row["id"] for row in actual] == [id for id, _ in nonnull + missing]


def test_long_strings_with_shared_prefix_and_null_bytes(client, admin):
    define(client, admin, fields=FIELDS)
    values = ["x" * 50000 + "z", "x" * 50000 + "a", "x" * 50000, "x" * 50000 + "\0", "before"]
    for i, value in enumerate(values):
        saved = entry(client, admin, f"long-{i}", data={"title": f"Entry {i}", "body": value}, status="published")
        assert not saved.get("errors"), saved
    for direction in ("ASC", "DESC"):
        result = pages(client, token(client, admin), "body", direction, True, first=1)
        assert [row["data"]["body"] for row in result] == sorted(values, reverse=direction == "DESC")


def test_draft_changes_do_not_change_live_order_and_filters_still_apply(client, admin):
    define(client, admin, fields=FIELDS)
    first = entry(client, admin, "first", data={"title": "First", "price": 1, "category": "news"}, status="published")[
        "data"
    ]["saveEntry"]
    second = entry(
        client, admin, "second", data={"title": "Second", "price": 2, "category": "guide"}, status="published"
    )["data"]["saveEntry"]
    entry(
        client,
        admin,
        "first",
        data={"title": "First", "price": 9, "category": "news"},
        id=first["id"],
        version=first["version"],
    )
    delivery = token(client, admin)
    assert [row["id"] for row in pages(client, delivery, "price", delivery=True)] == [first["id"], second["id"]]
    assert [row["id"] for row in pages(client, admin, "price")] == [second["id"], first["id"]]
    assert [row["id"] for row in pages(client, delivery, "price", delivery=True, filters={"category": "news"})] == [
        first["id"]
    ]


@pytest.mark.parametrize("field", ["secret", "translated", "nested", "missing", "price; DROP TABLE entries"])
def test_private_and_nonscalar_fields_are_rejected(client, admin, field):
    define(client, admin, fields=FIELDS)
    result = gql(
        client,
        token(client, admin),
        'query($field:String!){entries(typeKey:"article",orderBy:{field:$field}){nodes{id}}}',
        {"field": field},
        delivery=True,
    )
    assert result.get("errors")


def test_cursors_are_bound_to_workspace_snapshot_field_and_direction(client, admin):
    define(client, admin, fields=FIELDS)
    for i in range(3):
        entry(client, admin, f"record-{i}", data={"title": str(i), "price": i}, status="published")
    query = 'query($after:String,$field:String!,$direction:OrderDirection!){entries(typeKey:"article",orderBy:{field:$field,direction:$direction},first:1,after:$after){nodes{id} endCursor}}'
    result = gql(client, admin, query, {"field": "price", "direction": "ASC"})
    cursor = result["data"]["entries"]["endCursor"]
    for field, direction, delivery in (("title", "ASC", False), ("price", "DESC", False), ("price", "ASC", True)):
        result = gql(
            client,
            token(client, admin) if delivery else admin,
            query,
            {"after": cursor, "field": field, "direction": direction},
            delivery=delivery,
        )
        assert result.get("errors")
    other = client.post("/api/projects", headers=admin, json={"name": "Other workspace"}).json()
    other_headers = {**admin, "x-moss-project": other["id"]}
    define(client, other_headers, fields=FIELDS)
    entry(client, other_headers, data={"title": "Other", "price": 1})
    assert gql(client, other_headers, query, {"after": cursor, "field": "price", "direction": "ASC"}).get("errors")
    define(client, admin, key="product", fields=FIELDS)
    other_type_query = query.replace('typeKey:"article"', 'typeKey:"product"')
    assert gql(client, admin, other_type_query, {"after": cursor, "field": "price", "direction": "ASC"}).get("errors")
    for broken in ("invalid", base64.urlsafe_b64encode(b"{}").decode()):
        assert gql(client, admin, query, {"after": broken, "field": "price", "direction": "ASC"}).get("errors")


def test_omitted_totals_skip_count_including_generated_queries_and_fragment_totals_work(app, client, admin):
    define(client, admin)
    entry(client, admin, status="published")
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(app.state.engine, "before_cursor_execute", capture)
    try:
        for query in (
            "{entries(first:1){nodes{id} hasNextPage}}",
            "{allCmsArticle(first:1){id}}",
            "query($show:Boolean!){entries{total @include(if:$show) nodes{id}}}",
        ):
            statements.clear()
            result = gql(client, admin, query, {"show": False})
            assert not result.get("errors"), result
            assert not any("count(" in sql.lower() for sql in statements)
        statements.clear()
        result = gql(client, admin, "{entries{...Totals}} fragment Totals on EntryPage {a:total b:total}")
        assert result["data"]["entries"] == {"a": 1, "b": 1}
        assert sum("count(" in sql.lower() for sql in statements) == 1
    finally:
        event.remove(app.state.engine, "before_cursor_execute", capture)


def test_sort_indexes_backfill_and_have_usable_plans(app, client, admin):
    define(client, admin, fields=FIELDS)
    entry(client, admin, data={"title": "Value", "price": 2, "date": "2026-10-12"})
    with app.state.engine.connect() as connection:
        row = connection.execute(select(EntryFieldIndex).where(EntryFieldIndex.field == "price")).one()
        assert row.sort_key is None and row.sort_prefix == order_keys(2)["sort_key"]
        assert len(row.sort_prefix) <= SORT_PREFIX_BYTES and not row.sort_long
        if connection.dialect.name == "postgresql":
            connection.execute(text("SET LOCAL enable_seqscan = off"))
            prefix = "EXPLAIN "
        else:
            prefix = "EXPLAIN QUERY PLAN "
        if connection.dialect.name == "sqlite":
            probe = (
                select(EntryFieldIndex.entry_id)
                .where(
                    EntryFieldIndex.project_id == admin["x-moss-project"],
                    EntryFieldIndex.type_id == row.type_id,
                    EntryFieldIndex.snapshot == "draft",
                    EntryFieldIndex.field == "body",
                    EntryFieldIndex.sort_long.is_(True),
                )
                .limit(1)
            )
            sql = str(probe.compile(connection, compile_kwargs={"literal_binds": True}))
            assert "ix_entry_fields_long" in str(connection.exec_driver_sql("EXPLAIN QUERY PLAN " + sql).all())
        for column, index in (("sort_prefix", "ix_entry_fields_order"), ("date_key", "ix_entry_fields_date_order")):
            plan = connection.execute(
                text(
                    prefix
                    + f"SELECT entry_id FROM entry_field_indexes WHERE project_id=:project AND type_id=:type AND snapshot='draft' AND field='price' AND {column} IS NOT NULL ORDER BY {column}, entry_id LIMIT 20"
                ),
                {"project": admin["x-moss-project"], "type": row.type_id},
            ).all()
            assert index in str(plan)
    names = {row["name"] for row in inspect(app.state.engine).get_indexes("entry_field_indexes")}
    assert {"ix_entry_fields_order", "ix_entry_fields_date_order", "ix_entry_fields_long"} <= names
