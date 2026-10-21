#!/usr/bin/env python3
"""Deterministic fixtures and HTTP measurements for disposable benchmark databases."""

import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image
from sqlalchemy import MetaData, create_engine, event, inspect, select, text
from sqlalchemy.engine import make_url

PASSWORD = "fixture-only-benchmark-password"
DELIVERY_TOKEN = "fixture-only-benchmark-delivery-token"
WORKSPACE = "benchmark-workspace-0"
INSTANT = datetime(2026, 1, 1)
FIELDS = [
    {"name": "title", "type": "text", "required": True},
    {"name": "body", "type": "richText", "localized": True},
    {"name": "category", "type": "enum", "options": ["news", "guide"]},
    {"name": "related", "type": "reference", "target": "article"},
    {"name": "cover", "type": "asset"},
    {"name": "internalNotes", "type": "text", "private": True},
    {
        "name": "seo",
        "type": "object",
        "fields": [
            {"name": "description", "type": "text"},
            {"name": "internal", "type": "text", "private": True},
        ],
    },
]
LIST_QUERY = 'query($search:String!,$filters:JSON){entries(typeKey:"article",first:20,search:$search,filters:$filters){nodes{id slug data} total endCursor hasNextPage}}'
GENERATED_QUERY = '{allCmsArticle(first:20){id slug title body(locale:"he") cover{id name url} related{id entry{id slug data}} seo{description}}}'
ENTRY_QUERY = "query($id:ID!){entry(id:$id){id slug data version publishedRevision scheduledRevision}}"
SAVE_QUERY = 'mutation($id:ID!,$slug:String!,$data:JSON!,$version:Int!){saveEntry(typeKey:"article",id:$id,slug:$slug,data:$data,version:$version,status:"draft"){id version publishedRevision scheduledRevision}}'


def guarded_url(value):
    url = make_url(value)
    if (
        url.get_backend_name() != "postgresql"
        or url.host not in {"localhost", "127.0.0.1", "db"}
        or not (url.database or "").startswith("moss_benchmark_")
    ):
        raise ValueError("Use an explicit disposable moss_benchmark_* PostgreSQL database on loopback or benchmark db.")
    return url


def workspace(index):
    remainder = index % 10
    return 0 if remainder < 8 else remainder - 7


def fixture_entry(index):
    group = workspace(index)
    state = index % 5
    data = {
        "title": f"Draft article {index:06d}",
        "body": {"en": "Benchmark body. " * 80, "he": "תוכן לדוגמה " * 40},
        "category": "news" if index % 2 == 0 else "guide",
        "related": f"benchmark-entry-{[2, 8, 9][group]}",
        "cover": f"benchmark-asset-{group}",
        "internalNotes": "PRIVATE-BENCHMARK-MARKER",
        "seo": {
            "description": "Public description",
            "internal": "PRIVATE-BENCHMARK-MARKER",
        },
    }
    live = {**data, "title": f"Live article {index:06d}"} if state >= 2 else None
    scheduled = {**data, "title": f"Scheduled article {index:06d}"} if state in {1, 4} else None
    return {
        "id": f"benchmark-entry-{index}",
        "project_id": f"benchmark-workspace-{group}",
        "type_id": f"benchmark-type-{group}",
        "slug": f"article-{index:06d}",
        "title": data["title"],
        "data": data,
        "status": "scheduled" if scheduled else "published" if live else "draft",
        "published_data": live,
        "published_slug": f"article-{index:06d}" if live else None,
        "published_title": live["title"] if live else None,
        "published_at": INSTANT if live else None,
        "published_revision": 3 if live else None,
        "published_schema_version": 1 if live else None,
        "scheduled_data": scheduled,
        "scheduled_slug": f"article-{index:06d}" if scheduled else None,
        "scheduled_title": scheduled["title"] if scheduled else None,
        "scheduled_at": datetime(2035, 1, 1) if scheduled else None,
        "scheduled_revision": 4 if scheduled else None,
        "scheduled_schema_version": 1 if scheduled else None,
        "version": 5,
        "updated_at": INSTANT + timedelta(seconds=index),
    }


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def fingerprint(engine, media, omit_project_locales=False):
    metadata = MetaData()
    metadata.reflect(engine)
    tables = {}
    with engine.connect() as connection:
        for name, table in sorted(metadata.tables.items()):
            if name == "alembic_version":
                continue
            checksum, count = hashlib.sha256(), 0
            for row in (
                connection.execution_options(yield_per=1000)
                .execute(select(table).order_by(*table.primary_key))
                .mappings()
            ):
                values = dict(row)
                if name == "projects" and omit_project_locales:
                    # These columns are added by the upgrade rehearsed by seed().
                    values.pop("locales", None)
                    values.pop("default_locale", None)
                checksum.update(json.dumps(values, sort_keys=True, default=str).encode())
                count += 1
            tables[name] = {"count": count, "sha256": checksum.hexdigest()}
    files = {
        str(p.relative_to(media)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(media.rglob("*"))
        if p.is_file()
    }
    return {"tables": tables, "media": files}


def seed(engine, media, size):
    from app.migrate import migrate
    from app.security import digest, password_hash

    if inspect(engine).get_table_names() or any(media.iterdir()):
        raise ValueError("Seed requires an empty benchmark database and media directory.")
    migrate(engine, "0008")
    metadata = MetaData()
    metadata.reflect(engine)
    image = BytesIO()
    Image.new("RGB", (32, 32), (35, 85, 65)).save(image, format="PNG")
    image_bytes = image.getvalue()
    with engine.begin() as connection:
        for group in range(3):
            project = f"benchmark-workspace-{group}"
            connection.execute(
                metadata.tables["projects"].insert(),
                {"id": project, "name": project, "created_at": INSTANT},
            )
            for kind, fields in [
                ("article", FIELDS),
                ("restricted", [{"name": "secret", "type": "text"}]),
            ]:
                connection.execute(
                    metadata.tables["content_types"].insert(),
                    {
                        "id": f"benchmark-type-{group}" if kind == "article" else f"benchmark-restricted-{group}",
                        "project_id": project,
                        "key": kind,
                        "name": kind,
                        "fields": fields,
                        "version": 1,
                    },
                )
            key = f"benchmark-{group}.png"
            (media / key).write_bytes(image_bytes)
            connection.execute(
                metadata.tables["assets"].insert(),
                {
                    "id": f"benchmark-asset-{group}",
                    "project_id": project,
                    "name": key,
                    "key": key,
                    "storage": "local",
                    "mime": "image/png",
                    "size": len(image_bytes),
                    "width": 32,
                    "height": 32,
                    "created_at": INSTANT,
                },
            )
        hashed = password_hash(PASSWORD)
        for writer in range(3):
            user = f"benchmark-writer-{writer}"
            connection.execute(
                metadata.tables["users"].insert(),
                {
                    "id": user,
                    "name": user,
                    "email": f"writer{writer}@benchmark.invalid",
                    "password_hash": hashed,
                    "created_at": INSTANT,
                },
            )
            connection.execute(
                metadata.tables["memberships"].insert(),
                {
                    "project_id": WORKSPACE,
                    "user_id": user,
                    "role": "editor",
                },
            )
        connection.execute(
            metadata.tables["tokens"].insert(),
            {
                "id": digest(DELIVERY_TOKEN),
                "kind": "delivery",
                "project_id": WORKSPACE,
                "name": "benchmark",
                "scopes": ["article"],
                "expires_at": datetime(2035, 1, 1),
                "email": "",
                "role": "reader",
                "csrf": "",
                "created_at": INSTANT,
            },
        )
        for start in range(0, size, 1000):
            rows = [fixture_entry(i) for i in range(start, min(size, start + 1000))]
            connection.execute(metadata.tables["entries"].insert(), rows)
            revisions = []
            for row in rows:
                for number in (3, 4, 5):
                    revisions.append(
                        {
                            "id": f"{row['id']}-revision-{number}",
                            "project_id": row["project_id"],
                            "entry_id": row["id"],
                            "number": number,
                            "snapshot": {
                                "data": row["scheduled_data"]
                                if number == 4 and row["scheduled_data"]
                                else row["published_data"]
                                if number == 3 and row["published_data"]
                                else row["data"],
                                "slug": row["slug"],
                            },
                            "author": "benchmark",
                            "created_at": INSTANT,
                        }
                    )
            connection.execute(metadata.tables["revisions"].insert(), revisions)
    before = fingerprint(engine, media, omit_project_locales=True)
    started = time.perf_counter()
    migrate(engine)
    seconds = time.perf_counter() - started
    after = fingerprint(engine, media, omit_project_locales=True)
    assert all(after["tables"][key] == value for key, value in before["tables"].items()), (
        "Upgrade changed fixture records"
    )
    assert before["media"] == after["media"]
    with engine.begin() as connection:
        connection.execute(text("UPDATE projects SET locales = '[\"en\",\"he\"]', default_locale = 'en'"))
        connection.execute(text("ANALYZE"))
        schema_revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    return {
        "entries": size,
        "revisions": size * 3,
        "workspaces": 3,
        "workspaceMix": "80% / 10% / 10%",
        "liveEntries": size * 3 // 5,
        "scheduledEntries": size * 2 // 5,
        "assets": 3,
        "upgrade": {
            "from": "0008",
            "to": schema_revision,
            "seconds": seconds,
            "recordsPreserved": True,
        },
        "seed": "index-based-v1",
        "python": platform.python_version(),
    }


def summarize(samples, elapsed):
    values = sorted(samples)

    def percentile(percent):
        return round(values[max(0, math.ceil(len(values) * percent) - 1)], 3) if values else None

    return {
        "requests": len(values),
        "requestsPerSecond": round(len(values) / elapsed, 3),
        "p50Ms": percentile(0.5),
        "p95Ms": percentile(0.95),
        "p99Ms": percentile(0.99),
    }


async def request(client, query, variables=None, headers=None, editorial=False):
    response = await client.post(
        "/graphql" if editorial else "/delivery/graphql",
        json={"query": query, "variables": variables},
        headers=headers,
    )
    response.raise_for_status()
    result = response.json()
    if result.get("errors"):
        raise ValueError(result["errors"][0].get("extensions", {}).get("code", "GRAPHQL_ERROR"))
    if "PRIVATE-BENCHMARK-MARKER" in response.text and not editorial:
        raise ValueError("PRIVATE_FIELD_EXPOSURE")
    return result["data"], response


async def editor(client, writer):
    response = await client.post(
        "/auth/login",
        json={"email": f"writer{writer}@benchmark.invalid", "password": PASSWORD},
    )
    response.raise_for_status()
    me = (await client.get("/auth/me")).json()
    headers = {"X-Moss-Project": WORKSPACE, "X-Moss-CSRF": me["csrf"]}
    entry, _ = await request(client, ENTRY_QUERY, {"id": f"benchmark-entry-{writer * 10 + 4}"}, headers, True)
    return headers, entry["entry"]


async def workload(base_url, seconds, readers, writers):
    samples, errors, status_counts = defaultdict(list), Counter(), Counter()
    delivery = {"Authorization": f"Bearer {DELIVERY_TOKEN}"}
    initial = []
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        for phase in ("first_after_start", "after_warmup"):
            for name, query, variables in (
                ("list", LIST_QUERY, {"search": "", "filters": None}),
                ("generated", GENERATED_QUERY, None),
            ):
                clock = time.perf_counter()
                await request(client, query, variables, delivery)
                initial.append(
                    {
                        "phase": phase,
                        "operation": name,
                        "milliseconds": (time.perf_counter() - clock) * 1000,
                    }
                )
    started = time.perf_counter()
    deadline = started + seconds

    async def reader(index):
        async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
            turn, etag = index, None
            while time.perf_counter() < deadline:
                kind = ["list", "search", "filter", "generated", "etag"][turn % 5]
                query = GENERATED_QUERY if kind == "generated" else LIST_QUERY
                variables = {
                    "search": f"article-{turn % 100:06d}" if kind == "search" else "",
                    "filters": {"category": "news"} if kind == "filter" else None,
                }
                headers = {
                    **delivery,
                    **({"If-None-Match": etag} if kind == "etag" and etag else {}),
                }
                clock = time.perf_counter()
                try:
                    response = await client.post(
                        "/delivery/graphql",
                        json={"query": query, "variables": variables},
                        headers=headers,
                    )
                    status_counts[str(response.status_code)] += 1
                    if response.status_code != 304:
                        response.raise_for_status()
                    if response.status_code != 304:
                        result = response.json()
                        if result.get("errors"):
                            raise ValueError(result["errors"][0].get("extensions", {}).get("code", "GRAPHQL_ERROR"))
                        if "PRIVATE-BENCHMARK-MARKER" in response.text:
                            raise ValueError("PRIVATE_FIELD_EXPOSURE")
                        if kind in {"list", "etag"}:
                            etag = response.headers.get("etag")
                except Exception as error:
                    errors[f"{kind}:{error if isinstance(error, ValueError) else type(error).__name__}"] += 1
                samples[kind].append((time.perf_counter() - clock) * 1000)
                turn += 1

    async def writer(index):
        async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
            headers, saved = await editor(client, index)
            while time.perf_counter() < deadline:
                clock = time.perf_counter()
                try:
                    data = {
                        **saved["data"],
                        "title": f"Writer {index} revision {saved['version']}",
                    }
                    result, _ = await request(
                        client,
                        SAVE_QUERY,
                        {
                            "id": saved["id"],
                            "slug": saved["slug"],
                            "data": data,
                            "version": saved["version"],
                        },
                        headers,
                        True,
                    )
                    assert result["saveEntry"]["publishedRevision"] == saved["publishedRevision"]
                    assert result["saveEntry"]["scheduledRevision"] == saved["scheduledRevision"]
                    saved.update(result["saveEntry"])
                    saved["data"] = data
                except Exception as error:
                    errors[f"save:{error if isinstance(error, ValueError) else type(error).__name__}"] += 1
                    result, _ = await request(client, ENTRY_QUERY, {"id": saved["id"]}, headers, True)
                    saved = result["entry"]
                samples["save"].append((time.perf_counter() - clock) * 1000)
                await asyncio.sleep(1)

    await asyncio.gather(*(reader(i) for i in range(readers)), *(writer(i) for i in range(writers)))
    elapsed = time.perf_counter() - started
    return {
        "durationSeconds": round(elapsed, 3),
        "requestedSeconds": seconds,
        "readers": readers,
        "writers": writers,
        "operations": {k: summarize(v, elapsed) for k, v in samples.items()},
        "errors": dict(errors),
        "httpStatuses": dict(status_counts),
        "initialRequests": initial,
        "cacheNote": "Initial and warmed process requests are separate; database/OS caches are not forcibly evicted. ETag measures conditional responses, not a CDN or server response cache.",
    }


def ordering_plans(engine):
    from sqlalchemy.orm import Session
    from app.content import entry_page

    captured = []
    totals = []
    searches = []
    search_phase = False

    def capture(connection, cursor, statement, parameters, context, executemany):
        if search_phase and statement.startswith(("SELECT entries.", "SELECT count(")):
            searches.append((statement, parameters))
        elif statement.startswith("SELECT entries."):
            captured.append((statement, parameters))
        elif statement.startswith("SELECT count("):
            totals.append((statement, parameters))

    event.listen(engine, "before_cursor_execute", capture)
    try:
        with Session(engine) as session:
            identity = {
                "project_id": WORKSPACE,
                "role": "reader",
                "delivery": True,
                "scopes": ["article"],
            }
            page = entry_page(
                session,
                identity,
                "article",
                order_by={"field": "title", "direction": "asc"},
                include_total=False,
            )
            assert page["nodes"] and page["hasNextPage"]
            entry_page(session, identity, "article", filters={"category": "news"})
            search_phase = True
            for term, expected in [("article-000001", 0), ("article-000002", 1), ("Live", None)]:
                page = entry_page(session, identity, "article", search=term)
                assert page["total"] == expected if expected is not None else page["total"] > 0
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    with engine.connect() as connection:
        return [
            connection.exec_driver_sql("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, parameters).scalar_one()
            for sql, parameters in captured + totals + searches
        ]


async def verify(base_url):
    delivery = {"Authorization": f"Bearer {DELIVERY_TOKEN}"}
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        data, _ = await request(client, LIST_QUERY, {"search": "", "filters": None}, delivery)
        assert data["entries"]["nodes"]
        assert all(
            node["id"].rsplit("-", 1)[-1].isdigit() and workspace(int(node["id"].rsplit("-", 1)[-1])) == 0
            for node in data["entries"]["nodes"]
        )
        generated, _ = await request(client, GENERATED_QUERY, headers=delivery)
        asset_url = generated["allCmsArticle"][0]["cover"]["url"]
        image = await client.get(asset_url)
        assert image.status_code == 200 and image.content.startswith(b"\x89PNG")
        order_query = 'query($after:String){entries(typeKey:"article",orderBy:{field:"title",direction:ASC},first:20,after:$after){nodes{id data} endCursor hasNextPage}}'
        first_page, _ = await request(client, order_query, {"after": None}, delivery)
        next_page, _ = await request(client, order_query, {"after": first_page["entries"]["endCursor"]}, delivery)
        ordered = first_page["entries"]["nodes"] + next_page["entries"]["nodes"]
        assert len({row["id"] for row in ordered}) == 40
        assert [(row["data"]["title"], row["id"]) for row in ordered] == sorted(
            (row["data"]["title"], row["id"]) for row in ordered
        )
        comparison = {"legacyTitle": [], "indexedTitle": []}
        legacy_query = '{entries(typeKey:"article",sort:"title_asc",first:20){nodes{id data} endCursor hasNextPage}}'
        for _ in range(20):
            for name, query in (
                ("legacyTitle", legacy_query),
                ("indexedTitle", order_query),
            ):
                started = time.perf_counter()
                await request(client, query, {"after": None}, delivery)
                comparison[name].append((time.perf_counter() - started) * 1000)
        headers, saved = await editor(client, 0)
        assert "PRIVATE-BENCHMARK-MARKER" in json.dumps(saved)
        hidden = await client.post(
            "/delivery/graphql",
            headers=delivery,
            json={"query": "{allCmsRestricted(first:1){id}}"},
        )
        assert hidden.json().get("errors"), "Token scope exposed restricted schema"
        draft = await client.post(
            "/delivery/graphql",
            headers=delivery,
            json={"query": ENTRY_QUERY, "variables": {"id": "benchmark-entry-0"}},
        )
        assert draft.json().get("errors") or draft.json().get("data", {}).get("entry") is None
        response = await client.post(
            "/graphql",
            headers={**headers, "X-Moss-Project": "benchmark-workspace-1"},
            json={"query": "{entries(first:1){total}}"},
        )
        assert response.status_code == 403, "Editorial workspace isolation failed"
    return {
        "delivery": True,
        "scalarOrdering": True,
        "sequentialOrderProbe": {key: summarize(values, sum(values) / 1000) for key, values in comparison.items()},
        "privateFieldsExcluded": True,
        "workspaceIsolation": True,
        "scopeIsolation": True,
        "draftExcluded": True,
        "media": True,
    }


async def prepare_schedule(base_url):
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        headers, saved = await editor(client, 0)
        due = datetime.now(timezone.utc) + timedelta(seconds=10)
        data = {**saved["data"], "title": "Captured benchmark publication"}
        query = SAVE_QUERY.replace("$version:Int!", "$version:Int!,$due:String!").replace(
            'status:"draft"', 'status:"scheduled",scheduledAt:$due'
        )
        result, _ = await request(
            client,
            query,
            {
                "id": saved["id"],
                "slug": saved["slug"],
                "data": data,
                "version": saved["version"],
                "due": due.isoformat(),
            },
            headers,
            True,
        )
        capture = result["saveEntry"]
        await request(
            client,
            SAVE_QUERY,
            {
                "id": saved["id"],
                "slug": saved["slug"],
                "data": {**data, "title": "Later benchmark draft"},
                "version": capture["version"],
            },
            headers,
            True,
        )
        return {
            "entryId": saved["id"],
            "revision": capture["scheduledRevision"],
            "due": due.isoformat(),
            "liveTitle": data["title"],
            "draftTitle": "Later benchmark draft",
        }


def verify_schedule(engine, expected):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        with engine.connect() as connection:
            entry = (
                connection.execute(
                    text("SELECT data,published_data,published_revision,scheduled_at FROM entries WHERE id=:id"),
                    {"id": expected["entryId"]},
                )
                .mappings()
                .one()
            )
            if entry["published_revision"] == expected["revision"]:
                assert entry["data"]["title"] == expected["draftTitle"]
                assert entry["published_data"]["title"] == expected["liveTitle"]
                assert entry["scheduled_at"] is None
                events = connection.execute(
                    text(
                        "SELECT count(*) FROM publication_events WHERE payload->>'entryId'=:id "
                        "AND payload->>'publicationRevision'=:revision AND payload->>'event'='published'"
                    ),
                    {"id": expected["entryId"], "revision": str(expected["revision"])},
                ).scalar_one()
                assert events == 1, "Scheduled publication emitted duplicate effects"
                return {
                    "capturedRevisionPublished": True,
                    "laterDraftPreserved": True,
                    "publicationEvents": events,
                }
        time.sleep(1)
    raise AssertionError("Captured schedule did not publish within 45 seconds after restart")


async def verify_history(base_url):
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        headers, saved = await editor(client, 2)
        before, _ = await request(
            client,
            ENTRY_QUERY.replace("data version", "data publishedData version"),
            {"id": saved["id"]},
            headers,
            True,
        )
        result, _ = await request(
            client,
            "mutation($id:ID!,$version:Int!){restoreEntry(id:$id,number:3,version:$version){data publishedData publishedRevision scheduledRevision version}}",
            {"id": saved["id"], "version": saved["version"]},
            headers,
            True,
        )
        restored = result["restoreEntry"]
        assert restored["data"] == before["entry"]["publishedData"]
        assert restored["publishedData"] == before["entry"]["publishedData"]
        assert restored["scheduledRevision"] == saved["scheduledRevision"]
        assert restored["publishedRevision"] == saved["publishedRevision"]
        assert restored["version"] > saved["version"]
    return {
        "historicalRevisionRestoredAsDraft": True,
        "liveSnapshotPreserved": True,
        "schedulePreserved": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "seed",
            "run",
            "fingerprint",
            "verify",
            "prepare-schedule",
            "verify-schedule",
            "verify-history",
        ],
    )
    parser.add_argument("--size", type=int, choices=[1000, 10000, 50000, 100000], default=1000)
    parser.add_argument("--seconds", type=int, default=1800)
    parser.add_argument("--readers", type=int, default=20)
    parser.add_argument("--writers", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 86400 or not 1 <= args.readers <= 100 or not 1 <= args.writers <= 3:
        parser.error("Use 1–86400 seconds, 1–100 readers and 1–3 writers.")
    url = guarded_url(os.environ["MOSS_BENCHMARK_DATABASE_URL"])
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "api" if (root / "api").is_dir() else Path("/app")))
    engine = create_engine(url)
    media = Path(os.environ.get("MOSS_STORAGE_DIR", "/data"))
    try:
        if args.action == "seed":
            result = seed(engine, media, args.size)
        else:
            with engine.connect() as connection:
                assert (
                    connection.execute(
                        text("SELECT count(*) FROM projects WHERE id LIKE 'benchmark-workspace-%'")
                    ).scalar_one()
                    == 3
                ), "Not a benchmark fixture"
            if args.action == "fingerprint":
                result = fingerprint(engine, media)
            elif args.action == "verify":
                result = asyncio.run(verify("http://app:8001"))
                result["orderingPlans"] = ordering_plans(engine)
            elif args.action == "prepare-schedule":
                result = asyncio.run(prepare_schedule("http://app:8001"))
            elif args.action == "verify-schedule":
                result = verify_schedule(engine, json.loads(Path("/results/schedule.json").read_text()))
            elif args.action == "verify-history":
                result = asyncio.run(verify_history("http://app:8001"))
            else:
                snapshot_query = text(
                    "SELECT id,published_data,scheduled_data FROM entries "
                    "WHERE id IN ('benchmark-entry-4','benchmark-entry-14','benchmark-entry-24') ORDER BY id"
                )
                with engine.connect() as connection:
                    snapshots_before = connection.execute(snapshot_query).all()
                result = asyncio.run(workload("http://app:8001", args.seconds, args.readers, args.writers))
                with engine.connect() as connection:
                    assert connection.execute(snapshot_query).all() == snapshots_before, (
                        "Draft load changed captured snapshots"
                    )
                    result["liveAndScheduledSnapshotsPreserved"] = True
                    result["databaseBytes"] = connection.execute(
                        text("SELECT pg_database_size(current_database())")
                    ).scalar_one()
                    result["scalarIndexStorage"] = dict(
                        connection.execute(
                            text(
                                "SELECT pg_table_size('entry_field_indexes') AS table_bytes, pg_indexes_size('entry_field_indexes') AS index_bytes, (SELECT count(*) FROM entry_field_indexes) AS rows"
                            )
                        )
                        .mappings()
                        .one()
                    )
                    result["searchIndexStorage"] = dict(
                        connection.execute(
                            text(
                                "SELECT pg_relation_size('ix_entries_draft_search') AS draft_bytes, pg_relation_size('ix_entries_published_search') AS published_bytes"
                            )
                        )
                        .mappings()
                        .one()
                    )
        write_json(args.output, result)
        print(
            json.dumps(
                {
                    "action": args.action,
                    "output": args.output.name,
                    "errors": result.get("errors", {}),
                }
            )
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
