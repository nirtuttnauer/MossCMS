#!/usr/bin/env python3
"""Destructive fixture walkthrough: use ONLY the explicitly guarded disposable restored database.
Run with api/.venv/bin/python; build personal-site first. Ports 18033/15133 must be free.
The fixture database must have no user accounts and 1,004 schema-0001 fixture entries.
"""

import os, time, json, subprocess, platform, math, secrets
from io import BytesIO
from PIL import Image
from pathlib import Path
from datetime import datetime, timedelta, timezone
import httpx

ROOT = Path(__file__).resolve().parents[1]
NODE = os.environ.get("MOSS_RELEASE_NODE", "node")
from sqlalchemy.engine import make_url

release_database = os.environ["MOSS_RELEASE_DATABASE_URL"]
url = make_url(release_database)
if url.host not in {"127.0.0.1", "localhost"} or not (url.database or "").startswith(
    "moss_release_"
):
    raise SystemExit(
        "Use an explicit loopback moss_release_* disposable database restored from the fixture."
    )
from sqlalchemy import create_engine, text

fixture_engine = create_engine(release_database)
with fixture_engine.connect() as connection:
    if (
        connection.execute(text("select count(*) from users")).scalar_one() != 0
        or connection.execute(
            text("select count(*) from entries where id like 'legacy-%'")
        ).scalar_one()
        != 1004
    ):
        raise SystemExit(
            "Restore the clean 1004-entry fixture with no accounts before this walkthrough."
        )
fixture_engine.dispose()
env = {
    **os.environ,
    "DATABASE_URL": release_database,
    "MOSS_SECRET_KEY": "fixture-only-secret-" * 3,
    "MOSS_SETUP_TOKEN": "fixture-only-setup-" * 3,
    "MOSS_STORAGE_DIR": "/tmp/moss33-media",
    "MOSS_PUBLIC_URL": "http://127.0.0.1:18033",
    "MOSS_SKIP_AUTH": "false",
    "MOSS_WEBHOOK_ORIGINS": "http://127.0.0.1:15133",
}
api = subprocess.Popen(
    [
        str(ROOT / "api/.venv/bin/python"),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "18033",
        "--no-access-log",
    ],
    cwd=ROOT / "api",
    env=env,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
site = None
try:
    c = httpx.Client(base_url="http://127.0.0.1:18033", timeout=15)
    for _ in range(100):
        try:
            if c.get("/ready").status_code == 200:
                break
        except httpx.ConnectError:
            pass
        time.sleep(0.1)
    response = c.post(
        "/auth/setup",
        json={
            "token": env["MOSS_SETUP_TOKEN"],
            "name": "Release fixture",
            "email": "release@example.com",
            "password": "fixture-only-password-long",
        },
    )
    assert response.status_code == 200, response.text
    me = c.get("/auth/me").json()
    h = {"x-moss-project": me["projects"][0]["id"], "x-moss-csrf": me["csrf"]}

    def gql(query, variables=None, delivery=False):
        response = c.post(
            "/delivery/graphql" if delivery else "/graphql",
            headers=({"Authorization": "Bearer " + token} if delivery else h),
            json={"query": query, "variables": variables},
        )
        result = response.json()
        assert not result.get("errors"), result
        return result["data"]

    def define(key, fields):
        return gql(
            "mutation($key:String!,$fields:JSON!){saveContentType(key:$key,name:$key,fields:$fields){id}}",
            {"key": key, "fields": fields},
        )

    text = lambda name, **extra: {"name": name, "type": "text", **extra}
    image = {
        "name": "cover",
        "type": "object",
        "fields": [
            {"name": "asset", "type": "asset", "imageOnly": True},
            text("alt"),
            {"name": "focalX", "type": "number"},
        ],
    }
    define(
        "sitePage",
        [
            text("title"),
            {"name": "kind", "type": "enum", "options": ["home", "blog", "projects"]},
            text(
                "body",
            ),
        ],
    )
    define("siteProfile", [text("name"), text("headline")])
    define(
        "sitePost",
        [
            text("title", required=True),
            {"name": "body", "type": "richText"},
            text("description"),
            text("secret", private=True),
            image,
        ],
    )
    define(
        "siteProject",
        [
            text("title"),
            {"name": "body", "type": "richText"},
            {
                "name": "gallery",
                "type": "list",
                "item": {"type": "object", "fields": image["fields"]},
            },
        ],
    )
    define(
        "siteSlide",
        [
            text("title"),
            {"name": "kind", "type": "enum", "options": ["promotion"]},
            {"name": "enabled", "type": "boolean"},
        ],
    )
    mutation = "mutation($key:String!,$slug:String!,$data:JSON!,$status:String!,$id:ID,$version:Int,$due:String,$request:String){saveEntry(typeKey:$key,slug:$slug,data:$data,status:$status,id:$id,version:$version,scheduledAt:$due,requestKey:$request){id version publishedRevision slug data isLive scheduledRevision}}"

    def save(key, slug, data, status="published", saved=None, due=None):
        return gql(
            mutation,
            {
                "key": key,
                "slug": slug,
                "data": data,
                "status": status,
                "id": saved["id"] if saved else None,
                "version": saved["version"] if saved else None,
                "due": due,
                "request": secrets.token_urlsafe(20),
            },
        )["saveEntry"]

    save(
        "siteProfile",
        "profile",
        {"name": "Release fixture", "headline": "Acceptance fixture"},
    )
    save("sitePage", "home", {"title": "Home", "kind": "home"})
    save("sitePage", "blog", {"title": "Blog", "kind": "blog"})
    save("sitePage", "projects", {"title": "Projects", "kind": "projects"})
    token = c.post(
        "/api/tokens",
        headers=h,
        json={
            "name": "release-website",
            "days": 1,
            "scopes": [
                "sitePage",
                "siteProfile",
                "sitePost",
                "siteProject",
                "siteSlide",
            ],
        },
    ).json()["token"]
    hook = c.post(
        "/api/webhooks",
        headers=h,
        json={"url": "http://127.0.0.1:15133/api/moss-events"},
    )
    assert hook.status_code == 200, hook.text
    hook = hook.json()
    siteenv = {
        **os.environ,
        "MOSS_API_URL": "http://127.0.0.1:18033",
        "MOSS_DELIVERY_TOKEN": token,
        "SITE_PUBLIC_URL": "http://127.0.0.1:15133",
        "PORT": "15133",
        "MOSS_WEBHOOK_SECRET": hook["secret"],
        "SITE_MOSS_WORKSPACE_ID": h["x-moss-project"],
    }
    site = subprocess.Popen(
        [NODE, "server/index.mjs"],
        cwd=ROOT / "personal-site",
        env=siteenv,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    w = httpx.Client(base_url="http://127.0.0.1:15133", timeout=15)
    for _ in range(100):
        try:
            if w.get("/api/site").status_code == 200:
                break
        except httpx.ConnectError:
            pass
        time.sleep(0.1)
    draft = save(
        "sitePost",
        "acceptance",
        {
            "title": "Draft only",
            "body": "## Heading\n\n**Bold** [Safe](https://example.com)",
            "secret": "PRIVATE_ONLY",
        },
        "draft",
    )
    assert not any(p["id"] == draft["id"] for p in w.get("/api/site").json()["pages"])
    assert w.get("/blog/acceptance").status_code == 404
    c.patch(
        "/api/project/preview", headers=h, json={"origin": "http://127.0.0.1:15133"}
    )
    grant = gql(
        "mutation($id:ID!,$version:Int!){createPreviewGrant(id:$id,version:$version)}",
        draft,
    )["createPreviewGrant"]
    assert grant["previewUrl"].startswith("http://127.0.0.1:15133/preview#grant=")
    preview = httpx.Client(base_url=w.base_url, timeout=15)
    assert "history.replaceState" in preview.get("/preview").text
    r = preview.post(
        "/api/preview",
        headers={"Origin": "http://127.0.0.1:15133"},
        json={"token": grant["token"]},
    )
    assert r.status_code == 200, r.text
    assert "HttpOnly" in r.headers["set-cookie"]
    preview_data = preview.get("/api/site").json()
    assert preview_data["preview"]["revision"] == draft["version"]
    assert "PRIVATE_ONLY" not in json.dumps(preview_data)
    assert not any(p["id"] == draft["id"] for p in w.get("/api/site").json()["pages"])
    gql("mutation($id:ID!){revokePreviewGrant(id:$id)}", {"id": grant["id"]})
    assert preview.get("/api/site").status_code == 401
    # Cover/gallery asset IDs and bounded signed variant delivery across HTTP.
    image_bytes = BytesIO()
    Image.new("RGB", (800, 400), "red").save(image_bytes, format="PNG")
    upload = c.post(
        "/api/assets",
        headers=h,
        files={"file": ("cover.png", image_bytes.getvalue(), "image/png")},
    )
    assert upload.status_code == 200, upload.text
    asset = upload.json()
    project = save(
        "siteProject",
        "gallery",
        {
            "title": "Gallery",
            "gallery": [{"asset": asset["id"], "alt": "Red rectangle", "focalX": 20}],
        },
    )
    manifest = gql(
        '{entries(typeKey:"siteProject"){nodes{data resolvedAssets{id width height variants}}}}',
        delivery=True,
    )["entries"]["nodes"][0]
    assert (
        manifest["data"]["gallery"][0]["asset"] == asset["id"]
        and manifest["resolvedAssets"][0]["width"] == 800
    )
    assert (
        c.get(manifest["resolvedAssets"][0]["variants"][0]["url"]).headers[
            "content-type"
        ]
        == "image/webp"
    )
    latencies = []
    freshness = []
    for i in range(12):
        w.get("/api/site")  # warm cache to require an event
        started = time.perf_counter()
        draft = save(
            "sitePost",
            "acceptance",
            {
                "title": f"Published {i}",
                "body": "## Heading\n\n**Bold** [Safe](https://example.com)",
            },
            saved=draft,
        )
        latencies.append(time.perf_counter() - started)
        committed = time.perf_counter()
        for _ in range(160):
            pages = w.get("/api/site").json()["pages"]
            if any(
                p["id"] == draft["id"] and p["title"] == f"Published {i}" for p in pages
            ):
                break
            time.sleep(0.05)
        else:
            raise AssertionError("No website update")
        freshness.append(time.perf_counter() - committed)
    old = draft.copy()
    edited = save(
        "sitePost",
        "changed-draft",
        {"title": "Newer working title"},
        "draft",
        saved=draft,
    )
    assert any(
        p["slug"] == "blog/acceptance" and p["title"] == "Published 11"
        for p in w.get("/api/site").json()["pages"]
    )
    assert w.get("/blog/changed-draft").status_code == 404
    page = w.get("/blog/acceptance")
    assert (
        page.status_code == 200
        and "<title>Published 11" in page.text
        and "http://127.0.0.1:15133/blog/acceptance" in page.text
    )
    assert w.get("/acceptance", follow_redirects=False).status_code == 308
    assert (
        "/blog/acceptance" in w.get("/sitemap.xml").text
        and "Published 11" in w.get("/rss.xml").text
    )
    due = datetime.now(timezone.utc) + timedelta(seconds=2)
    queued = save(
        "sitePost",
        "scheduled-capture",
        {"title": "Captured schedule"},
        "scheduled",
        saved=edited,
        due=due.isoformat(),
    )
    newer = save(
        "sitePost", "newer-draft", {"title": "Later draft"}, "draft", saved=queued
    )
    for _ in range(220):
        public = gql(
            '{entries(typeKey:"sitePost"){nodes{slug data version}}}', delivery=True
        )["entries"]["nodes"]
        if any(p["slug"] == "scheduled-capture" for p in public):
            break
        time.sleep(0.05)
    else:
        raise AssertionError("Schedule never published")
    schedule_delay = (datetime.now(timezone.utc) - due).total_seconds()
    # A ten-entry same-due batch exercises scheduling throughput under this fixture.
    batch_due = datetime.now(timezone.utc) + timedelta(seconds=2)
    batch = []
    for index in range(10):
        batch.append(
            save(
                "sitePost",
                f"batch-{index}",
                {"title": f"Batch {index}"},
                "scheduled",
                due=batch_due.isoformat(),
            )["id"]
        )
    for _ in range(220):
        delivered = gql(
            '{entries(typeKey:"sitePost",first:100){nodes{id publishedAt}}}',
            delivery=True,
        )["entries"]["nodes"]
        batch_times = [
            (
                datetime.fromisoformat(p["publishedAt"].replace("Z", "+00:00"))
                - batch_due
            ).total_seconds()
            for p in delivered
            if p["id"] in batch
        ]
        if len(batch_times) == 10:
            break
        time.sleep(0.05)
    else:
        raise AssertionError("Scheduled batch incomplete")
    assert (
        public[0]["data"]["title"] == "Captured schedule"
        and public[0]["version"] == queued["version"]
    )
    current = gql("query($id:ID!){entry(id:$id){id version slug data isLive}}", newer)[
        "entry"
    ]
    assert current["slug"] == "newer-draft"
    gql(
        "mutation($id:ID!,$version:Int!){unpublishEntry(id:$id,version:$version){id}}",
        current,
    )
    assert not any(
        p["id"] == current["id"]
        for p in gql(
            '{entries(typeKey:"sitePost",first:100){nodes{id}}}', delivery=True
        )["entries"]["nodes"]
    )
    # Fallback without webhook: simulate browser's 10-second polling interval.
    assert c.delete("/api/webhooks/" + hook["id"], headers=h).status_code == 200
    fallback = []
    for i in range(2):
        w.get("/api/site")
        current = gql("query($id:ID!){entry(id:$id){id version}}", current)["entry"]
        save("sitePost", "fallback", {"title": f"Fallback {i}"}, saved=current)
        start = time.perf_counter()
        time.sleep(10)
        assert any(
            p["title"] == f"Fallback {i}" for p in w.get("/api/site").json()["pages"]
        )
        fallback.append(time.perf_counter() - start)

    def p95(values):
        return sorted(values)[math.ceil(len(values) * 0.95) - 1]

    results = {
        "hardware": platform.machine() + " " + platform.platform(),
        "apiSaves": len(latencies),
        "saveP95Seconds": round(p95(latencies), 4),
        "eventFreshnessP95Seconds": round(p95(freshness), 4),
        "eventFreshnessRangeSeconds": [
            round(min(freshness), 4),
            round(max(freshness), 4),
        ],
        "scheduledPublishDelaySeconds": round(schedule_delay, 4),
        "scheduledBatchSamples": len(batch_times),
        "scheduledBatchP95Seconds": round(p95(batch_times), 4),
        "localCoverGalleryVariantHTTP": "passed",
        "fallbackPollSeconds": [round(v, 4) for v in fallback],
        "previewRevocationAndIsolation": "passed",
        "metadataRoutesFeeds": "passed",
        "legacyDatasetEntries": 1004,
        "concurrency": "one HTTP author, sequential requests",
        "build": "local uvicorn + production Node website; PostgreSQL17 Docker",
    }
    Path(os.environ.get("MOSS_RELEASE_RESULTS", "/tmp/moss33-results.json")).write_text(
        json.dumps(results, indent=2)
    )
    print(json.dumps(results, indent=2))
finally:
    if site:
        site.terminate()
        site.wait(timeout=10)
    api.terminate()
    api.wait(timeout=10)
