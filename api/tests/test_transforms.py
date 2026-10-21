import pytest

from app.security import CmsError
from app.transforms import transform_data
from conftest import define, entry, gql


def test_ordered_nested_transforms_do_not_mutate_input():
    data = {"items": [{"old": "12"}, {"old": "4"}], "localized": {"en": {"value": "true"}}}
    result = transform_data(
        data,
        [
            {"op": "rename", "path": "items.*.old", "to": "count"},
            {"op": "convert", "path": "items.*.count", "to": "number"},
            {"op": "default", "path": "items.*.flag", "value": False},
            {"op": "convert", "path": "localized.*.value", "to": "boolean"},
            {"op": "drop", "path": "items.*.flag"},
            {"op": "drop", "path": "items", "typeKey": "other"},
        ],
        "article",
    )
    assert result == {"items": [{"count": 12}, {"count": 4}], "localized": {"en": {"value": True}}}
    assert data["items"][0] == {"old": "12"}


@pytest.mark.parametrize(
    "data,steps",
    [
        ({"old": 1, "new": 2}, [{"op": "rename", "path": "old", "to": "new"}]),
        ({"x": "maybe"}, [{"op": "convert", "path": "x", "to": "boolean"}]),
        ({"x": "NaN"}, [{"op": "convert", "path": "x", "to": "number"}]),
        ({"x": True}, [{"op": "convert", "path": "x", "to": "number"}]),
        ({"x": "9007199254740993.0"}, [{"op": "convert", "path": "x", "to": "number"}]),
        ({}, [{"op": "execute", "path": "x"}]),
        ({}, [{"op": [], "path": "x"}]),
        ({}, [{"op": "drop", "path": "x", "code": "arbitrary"}]),
    ],
)
def test_invalid_or_lossy_transforms_fail(data, steps):
    with pytest.raises(CmsError):
        transform_data(data, steps)


def test_existing_schema_migration_accepts_pipeline_steps(client, admin):
    define(client, admin, fields=[{"name": "amount", "type": "text"}])
    created = entry(client, admin, data={"amount": "12"}, status="published")["data"]["saveEntry"]
    result = gql(
        client,
        admin,
        'mutation($migration:JSON!){saveContentType(key:"article",name:"Article",version:1,fields:[{name:"count",type:"number"}],migration:$migration){version}}',
        {
            "migration": {
                "steps": [
                    {"op": "rename", "path": "amount", "to": "count"},
                    {"op": "convert", "path": "count", "to": "number"},
                ]
            }
        },
    )
    assert "errors" not in result, result
    result = gql(client, admin, "query($id:ID!){entry(id:$id){data publishedData}}", {"id": created["id"]})
    assert "errors" not in result, result
    assert result["data"]["entry"]["data"] == {"count": 12}
    assert result["data"]["entry"]["publishedData"] == {"count": 12}
