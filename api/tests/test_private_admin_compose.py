"""Variant A allowlist proxy and variant B private listener, exercised with Compose."""

import base64
import json
import os
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from scripts.classify_routes import classify, load_app, route_keys

pytestmark = pytest.mark.compose

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "reviews" / "MOSS-059"
PROJECT = "moss059"
PROXY = "http://127.0.0.1:18059"
PRIVATE = "http://127.0.0.1:18058"
SITE = "http://127.0.0.1:18057"
SECRET = "s" * 40
SETUP = "t" * 30
EMAIL = "moss059-admin@example.com"
PASSWORD = "secure-test-password"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
FIELDS = [
    {"name": "title", "type": "text", "required": True},
    {"name": "body", "type": "richText"},
    {"name": "kind", "type": "text"},
    {"name": "description", "type": "text"},
]
SAMPLES = {
    "id": "11111111-1111-1111-1111-111111111111",
    "typeKey": "article",
    "user_id": "22222222-2222-2222-2222-222222222222",
    "token_id": "abc",
    "provider": "github",
    "width": "320",
    "project_id": "33333333-3333-3333-3333-333333333333",
}


def _compose_env():
    # The env file is the source for this stack. A parent MOSS_USE_SQLITE must not select the other database file.
    return {key: value for key, value in os.environ.items() if not key.startswith(("MOSS_", "POSTGRES_", "COMPOSE_"))}


def _run(command, timeout=900):
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=timeout, env=_compose_env())
    if completed.returncode != 0:
        raise AssertionError(
            f"{' '.join(command)}\nexit {completed.returncode}\n{completed.stdout[-4000:]}\n{completed.stderr[-4000:]}"
        )
    return completed


def _concrete(path):
    for name, value in SAMPLES.items():
        path = path.replace("{" + name + "}", value)
    if "{" in path:
        raise AssertionError(path)
    return path


def _raw(url, method="GET", headers=None):
    # -X HEAD still waits for a body. --head tells curl the response has none.
    command = ["curl", "-sS", "--path-as-is", "--max-time", "15", "-D", "-", "-o", "/tmp/moss059-body"]
    command.append("--head" if method == "HEAD" else "-X")
    if method != "HEAD":
        command.append(method)
    for key, value in (headers or {}).items():
        command.extend(["-H", f"{key}: {value}"])
    command.append(url)
    completed = subprocess.run(command, text=True, capture_output=True, timeout=30)
    status = None
    request_id = None
    for line in completed.stdout.splitlines():
        if line.startswith("HTTP/"):
            status = int(line.split()[1])
        elif line.lower().startswith("x-request-id:"):
            request_id = line.split(":", 1)[1].strip()
    body = b"" if method == "HEAD" else Path("/tmp/moss059-body").read_bytes()
    return status, request_id, body, completed.returncode, completed.stderr


def _port_open(port):
    with socket.socket() as sock:
        sock.settimeout(2)
        try:
            sock.connect(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _log_json(stack, request_id):
    last = ""
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        last = stack.logs()
        for line in last.splitlines():
            if request_id not in line or '"path"' not in line:
                continue
            return json.loads(line[line.find("{") : line.rfind("}") + 1])
        time.sleep(0.2)
    raise AssertionError(f"{request_id} missing from app log\n{last[-2000:]}")


class Stack:
    def __init__(self, tmp_path):
        self.env_file = tmp_path / "moss059.env"
        self.token = "unset"
        self.webhook_secret = "unset"
        self.project_id = "unset"
        self.cookie = ""
        self.csrf = ""
        self.admin = {}
        self.variant_url = ""
        self.grant = ""
        self.http = httpx.Client(base_url=PRIVATE, timeout=20)
        self.site_env = ROOT / "example-site" / ".env"
        self.created_site_env = False
        self.overlays = ("variant-a.compose.yaml",)

    def close(self):
        self.http.close()
        command = [
            "docker",
            "compose",
            "--env-file",
            str(self.env_file),
            "-p",
            PROJECT,
            "-f",
            str(ROOT / "compose.yaml"),
        ]
        for name in ("variant-a.compose.yaml", "variant-b.compose.yaml", "variant-b-published.compose.yaml"):
            command.extend(["-f", str(REVIEW / name)])
        subprocess.run(
            [*command, "--profile", "website", "down", "--volumes", "--remove-orphans"],
            cwd=ROOT,
            timeout=180,
            env=_compose_env(),
        )
        if self.created_site_env and self.site_env.exists():
            self.site_env.unlink()

    def write_env(self):
        values = {
            "MOSS_USE_SQLITE": "true",
            "MOSS_SECRET_KEY": SECRET,
            "MOSS_SETUP_TOKEN": SETUP,
            "MOSS_DELIVERY_TOKEN": self.token,
            "MOSS_WEBHOOK_SECRET": self.webhook_secret,
            "SITE_MOSS_WORKSPACE_ID": self.project_id,
        }
        self.env_file.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
        if not self.site_env.exists():
            self.site_env.write_text(
                "MOSS_API_URL=http://app:8001\nMOSS_DELIVERY_TOKEN=unset\nSITE_PUBLIC_URL=http://127.0.0.1:18057\n"
            )
            self.created_site_env = True

    def compose(self, *args, overlays=None, profile=False):
        command = ["docker", "compose", "--env-file", str(self.env_file), "-p", PROJECT]
        if profile:
            command.extend(["--profile", "website"])
        command.extend(["-f", str(ROOT / "compose.yaml")])
        for name in overlays or self.overlays:
            command.extend(["-f", str(REVIEW / name)])
        command.extend(args)
        return command

    def config(self, overlays):
        completed = _run(self.compose("config", "--format", "json", overlays=overlays))
        return json.loads(completed.stdout)

    def exec(self, service, *args, env=None):
        command = self.compose("exec", "-T", profile=True)
        for key, value in (env or {}).items():
            command.extend(["-e", f"{key}={value}"])
        command.extend([service, *args])
        return _run(command, timeout=60)

    def app_call(self, method, path, headers=None, body=None):
        spec = json.dumps({"method": method, "path": path, "headers": headers or {}, "body": body})
        script = (
            "import json,os,urllib.request,urllib.error\n"
            "spec=json.loads(os.environ['MOSS_CALL'])\n"
            "data=None if spec['body'] is None else spec['body'].encode()\n"
            "request=urllib.request.Request('http://127.0.0.1:8001'+spec['path'],data=data,headers=spec['headers'],method=spec['method'])\n"
            "try:\n"
            "  response=urllib.request.urlopen(request,timeout=20)\n"
            "  raw=response.read().decode()\n"
            "  print(json.dumps({'status':response.status,'body':raw[:4000]}))\n"
            "except urllib.error.HTTPError as error:\n"
            "  print(json.dumps({'status':error.code,'body':error.read().decode()[:4000]}))\n"
        )
        completed = self.exec("app", "python", "-c", script, env={"MOSS_CALL": spec})
        return json.loads(completed.stdout.strip().splitlines()[-1])

    def logs(self):
        return _run(self.compose("logs", "app", "--no-color"), timeout=60).stdout

    def gql(self, query, variables=None):
        response = self.http.post("/graphql", json={"query": query, "variables": variables or {}}, headers=self.admin)
        assert response.status_code == 200, response.text
        body = response.json()
        assert "errors" not in body, body
        return body["data"]

    def cookie_headers(self, extra=None):
        headers = {"cookie": f"moss_session={self.cookie}", **(extra or {})}
        return headers


def test_variant_a_proxy_and_variant_b_private_listener(tmp_path):
    stack = Stack(tmp_path)
    try:
        stack.write_env()
        rendered = stack.config(("variant-b.compose.yaml",))
        assert "ports" not in rendered["services"]["app"], rendered["services"]["app"].keys()
        _run(
            stack.compose(
                "up",
                "-d",
                "--build",
                "--wait",
                "--wait-timeout",
                "240",
                "app",
                "public-proxy",
                overlays=("variant-a.compose.yaml",),
            )
        )
        _seed(stack)
        _assert_proxy_matrix(stack)
        _assert_confusion(stack)
        _assert_graphql_admin_preview_media_health(stack)
        _assert_proxy_peer(stack)
        _start_site_and_webhook(stack)
        _assert_variant_b(stack)
    finally:
        stack.close()


def _seed(stack):
    setup = stack.http.post(
        "/auth/setup",
        json={"token": SETUP, "email": EMAIL, "password": PASSWORD, "name": "Moss"},
    )
    assert setup.status_code == 200, setup.text
    logged_in = stack.http.post(
        "/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        headers={"X-Forwarded-For": "203.0.113.50", "Forwarded": "for=203.0.113.50"},
    )
    assert logged_in.status_code == 200, logged_in.text
    for index in range(7):
        failed = stack.http.post(
            "/auth/login",
            json={"email": EMAIL, "password": "wrong-password-value"},
            headers={"X-Forwarded-For": f"203.0.113.{index}", "Forwarded": f"for=203.0.113.{index}"},
        )
        assert failed.status_code == 401, failed.text
    blocked = stack.http.post(
        "/auth/login",
        json={"email": EMAIL, "password": "wrong-password-value"},
        headers={"X-Forwarded-For": "198.51.100.9", "Forwarded": "for=198.51.100.9"},
    )
    assert blocked.status_code == 429, blocked.text
    audit = stack.exec(
        "app",
        "python",
        "-c",
        "import sqlite3; print(sqlite3.connect('/data/mosscms.db').execute(\"select details from audit where action='account.login'\").fetchone()[0])",
    )
    details = json.loads(audit.stdout.strip())
    assert details["client"] != "203.0.113.50"
    assert "203.0.113" not in json.dumps(details)
    assert "198.51.100" not in json.dumps(details)

    me = stack.http.get("/auth/me")
    assert me.status_code == 200, me.text
    account = me.json()
    stack.csrf = account["csrf"]
    stack.project_id = account["projects"][0]["id"]
    stack.cookie = stack.http.cookies.get("moss_session")
    stack.admin = {"x-moss-project": stack.project_id, "x-moss-csrf": stack.csrf}
    stack.gql(
        "mutation($key:String!,$fields:JSON!){saveContentType(key:$key,name:$key,fields:$fields){key}}",
        {"key": "sitePage", "fields": FIELDS},
    )
    stack.gql(
        'mutation($slug:String!,$data:JSON!){saveEntry(typeKey:"sitePage",slug:$slug,data:$data,status:"published"){id version}}',
        {"slug": "home", "data": {"title": "Home", "body": "Home", "kind": "home", "description": "Home"}},
    )
    note = stack.gql(
        'mutation($slug:String!,$data:JSON!){saveEntry(typeKey:"sitePage",slug:$slug,data:$data,status:"published"){id version}}',
        {
            "slug": "moss059-note",
            "data": {
                "title": "Moss059 Published Title",
                "body": "Moss059 body",
                "kind": "page",
                "description": "Moss059 description",
            },
        },
    )["saveEntry"]
    issued = stack.http.post("/api/tokens", headers=stack.admin, json={"name": "site", "scopes": [], "days": 1})
    assert issued.status_code == 200, issued.text
    stack.token = issued.json()["token"]
    uploaded = stack.http.post("/api/assets", headers=stack.admin, files={"file": ("dot.png", PNG, "image/png")})
    assert uploaded.status_code == 200, uploaded.text
    uploaded_body = uploaded.json()
    variant = uploaded_body["variants"][0]
    stack.asset_id = uploaded_body["id"]
    stack.variant_width = variant["width"]
    stack.variant_url = variant["url"]
    assert variant["url"].startswith(PROXY + "/media/")
    grant = stack.gql(
        "mutation($id:ID!,$version:Int!){createPreviewGrant(id:$id,version:$version)}",
        {"id": note["id"], "version": note["version"]},
    )["createPreviewGrant"]
    stack.grant = grant["token"]
    stack.note = note


def _assert_proxy_matrix(stack):
    classified = classify(route_keys(load_app()))
    for key, kind in classified.items():
        url = PROXY + _concrete(key.path)
        status, request_id, body, code, err = _raw(url, key.method)
        assert code == 0, (key, err)
        if kind == "private":
            assert status == 404, (key, status, body[:200])
            assert request_id is None, (key, request_id)
        else:
            assert request_id, (key, status, body[:200])
            assert status != 404, (key, status, body[:200])
    health_status, _, health_body, _, _ = _raw(PROXY + "/health")
    assert health_status == 200
    assert json.loads(health_body) == {"status": "ok"}
    lowered = health_body.decode().lower()
    for needle in ("version", "sqlite", "postgres", "secret", "database", "0.2.0"):
        assert needle not in lowered
    for path in ("/openapi.json", "/docs", "/redoc", "/ready", "/metrics", "/graphql"):
        status, request_id, _, _, _ = _raw(PROXY + path)
        assert status == 404 and request_id is None, path


def _assert_confusion(stack):
    before = stack.logs()
    health_before = before.count('"path": "/health"')
    prefixes = ("/api", "/auth", "/graphql", "/metrics")
    paths = ["/DELIVERY/moss059-never", "/DELIVERY/types"]
    for prefix in prefixes:
        paths.extend(
            [
                f"/delivery/../{prefix}/moss059-never",
                f"/delivery/%2e%2e/{prefix}/moss059-never",
                f"/delivery%2F..%2F{prefix}/moss059-never",
                f"//{prefix}/moss059-never",
                f"/delivery;/{prefix}/moss059-never",
                f"{prefix}/moss059-never.",
            ]
        )
    for path in paths:
        status, request_id, _, code, err = _raw(PROXY + path)
        assert code == 0, (path, err)
        assert status == 404 and request_id is None, (path, status, request_id)
    for prefix in prefixes:
        probes = [
            ("/health", {"X-Original-URL": f"{prefix}/moss059-never"}),
            ("/health", {"X-Rewrite-URL": f"{prefix}/moss059-never"}),
            (f"{prefix}/moss059-never", {"X-HTTP-Method-Override": "GET"}),
        ]
        for path, headers in probes:
            status, request_id, _, code, err = _raw(PROXY + path, headers=headers)
            assert code == 0, (path, headers, err)
            assert status == 404 and request_id is None, (path, headers, status, request_id)
    status, request_id, _, _, _ = _raw(
        PROXY + "/delivery/types", method="POST", headers={"X-HTTP-Method-Override": "GET"}
    )
    assert status == 404 and request_id is None
    after = stack.logs()
    assert after.count("moss059-never") == before.count("moss059-never")
    assert after.count('"path": "/health"') == health_before


def _assert_graphql_admin_preview_media_health(stack):
    from app.graphql import generated_schema

    names = list(generated_schema([], delivery=False)._schema.get_type("Mutation").fields)
    delivery = {"Authorization": "Bearer " + stack.token}
    for name in names:
        response = httpx.post(
            PROXY + "/delivery/graphql",
            json={"query": f"mutation {{ {name} }}"},
            headers=delivery,
            timeout=20,
        )
        body = response.json()
        assert response.status_code in {200, 400}, (name, response.status_code, response.text)
        assert not body.get("data"), (name, body)
        assert body.get("errors"), (name, body)
    targeted = httpx.post(
        PROXY + "/delivery/graphql",
        json={
            "query": "mutation($id:ID!,$version:Int!){deleteEntry(id:$id,version:$version)}",
            "variables": {"id": stack.note["id"], "version": stack.note["version"]},
        },
        headers=delivery,
        timeout=20,
    )
    assert targeted.status_code == 200, targeted.text
    assert targeted.json().get("errors")
    kept = stack.gql("query($id:ID!){entry(id:$id){status}}", {"id": stack.note["id"]})
    assert kept["entry"]["status"] == "published"
    intro = httpx.post(
        PROXY + "/delivery/graphql",
        json={
            "query": "{ schemaInfo: __schema { mutationType { name } types { name } } "
            'found: __type(name: "Mutation") { name fields { name } } }'
        },
        headers=delivery,
        timeout=20,
    )
    assert intro.status_code == 200, intro.text
    payload = intro.json()["data"]
    assert payload["schemaInfo"]["mutationType"] is None
    assert payload["found"] is None
    assert "Mutation" not in {item["name"] for item in payload["schemaInfo"]["types"]}

    session = stack.cookie_headers()
    bearer = {"Authorization": "Bearer " + stack.cookie, "x-moss-project": stack.project_id}
    for headers in (session, bearer):
        for path in ("/auth/me", "/api/tokens", "/graphql", "/metrics", "/docs", "/openapi.json"):
            status, request_id, _, _, _ = _raw(PROXY + path, headers=headers)
            assert status == 404 and request_id is None, (path, headers, status, request_id)
    me = stack.http.get("/auth/me")
    assert me.status_code == 200, me.text
    tokens = stack.http.get("/api/tokens", headers=bearer)
    assert tokens.status_code == 200, tokens.text

    redeem_headers = {"Authorization": "Bearer " + stack.token, "content-type": "application/json"}
    private_redeem = stack.http.post("/api/preview/redeem", headers=redeem_headers, json={"token": stack.grant})
    assert private_redeem.status_code == 200, private_redeem.text
    assert private_redeem.json()["entry"]["data"]["title"] == "Moss059 Published Title"
    public_redeem = httpx.post(
        PROXY + "/api/preview/redeem", headers=redeem_headers, json={"token": stack.grant}, timeout=20
    )
    assert public_redeem.status_code == 404
    assert "x-request-id" not in {key.lower() for key in public_redeem.headers}

    media = httpx.get(stack.variant_url, timeout=20)
    assert media.status_code == 200, media.text
    assert media.headers["content-type"].startswith("image/")
    assert len(media.content) > 0


def _assert_proxy_peer(stack):
    peers = []
    for host in ("203.0.113.10", "198.51.100.10"):
        response = httpx.get(
            PROXY + "/health",
            headers={"X-Forwarded-For": host, "Forwarded": f"for={host}"},
            timeout=20,
        )
        assert response.status_code == 200
        recorded = _log_json(stack, response.headers["x-request-id"])
        assert recorded["client"] != host
        assert "203.0.113" not in recorded["client"]
        assert "198.51.100" not in recorded["client"]
        peers.append(recorded["client"])
    assert peers[0] == peers[1]
    direct = httpx.get(PRIVATE + "/health", headers={"X-Forwarded-For": "203.0.113.10"}, timeout=20)
    direct_client = _log_json(stack, direct.headers["x-request-id"])["client"]
    assert direct_client != peers[0]
    assert direct_client != "203.0.113.10"


def _start_site_and_webhook(stack):
    stack.write_env()
    _run(
        stack.compose(
            "up",
            "-d",
            "--build",
            "--wait",
            "--wait-timeout",
            "240",
            "example-site",
            overlays=("variant-a.compose.yaml",),
            profile=True,
        )
    )
    created = stack.http.post(
        "/api/webhooks",
        headers=stack.admin,
        json={"url": "http://example-site:5174/api/moss-events"},
    )
    assert created.status_code == 200, created.text
    stack.webhook_secret = created.json()["secret"]
    stack.write_env()
    _run(
        stack.compose(
            "up",
            "-d",
            "--wait",
            "--wait-timeout",
            "240",
            "--force-recreate",
            "--no-deps",
            "example-site",
            overlays=("variant-a.compose.yaml",),
            profile=True,
        )
    )
    before = _delivered(stack)
    stack.gql(
        'mutation($slug:String!,$data:JSON!){saveEntry(typeKey:"sitePage",slug:$slug,data:$data,status:"published"){id}}',
        {"slug": "moss059-hook", "data": {"title": "Hook", "body": "Hook", "kind": "page", "description": "Hook"}},
    )
    _wait_delivered(stack, before)
    page = httpx.get(SITE + "/moss059-note", timeout=20)
    assert page.status_code == 200, page.text
    assert "Moss059 Published Title" in page.text
    assert httpx.get(SITE + "/openapi.json", timeout=20).status_code == 404
    assert httpx.get(SITE + "/docs", timeout=20).status_code == 404


def _delivered(stack):
    completed = stack.exec(
        "app",
        "python",
        "-c",
        "import sqlite3; print(sqlite3.connect('/data/mosscms.db').execute(\"select count(*) from webhook_deliveries where state='delivered'\").fetchone()[0])",
    )
    return int(completed.stdout.strip())


def _wait_delivered(stack, before):
    deadline = time.monotonic() + 40
    last = before
    while time.monotonic() < deadline:
        last = _delivered(stack)
        if last > before:
            return
        time.sleep(1)
    raise AssertionError(f"webhook deliveries stayed at {last}")


def _assert_variant_b(stack):
    stack.write_env()
    _run(
        stack.compose(
            "up",
            "-d",
            "--wait",
            "--wait-timeout",
            "240",
            "--force-recreate",
            "--remove-orphans",
            overlays=("variant-b.compose.yaml",),
            profile=True,
        )
    )
    assert not _port_open(18058)
    assert not _port_open(8001)
    page = httpx.get(SITE + "/moss059-note", timeout=20)
    assert page.status_code == 200, page.text
    assert "Moss059 Published Title" in page.text
    assert httpx.get(SITE + "/openapi.json", timeout=20).status_code == 404
    assert httpx.get(SITE + "/docs", timeout=20).status_code == 404
    redeem = stack.exec(
        "example-site",
        "node",
        "-e",
        "fetch('http://app:8001/api/preview/redeem',{method:'POST',headers:{'content-type':'application/json',authorization:'Bearer '+process.env.MOSS_DELIVERY_TOKEN},body:JSON.stringify({token:process.env.GRANT})}).then(async (response)=>{const body=await response.text(); console.log(JSON.stringify({status:response.status,body:body.slice(0,300)})); if(response.status!==200) process.exit(1);});",
        env={"GRANT": stack.grant},
    )
    assert '"status": 200' in redeem.stdout or '"status":200' in redeem.stdout
    assert "Moss059 Published Title" in redeem.stdout
    from app.media_links import media_signature

    expires = int(time.time()) + 600
    signature = media_signature(SECRET, stack.asset_id, expires, stack.variant_width)
    media_url = (
        f"http://app:8001/media/{stack.asset_id}/variant/{stack.variant_width}?expires={expires}&signature={signature}"
    )
    fetched = stack.exec(
        "example-site",
        "node",
        "-e",
        "fetch(process.env.MEDIA_URL).then(async (response)=>{const bytes=(await response.arrayBuffer()).byteLength; console.log(JSON.stringify({status:response.status,type:response.headers.get('content-type'),bytes})); if(response.status!==200) process.exit(1);});",
        env={"MEDIA_URL": media_url},
    )
    media = json.loads(fetched.stdout.strip().splitlines()[-1])
    assert media["status"] == 200 and media["bytes"] > 0 and media["type"].startswith("image/")
    before = _delivered(stack)
    published = stack.app_call(
        "POST",
        "/graphql",
        headers={
            "content-type": "application/json",
            "cookie": f"moss_session={stack.cookie}",
            "x-moss-project": stack.project_id,
            "x-moss-csrf": stack.csrf,
        },
        body=json.dumps(
            {
                "query": 'mutation($slug:String!,$data:JSON!){saveEntry(typeKey:"sitePage",slug:$slug,data:$data,status:"published"){id}}',
                "variables": {
                    "slug": "moss059-private",
                    "data": {"title": "Private", "body": "Private", "kind": "page", "description": "Private"},
                },
            }
        ),
    )
    assert published["status"] == 200, published
    assert "errors" not in published["body"], published
    _wait_delivered(stack, before)

    _run(
        stack.compose(
            "up",
            "-d",
            "--wait",
            "--wait-timeout",
            "180",
            "--force-recreate",
            "--no-deps",
            "app",
            overlays=("variant-b.compose.yaml", "variant-b-published.compose.yaml"),
            profile=True,
        )
    )
    assert _port_open(18058)
    opened = httpx.get(PRIVATE + "/health", timeout=20)
    assert opened.status_code == 200 and opened.json() == {"status": "ok"}
    _run(
        stack.compose(
            "up",
            "-d",
            "--wait",
            "--wait-timeout",
            "180",
            "--force-recreate",
            "--no-deps",
            "app",
            overlays=("variant-b.compose.yaml",),
            profile=True,
        )
    )
    assert not _port_open(18058)
    assert not _port_open(8001)
