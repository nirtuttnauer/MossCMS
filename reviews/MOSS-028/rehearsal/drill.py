#!/usr/bin/env python3
"""MOSS-028 upgrade and rollback rehearsal on this Linux VM.

Builds the image at 1d6d0ef (schema 0009) and the image at the current checkout
(schema 0014), loads content and media, upgrades in place, then restores the
pre-upgrade backup onto the older image. Alembic is not asked to move down.
Secrets stay in /tmp and in the gitignored .env. Evidence under reviews/MOSS-028
is redacted.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import ssl
import subprocess
import time
import urllib.error
import urllib.request
import zlib
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "reviews" / "MOSS-028"
OLD_SHA = "1d6d0ef5bcc2b2c8d7dd628098c89b680b060a9a"
OLD_IMAGE = "mosscms:moss028-1d6d0ef"
NEW_IMAGE = "mosscms:moss028-58a0f15"
PROBE_IMAGE = "mosscms:moss028-probe"
PROJECT = "moss028"
PUBLIC_URL = "https://cms.moss.test:8443"
TLS_DIR = Path("/tmp/moss-028-tls")
WORK_DIR = Path("/tmp/moss028")
NGINX_CONF = EVIDENCE / "rehearsal" / "nginx.conf"
BUILD_LOG = Path("/tmp/moss028-image-build.log")

SECRETS: list[str] = []
PHASE = "rehearsal"


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def remember(value: str | None) -> None:
    if value and value not in SECRETS and len(value) >= 8:
        SECRETS.append(value)


def redact(text: str) -> str:
    for secret in SECRETS:
        text = text.replace(secret, "[redacted]")
    return text


def phase_dir() -> Path:
    path = EVIDENCE / PHASE
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_command(name: str, command: str, output: str, code: int) -> None:
    header = (
        f"label: local\ndate: {now()}\nphase: {PHASE}\ncommand:\n{command}\n"
        f"exit_code: {code}\n---- output ----\n{redact(output)}"
    )
    (phase_dir() / f"{name}.txt").write_text(header)
    with (phase_dir() / "commands.txt").open("a") as handle:
        handle.write(f"{now()} exit={code} {command}\n")


def run(
    command: list[str] | str,
    name: str,
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    check: bool = True,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    display = command if isinstance(command, str) else " ".join(command)
    print(f"[{now()}] {PHASE}: {display}", flush=True)
    result = subprocess.run(
        command,
        cwd=cwd or ROOT,
        env=env,
        input=input_text,
        text=True,
        capture_output=True,
        shell=isinstance(command, str),
        executable="/bin/bash" if isinstance(command, str) else None,
    )
    output = (result.stdout or "") + (result.stderr or "")
    log_command(name, display, output, result.returncode)
    if check and result.returncode != 0:
        tail = redact(output)[-4000:]
        raise RuntimeError(f"{name} failed with exit {result.returncode}\n{tail}")
    return result


def compose_env(image: str, pull: str | None, compose_file: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["COMPOSE_PROJECT_NAME"] = PROJECT
    env["MOSS_IMAGE"] = image
    if pull is None:
        env.pop("MOSS_PULL_POLICY", None)
    else:
        env["MOSS_PULL_POLICY"] = pull
    if compose_file:
        # Same selection the recovery doc uses: base file, then the override.
        env["COMPOSE_FILE"] = f"compose.yaml:{compose_file}"
    else:
        env.pop("COMPOSE_FILE", None)
    env.pop("COMPOSE_PROGRESS", None)
    return env


def read_env_file() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def write_public_env() -> None:
    values = read_env_file()
    for key in ("MOSS_SECRET_KEY", "MOSS_SETUP_TOKEN", "POSTGRES_PASSWORD"):
        remember(values.get(key))
    public = {
        key: values[key]
        for key in (
            "MOSS_ENV",
            "MOSS_SKIP_AUTH",
            "MOSS_USE_SQLITE",
            "MOSS_PUBLIC_URL",
            "MOSS_ORIGINS",
            "MOSS_PORT",
            "POSTGRES_DB",
            "POSTGRES_USER",
        )
        if key in values
    }
    (phase_dir() / "env-public.json").write_text(json.dumps(public, indent=2) + "\n")


def set_env_key(key: str, value: str) -> None:
    path = ROOT / ".env"
    lines = path.read_text().splitlines()
    found = False
    updated = []
    for line in lines:
        if line.startswith(key + "="):
            updated.append(f"{key}={value}")
            found = True
        else:
            updated.append(line)
    if not found:
        updated.append(f"{key}={value}")
    path.write_text("\n".join(updated) + "\n")
    path.chmod(0o600)


def image_id(name: str) -> str:
    result = subprocess.run(
        ["docker", "image", "inspect", name, "--format", "{{.Id}}"],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def remove_project() -> None:
    identifiers = subprocess.run(
        ["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={PROJECT}"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.split()
    if identifiers:
        subprocess.run(["docker", "rm", "-f", *identifiers], check=True, capture_output=True)
    volumes = subprocess.run(
        ["docker", "volume", "ls", "-q", "--filter", f"label=com.docker.compose.project={PROJECT}"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.split()
    if volumes:
        subprocess.run(["docker", "volume", "rm", *volumes], check=True, capture_output=True)
    networks = subprocess.run(
        ["docker", "network", "ls", "-q", "--filter", f"label=com.docker.compose.project={PROJECT}"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.split()
    if networks:
        subprocess.run(["docker", "network", "rm", *networks], check=False, capture_output=True)


def png(width: int = 800, height: int = 400, rgb: tuple[int, int, int] = (180, 40, 48)) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            len(data).to_bytes(4, "big")
            + tag
            + data
            + (zlib.crc32(tag + data) & 0xFFFFFFFF).to_bytes(4, "big")
        )

    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))
    return b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x08\x02\x00\x00\x00"),
            chunk(b"IDAT", zlib.compress(raw, 9)),
            chunk(b"IEND", b""),
        ]
    )


class Cms:
    def __init__(self) -> None:
        context = ssl.create_default_context(cafile=str(TLS_DIR / "rehearsal.crt"))
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=context),
            urllib.request.HTTPCookieProcessor(CookieJar()),
        )
        self.csrf = ""
        self.project = ""

    def request(self, method: str, path: str, body: bytes | None = None, headers: dict[str, str] | None = None):
        request = urllib.request.Request(PUBLIC_URL + path, data=body, method=method)
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        if self.csrf:
            request.add_header("x-moss-csrf", self.csrf)
        if self.project:
            request.add_header("x-moss-project", self.project)
        try:
            with self.opener.open(request, timeout=60) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()

    def json_request(self, method: str, path: str, payload: dict | None = None) -> dict:
        body = None if payload is None else json.dumps(payload).encode()
        headers = {} if body is None else {"content-type": "application/json"}
        status, raw = self.request(method, path, body, headers)
        if status != 200:
            raise RuntimeError(f"{method} {path} -> {status}: {redact(raw.decode()[:1500])}")
        return json.loads(raw)

    def gql(self, query: str, variables: dict | None = None) -> dict:
        body = self.json_request("POST", "/graphql", {"query": query, "variables": variables or {}})
        if body.get("errors"):
            raise RuntimeError(redact(json.dumps(body["errors"])[:1500]))
        return body["data"]


def prepare_tls() -> None:
    TLS_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("body", "proxy", "fastcgi", "uwsgi", "scgi"):
        (TLS_DIR / name).mkdir(exist_ok=True)
    if not (TLS_DIR / "rehearsal.crt").exists():
        run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-keyout",
                str(TLS_DIR / "rehearsal.key"),
                "-out",
                str(TLS_DIR / "rehearsal.crt"),
                "-days",
                "2",
                "-nodes",
                "-subj",
                "/CN=cms.moss.test",
                "-addext",
                "subjectAltName=DNS:cms.moss.test",
            ],
            "openssl",
        )
        os.chmod(TLS_DIR / "rehearsal.key", 0o600)
    hosts = Path("/etc/hosts").read_text()
    if "cms.moss.test" not in hosts:
        run(["sudo", "tee", "-a", "/etc/hosts"], "hosts", input_text="127.0.0.1 cms.moss.test\n")
    if (TLS_DIR / "nginx.pid").exists():
        run(["sudo", "nginx", "-c", str(NGINX_CONF), "-s", "stop"], "nginx-stop", check=False)
    run(["sudo", "nginx", "-t", "-c", str(NGINX_CONF)], "nginx-test")
    run(["sudo", "nginx", "-c", str(NGINX_CONF)], "nginx-start")


def stop_nginx() -> None:
    if (TLS_DIR / "nginx.pid").exists():
        subprocess.run(["sudo", "nginx", "-c", str(NGINX_CONF), "-s", "stop"], check=False, capture_output=True)


def allow_bridge(env: dict[str, str]) -> None:
    network = f"{PROJECT}_default"
    inspect = run(
        ["docker", "network", "inspect", network, "--format", "{{.Id}}"],
        "network-id",
        env=env,
    )
    interface = "br-" + inspect.stdout.strip()[:12]
    policy = run(["sudo", "iptables-legacy", "-S", "FORWARD"], "iptables-forward", check=False)
    listed = run(["sudo", "iptables-legacy", "-S", "DOCKER-FORWARD"], "iptables-docker-forward", check=False)
    rule = ["sudo", "iptables-legacy", "-C", "DOCKER-FORWARD", "-i", interface, "-j", "ACCEPT"]
    present = subprocess.run(rule, capture_output=True)
    (phase_dir() / "iptables-note.txt").write_text(
        f"interface: {interface}\npolicy:\n{policy.stdout}\nDOCKER-FORWARD:\n{listed.stdout}\n"
        f"bridge accept already present: {present.returncode == 0}\n"
    )
    if "-P FORWARD DROP" in policy.stdout and present.returncode != 0:
        run(
            ["sudo", "iptables-legacy", "-A", "DOCKER-FORWARD", "-i", interface, "-j", "ACCEPT"],
            "iptables-accept-bridge",
        )


def wait_ready(env: dict[str, str]) -> None:
    allow_bridge(env)
    deadline = time.time() + 180
    last = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8001/ready", timeout=3) as response:
                body = response.read().decode()
                if response.status == 200 and "ready" in body:
                    (phase_dir() / "ready.body").write_text(body + "\n")
                    return
                last = body
        except Exception as exc:  # noqa: BLE001 - readiness poll
            last = str(exc)
        time.sleep(2)
    logs = run(["docker", "compose", "logs", "--no-color", "--tail", "200", "app"], "app-logs-not-ready", env=env, check=False)
    raise RuntimeError(f"app did not become ready: {last}\n{redact(logs.stdout)[-2000:]}")


def load_content() -> dict:
    values = read_env_file()
    password = WORK_DIR.joinpath("admin-password")
    if not password.exists():
        password.write_text(os.urandom(18).hex())
        password.chmod(0o600)
    admin_password = password.read_text().strip()
    remember(admin_password)
    cms = Cms()
    setup = cms.json_request(
        "POST",
        "/auth/setup",
        {
            "token": values["MOSS_SETUP_TOKEN"],
            "email": "rehearsal-admin@example.com",
            "password": admin_password,
            "name": "Rehearsal Admin",
            "workspaceName": "Upgrade rehearsal",
        },
    )
    cms.csrf = setup["csrf"]
    remember(cms.csrf)
    me = cms.json_request("GET", "/auth/me")
    cms.project = me["projects"][0]["id"]
    fields = [
        {"name": "title", "type": "text", "required": True},
        {"name": "body", "type": "richText"},
        {"name": "secret", "type": "text", "private": True},
    ]
    content_type = cms.gql(
        "mutation($key:String!,$fields:JSON!){saveContentType(key:$key,name:$key,fields:$fields){id key version}}",
        {"key": "note", "fields": fields},
    )["saveContentType"]
    boundary = "moss028boundary"
    image = png()
    body = b"".join(
        [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"rehearsal.png\"\r\n".encode(),
            b"Content-Type: image/png\r\n\r\n",
            image,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    status, raw = cms.request(
        "POST",
        "/api/assets",
        body,
        {"content-type": f"multipart/form-data; boundary={boundary}"},
    )
    if status != 200:
        raise RuntimeError(f"asset upload -> {status}: {redact(raw.decode()[:1500])}")
    asset = json.loads(raw)
    image_sha = hashlib.sha256(image).hexdigest()
    mutation = (
        "mutation($key:String!,$slug:String!,$data:JSON!,$status:String!){"
        "saveEntry(typeKey:$key,slug:$slug,data:$data,status:$status){id slug status version data}"
        "}"
    )
    published = cms.gql(
        mutation,
        {
            "key": "note",
            "slug": "upgrade-rehearsal-note",
            "status": "published",
            "data": {
                "title": "Upgrade rehearsal note",
                "body": f"Loaded before the upgrade. Asset {asset['id']}.",
                "secret": "moss-028-private-marker",
            },
        },
    )["saveEntry"]
    draft = cms.gql(
        mutation,
        {
            "key": "note",
            "slug": "upgrade-rehearsal-draft",
            "status": "draft",
            "data": {
                "title": "Upgrade rehearsal draft",
                "body": "Draft kept across the upgrade.",
                "secret": "moss-028-private-marker",
            },
        },
    )["saveEntry"]
    snapshot = read_entries(cms)
    record = {
        "workspace_id": cms.project,
        "content_type": content_type,
        "asset": {
            "id": asset.get("id"),
            "width": asset.get("width"),
            "height": asset.get("height"),
            "size": asset.get("size"),
            "mime": asset.get("mime"),
            "png_sha256": image_sha,
            "png_bytes": len(image),
        },
        "published": published,
        "draft": draft,
        "entries": snapshot,
    }
    (phase_dir() / "content-loaded.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return record


def read_entries(cms: Cms | None = None) -> list[dict]:
    if cms is None:
        values = read_env_file()
        password = WORK_DIR.joinpath("admin-password").read_text().strip()
        cms = Cms()
        login = cms.json_request(
            "POST",
            "/auth/login",
            {"email": "rehearsal-admin@example.com", "password": password},
        )
        cms.csrf = login["csrf"]
        remember(cms.csrf)
        me = cms.json_request("GET", "/auth/me")
        cms.project = me["projects"][0]["id"]
        del values
    data = cms.gql("{entries{nodes{id slug status version data}}}")
    nodes = data["entries"]["nodes"]
    return sorted(
        [{key: node[key] for key in ("id", "slug", "status", "version", "data")} for node in nodes],
        key=lambda node: node["id"],
    )


def save_json(name: str, payload: object) -> None:
    (phase_dir() / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def psql(env: dict[str, str], sql: str, name: str, database: str | None = None) -> str:
    if database:
        command = [
            "docker",
            "compose",
            "exec",
            "-T",
            "db",
            "sh",
            "-c",
            'psql -U "$POSTGRES_USER" -d "$1" -v ON_ERROR_STOP=1 -tA',
            "sh",
            database,
        ]
    else:
        command = [
            "docker",
            "compose",
            "exec",
            "-T",
            "db",
            "sh",
            "-c",
            'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -tA',
        ]
    result = run(command, name, env=env, input_text=sql)
    return result.stdout


def postgres_fingerprint(env: dict[str, str], name: str, database: str | None = None) -> dict:
    tables = [
        line.strip()
        for line in psql(
            env,
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY 1;",
            f"{name}-tables",
            database,
        ).splitlines()
        if line.strip()
    ]
    recorded = {}
    for table in tables:
        if not table.replace("_", "").isalnum():
            raise RuntimeError(f"unexpected table name {table}")
        line = psql(
            env,
            "SELECT count(*)::text || ' ' || "
            "COALESCE(md5(string_agg(md5(row_to_json(t)::text), '' ORDER BY md5(row_to_json(t)::text))), md5('')) "
            f"FROM {table} t;",
            f"{name}-{table}",
            database,
        ).strip()
        count, digest = line.split()
        recorded[table] = {"rows": int(count), "sha256_standin": digest}
    version = psql(env, "SELECT version_num FROM alembic_version;", f"{name}-alembic", database).strip()
    payload = {"alembic_version": version, "tables": recorded}
    save_json(f"{name}.json", payload)
    return payload


MEDIA_PROGRAM = r"""
import hashlib, json, pathlib, sys
root = pathlib.Path('/data')
skip = set(sys.argv[1:])
files = []
for path in sorted(p for p in root.rglob('*') if p.is_file()):
    rel = str(path.relative_to(root))
    if rel in skip:
        continue
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    files.append({'path': rel, 'sha256': digest, 'bytes': path.stat().st_size})
manifest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
print(json.dumps({'manifest_sha256': manifest, 'files': files}, sort_keys=True))
"""

SQLITE_PROGRAM = r"""
import hashlib, json, sqlite3
con = sqlite3.connect('file:/data/mosscms.db?mode=ro', uri=True)
tables = [row[0] for row in con.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY 1"
)]
recorded = {}
for table in tables:
    cols = [row[1] for row in con.execute(f'PRAGMA table_info("{table}")')]
    rows = []
    for record in con.execute(f'SELECT * FROM "{table}"'):
        payload = {}
        for col, value in zip(cols, record):
            if isinstance(value, bytes):
                payload[col] = {'b': value.hex()}
            else:
                payload[col] = value
        rows.append(hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest())
    rows.sort()
    recorded[table] = {
        'rows': len(rows),
        'sha256': hashlib.sha256(''.join(rows).encode()).hexdigest(),
    }
version = con.execute('SELECT version_num FROM alembic_version').fetchone()[0]
print(json.dumps({'alembic_version': version, 'tables': recorded}, sort_keys=True))
"""


def compose_python(env: dict[str, str], program: str, name: str, args: list[str] | None = None) -> dict:
    result = run(
        [
            "docker",
            "compose",
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "--entrypoint",
            "python",
            "app",
            "-c",
            program,
            *(args or []),
        ],
        name,
        env=env,
    )
    start = result.stdout.find("{")
    end = result.stdout.rfind("}")
    if start < 0 or end < start:
        raise RuntimeError(redact(result.stdout[:1500]))
    return json.loads(result.stdout[start : end + 1])


def newest(directory: Path, suffix: str) -> Path:
    matches = sorted(directory.glob(f"*{suffix}"))
    if not matches:
        raise RuntimeError(f"no *{suffix} in {directory}")
    return matches[-1]


def archive_info(path: Path) -> dict:
    data = path.read_bytes()
    info = {
        "path": str(path),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "gzip": data.startswith(b"\x1f\x8b"),
    }
    if not info["gzip"]:
        info["head"] = data[:180].decode("utf-8", errors="replace")
    return info


def gzip_test(path: Path, name: str) -> int:
    result = run(["gzip", "-t", str(path)], name, check=False)
    return result.returncode


def configure(sqlite: bool) -> None:
    command = [
        "python3",
        "scripts/configure.py",
        "--production",
        "--public-url",
        PUBLIC_URL,
    ]
    if sqlite:
        command.append("--sqlite")
    run(command, "configure")
    write_public_env()


def start_app(env: dict[str, str], name: str, extra: list[str] | None = None) -> None:
    run(["docker", "compose", "up", "-d", "--no-build", *(extra or [])], name, env=env)
    wait_ready(env)


def stop_writers(env: dict[str, str]) -> None:
    run(["docker", "compose", "stop", "app"], "stop-app", env=env)


def assert_image_unchanged(before: str, name: str) -> None:
    after = image_id(name)
    if after != before:
        raise RuntimeError(f"{name} changed from {before} to {after}")


# Session rows, the outbox claim, and migration bookkeeping are not editorial content.
# The upgrade worker marks an existing publication event processed; the entry payload stays.
OPERATIONAL_TABLES = {
    "alembic_version",
    "entry_field_indexes",
    "publication_events",
    "audit",
    "tokens",
    "webhook_deliveries",
}


def content_tables(snapshot: dict) -> dict:
    return {key: value for key, value in snapshot["tables"].items() if key not in OPERATIONAL_TABLES}


def same_entries(left: list[dict], right: list[dict]) -> None:
    if left != right:
        raise RuntimeError("editorial entries differ\n" + json.dumps({"before": left, "after": right}, indent=2)[:4000])


def probe_postgres_backup(old_before: str) -> dict:
    run(["docker", "image", "tag", old_before, PROBE_IMAGE], "tag-probe")
    probe_before = image_id(PROBE_IMAGE)
    directory = WORK_DIR / "probe-postgres"
    shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(parents=True)
    env = compose_env(PROBE_IMAGE, None)
    run(["python3", "scripts/backup.py", "--directory", str(directory)], "probe-backup", env=env, check=False)
    media = newest(directory, ".media.tar.gz")
    dump = newest(directory, ".dump")
    info = {"media": archive_info(media), "dump": archive_info(dump), "gzip_media_exit": gzip_test(media, "probe-gzip")}
    info["probe_image_before"] = probe_before
    info["probe_image_after"] = image_id(PROBE_IMAGE)
    info["old_image_after"] = image_id(OLD_IMAGE)
    info["media_is_gzip"] = info["media"]["gzip"]
    info["probe_image_rebuilt"] = info["probe_image_after"] != probe_before
    info["old_image_preserved"] = info["old_image_after"] == old_before
    save_json("probe-backup.json", info)
    if info["media_is_gzip"] or not info["probe_image_rebuilt"] or not info["old_image_preserved"]:
        raise RuntimeError(f"documented backup probe did not fail as expected: {json.dumps(info)[:2000]}")
    return info


def real_postgres_backup(env: dict[str, str], old_before: str) -> dict:
    directory = WORK_DIR / "backup-postgres"
    shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(parents=True)
    run(["python3", "scripts/backup.py", "--directory", str(directory)], "backup", env=env)
    assert_image_unchanged(old_before, OLD_IMAGE)
    media = newest(directory, ".media.tar.gz")
    dump = newest(directory, ".dump")
    info = {
        "media": archive_info(media),
        "dump": archive_info(dump),
        "gzip_media_exit": gzip_test(media, "backup-gzip"),
        "image_id": image_id(OLD_IMAGE),
    }
    if info["gzip_media_exit"] != 0 or not info["media"]["gzip"]:
        raise RuntimeError("corrected backup did not write a gzip media archive")
    listed = subprocess.run(
        ["docker", "run", "--rm", "-i", "postgres:17-alpine", "pg_restore", "-l"],
        input=dump.read_bytes(),
        capture_output=True,
    )
    (phase_dir() / "dump-list.txt").write_text(redact(listed.stderr.decode() + listed.stdout.decode()))
    if listed.returncode != 0:
        raise RuntimeError("pg_restore -l rejected the corrected dump")
    info["dump_restore_list_exit"] = listed.returncode
    save_json("backup.json", info)
    return {"dump": dump, "media": media, "info": info}


def write_override(image: str, volume: str, filename: str) -> str:
    text = (
        "services:\n"
        "  app:\n"
        f"    image: {image}\n"
        "    pull_policy: never\n"
        "    volumes: !override\n"
        f"      - {volume}:/data\n"
        "volumes:\n"
        f"  {volume}:\n"
    )
    path = EVIDENCE / "rehearsal" / filename
    path.write_text(text)
    return str(path.relative_to(ROOT))


def run_postgres() -> dict:
    global PHASE
    PHASE = "postgres"
    remove_project()
    env_path = ROOT / ".env"
    if env_path.exists():
        env_path.unlink()
    configure(False)
    old_before = image_id(OLD_IMAGE)
    env = compose_env(OLD_IMAGE, "never")
    start_app(env, "up")
    (phase_dir() / "image-id.txt").write_text(old_before + "\n")
    loaded = load_content()
    stop_writers(env)
    probe = probe_postgres_backup(old_before)
    backup_env = compose_env(OLD_IMAGE, "never")
    backup = real_postgres_backup(backup_env, old_before)
    before = postgres_fingerprint(backup_env, "checksum-before")
    before_media = compose_python(backup_env, MEDIA_PROGRAM, "media-before")
    save_json("media-before.json", before_media)
    if before["alembic_version"] != "0009":
        raise RuntimeError(f"old image left revision {before['alembic_version']}")
    stamp = backup["info"]["media"]["path"].rsplit("/", 1)[-1].replace(".media.tar.gz", "")
    backup_tag = f"mosscms:backup-{stamp}"
    run(["docker", "image", "tag", old_before, backup_tag], "tag-backup")
    upgrade_env = compose_env(NEW_IMAGE, "never")
    start_app(upgrade_env, "upgrade-up", ["--no-deps", "--force-recreate", "app"])
    run(
        ["docker", "compose", "logs", "--no-color", "--tail", "400", "app"],
        "upgrade-logs",
        env=upgrade_env,
        check=False,
    )
    after = postgres_fingerprint(upgrade_env, "checksum-after-upgrade")
    after_media = compose_python(upgrade_env, MEDIA_PROGRAM, "media-after-upgrade")
    save_json("media-after-upgrade.json", after_media)
    if after["alembic_version"] != "0014":
        raise RuntimeError(f"upgrade left revision {after['alembic_version']}")
    if content_tables(before) != {key: after["tables"][key] for key in content_tables(before)}:
        raise RuntimeError("upgrade changed stored content rows")
    if before_media != after_media:
        raise RuntimeError("upgrade changed media bytes")
    if "entry_field_indexes" not in after["tables"]:
        raise RuntimeError("upgrade did not create entry_field_indexes")
    upgraded_entries = read_entries()
    save_json("entries-after-upgrade.json", upgraded_entries)
    same_entries(loaded["entries"], upgraded_entries)
    stop_writers(upgrade_env)
    run(
        ["docker", "compose", "exec", "-T", "db", "sh", "-c", 'createdb -U "$POSTGRES_USER" mosscms_recovery'],
        "createdb",
        env=upgrade_env,
    )
    run(
        [
            "python3",
            "scripts/restore.py",
            str(backup["dump"]),
            "--target",
            "mosscms_recovery",
            "--confirm-target",
            "mosscms_recovery",
        ],
        "restore-db",
        env=upgrade_env,
    )
    override = write_override(backup_tag, "recovered_assets", "recovery.compose.yaml")
    restore_env = compose_env(backup_tag, "never", override)
    retained_before = image_id(backup_tag)
    run(
        ["python3", "scripts/restore_media.py", str(backup["media"]), "--confirm-empty-volume"],
        "restore-media",
        env=restore_env,
    )
    refused = run(
        ["python3", "scripts/restore_media.py", str(backup["media"]), "--confirm-empty-volume"],
        "restore-media-refused",
        env=restore_env,
        check=False,
    )
    if refused.returncode == 0:
        raise RuntimeError("second media restore was accepted")
    assert_image_unchanged(retained_before, backup_tag)
    restored = postgres_fingerprint(upgrade_env, "checksum-restored-before-start", "mosscms_recovery")
    if restored != before:
        raise RuntimeError("restored database differs from the pre-upgrade database")
    set_env_key("POSTGRES_DB", "mosscms_recovery")
    start_app(restore_env, "rollback-up", ["--no-deps", "app"])
    container_id = run(["docker", "compose", "ps", "-q", "app"], "rollback-container-id", env=restore_env).stdout.strip()
    container_image = run(
        ["docker", "inspect", "--format", "{{.Image}}", container_id],
        "rollback-container-image",
        env=restore_env,
    ).stdout.strip()
    if container_image != retained_before:
        raise RuntimeError(f"rollback container image {container_image} is not {retained_before}")
    rolled = postgres_fingerprint(restore_env, "checksum-after-rollback", "mosscms_recovery")
    rolled_media = compose_python(restore_env, MEDIA_PROGRAM, "media-after-rollback")
    save_json("media-after-rollback.json", rolled_media)
    rolled_entries = read_entries()
    save_json("entries-after-rollback.json", rolled_entries)
    same_entries(loaded["entries"], rolled_entries)
    stop_writers(restore_env)
    original = postgres_fingerprint(restore_env, "checksum-upgraded-db-still", "mosscms")
    if content_tables(rolled) != content_tables(before):
        raise RuntimeError("rollback changed stored content rows")
    if rolled_media != before_media:
        raise RuntimeError("rollback media checksum differs from the pre-upgrade media")
    if original["alembic_version"] != "0014":
        raise RuntimeError("upgraded database revision changed during rollback")
    result = {
        "engine": "postgresql",
        "old_image": OLD_IMAGE,
        "old_image_id": old_before,
        "new_image": NEW_IMAGE,
        "new_image_id": image_id(NEW_IMAGE),
        "backup_image": backup_tag,
        "backup_image_id": retained_before,
        "revision_before": before["alembic_version"],
        "revision_after_upgrade": after["alembic_version"],
        "revision_after_rollback": rolled["alembic_version"],
        "upgraded_database_revision_after_rollback": original["alembic_version"],
        "restored_database_equals_pre_upgrade": True,
        "content_checksum_equal_after_rollback": content_tables(rolled) == content_tables(before),
        "media_checksum_equal_after_rollback": rolled_media == before_media,
        "entries_equal": True,
        "probe_media_is_gzip": probe["media_is_gzip"],
        "probe_rebuilt_image": probe["probe_image_rebuilt"],
        "backup": backup["info"],
        "table_rows_before": {key: value["rows"] for key, value in before["tables"].items()},
    }
    save_json("result.json", result)
    return result


def sqlite_tar(env: dict[str, str], directory: Path, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = directory / f"{stamp}.sqlite-data.tar.gz"
    command = (
        "docker compose run --rm --no-deps -T --entrypoint tar app -C /data -czf - . "
        f"> {target}"
    )
    run(command, name, env=env)
    return target


def run_sqlite() -> dict:
    global PHASE
    PHASE = "sqlite"
    remove_project()
    configure(True)
    old_before = image_id(OLD_IMAGE)
    env = compose_env(OLD_IMAGE, "never")
    start_app(env, "up")
    loaded = load_content()
    stop_writers(env)
    run(["docker", "image", "tag", old_before, PROBE_IMAGE], "tag-probe")
    probe_before = image_id(PROBE_IMAGE)
    probe_env = compose_env(PROBE_IMAGE, None)
    probe_archive = sqlite_tar(probe_env, WORK_DIR / "probe-sqlite", "probe-tar")
    probe = {
        "archive": archive_info(probe_archive),
        "gzip_exit": gzip_test(probe_archive, "probe-gzip"),
        "probe_image_before": probe_before,
        "probe_image_after": image_id(PROBE_IMAGE),
        "old_image_after": image_id(OLD_IMAGE),
    }
    probe["media_is_gzip"] = probe["archive"]["gzip"]
    probe["probe_image_rebuilt"] = probe["probe_image_after"] != probe_before
    probe["old_image_preserved"] = probe["old_image_after"] == old_before
    save_json("probe-tar.json", probe)
    if probe["media_is_gzip"] or not probe["probe_image_rebuilt"] or not probe["old_image_preserved"]:
        raise RuntimeError(f"documented sqlite archive probe did not fail as expected: {json.dumps(probe)[:2000]}")
    backup_env = compose_env(OLD_IMAGE, "never")
    archive = sqlite_tar(backup_env, WORK_DIR / "backup-sqlite", "backup-tar")
    assert_image_unchanged(old_before, OLD_IMAGE)
    info = archive_info(archive)
    if gzip_test(archive, "backup-gzip") != 0:
        raise RuntimeError("corrected sqlite archive failed gzip -t")
    save_json("backup.json", info)
    before = compose_python(backup_env, SQLITE_PROGRAM, "checksum-before")
    before_media = compose_python(
        backup_env, MEDIA_PROGRAM, "media-before", ["mosscms.db", "mosscms.db-wal", "mosscms.db-shm"]
    )
    save_json("checksum-before.json", before)
    save_json("media-before.json", before_media)
    if before["alembic_version"] != "0009":
        raise RuntimeError(f"sqlite old image left revision {before['alembic_version']}")
    stamp = archive.name.replace(".sqlite-data.tar.gz", "")
    backup_tag = f"mosscms:backup-sqlite-{stamp}"
    run(["docker", "image", "tag", old_before, backup_tag], "tag-backup")
    upgrade_env = compose_env(NEW_IMAGE, "never")
    start_app(upgrade_env, "upgrade-up", ["--force-recreate"])
    run(["docker", "compose", "logs", "--no-color", "--tail", "400", "app"], "upgrade-logs", env=upgrade_env, check=False)
    after = compose_python(upgrade_env, SQLITE_PROGRAM, "checksum-after-upgrade")
    after_media = compose_python(
        upgrade_env, MEDIA_PROGRAM, "media-after-upgrade", ["mosscms.db", "mosscms.db-wal", "mosscms.db-shm"]
    )
    save_json("checksum-after-upgrade.json", after)
    save_json("media-after-upgrade.json", after_media)
    if after["alembic_version"] != "0014":
        raise RuntimeError(f"sqlite upgrade left revision {after['alembic_version']}")
    if content_tables(before) != {key: after["tables"][key] for key in content_tables(before)}:
        raise RuntimeError("sqlite upgrade changed stored content rows")
    if before_media != after_media:
        raise RuntimeError("sqlite upgrade changed media bytes")
    upgraded_entries = read_entries()
    save_json("entries-after-upgrade.json", upgraded_entries)
    same_entries(loaded["entries"], upgraded_entries)
    stop_writers(upgrade_env)
    override = write_override(backup_tag, "sqlite_recovered_assets", "sqlite-recovery.compose.yaml")
    restore_env = compose_env(backup_tag, "never", override)
    retained_before = image_id(backup_tag)
    run(
        ["python3", "scripts/restore_media.py", str(archive), "--confirm-empty-volume"],
        "restore-media",
        env=restore_env,
    )
    refused = run(
        ["python3", "scripts/restore_media.py", str(archive), "--confirm-empty-volume"],
        "restore-media-refused",
        env=restore_env,
        check=False,
    )
    if refused.returncode == 0:
        raise RuntimeError("second sqlite restore was accepted")
    assert_image_unchanged(retained_before, backup_tag)
    restored = compose_python(restore_env, SQLITE_PROGRAM, "checksum-restored-before-start")
    save_json("checksum-restored-before-start.json", restored)
    if restored != before:
        raise RuntimeError("restored sqlite database differs from the pre-upgrade database")
    start_app(restore_env, "rollback-up", ["--no-deps", "app"])
    rolled = compose_python(restore_env, SQLITE_PROGRAM, "checksum-after-rollback")
    rolled_media = compose_python(
        restore_env, MEDIA_PROGRAM, "media-after-rollback", ["mosscms.db", "mosscms.db-wal", "mosscms.db-shm"]
    )
    save_json("checksum-after-rollback.json", rolled)
    save_json("media-after-rollback.json", rolled_media)
    rolled_entries = read_entries()
    save_json("entries-after-rollback.json", rolled_entries)
    same_entries(loaded["entries"], rolled_entries)
    stop_writers(restore_env)
    if content_tables(rolled) != content_tables(before):
        raise RuntimeError("sqlite rollback changed stored content rows")
    if rolled_media != before_media:
        raise RuntimeError("sqlite rollback media checksum differs")
    original_volume = subprocess.run(
        ["docker", "volume", "ls", "-q", "--filter", f"label=com.docker.compose.project={PROJECT}"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.split()
    save_json("volumes.json", original_volume)
    result = {
        "engine": "sqlite",
        "old_image_id": old_before,
        "backup_image": backup_tag,
        "backup_image_id": retained_before,
        "revision_before": before["alembic_version"],
        "revision_after_upgrade": after["alembic_version"],
        "revision_after_rollback": rolled["alembic_version"],
        "restored_database_equals_pre_upgrade": True,
        "content_checksum_equal_after_rollback": content_tables(rolled) == content_tables(before),
        "media_checksum_equal_after_rollback": rolled_media == before_media,
        "entries_equal": True,
        "probe_media_is_gzip": probe["media_is_gzip"],
        "probe_rebuilt_image": probe["probe_image_rebuilt"],
        "backup": info,
        "table_rows_before": {key: value["rows"] for key, value in before["tables"].items()},
    }
    save_json("result.json", result)
    return result


def copy_build_log() -> None:
    target = EVIDENCE / "rehearsal" / "image-build.txt"
    header = (
        "label: local\n"
        f"date: {now()}\n"
        "command:\n"
        "docker build --tag mosscms:moss028-1d6d0ef /tmp/moss028-old\n"
        "docker build --tag mosscms:moss028-58a0f15 /agent/repos/MossCMS\n"
        "---- output ----\n"
    )
    target.write_text(header + BUILD_LOG.read_text(errors="replace"))


def record_context() -> None:
    global PHASE
    PHASE = "rehearsal"
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    versions = subprocess.check_output(
        "docker version --format '{{.Server.Version}}' && docker compose version && nginx -v",
        shell=True,
        executable="/bin/bash",
        text=True,
        stderr=subprocess.STDOUT,
    )
    text = (
        f"label: local\ndate: {now()}\nhead: {sha}\nold_sha: {OLD_SHA}\n"
        f"old_image: {OLD_IMAGE}\nnew_image: {NEW_IMAGE}\n"
        f"git status --porcelain:\n{status}\n---- versions ----\n{versions}\n"
    )
    (phase_dir() / "context.txt").write_text(text)
    copy_build_log()
    migrations = {}
    for image in (OLD_IMAGE, NEW_IMAGE):
        listed = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "python",
                image,
                "-c",
                "import pathlib; print('\\n'.join(sorted(p.name for p in pathlib.Path('migrations/versions').glob('*.py'))))",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        migrations[image] = [line for line in listed.stdout.splitlines() if line]
        (phase_dir() / f"migrations-{image.split(':', 1)[1]}.txt").write_text(listed.stdout)
    if "0010_delivery_page_index.py" in migrations[OLD_IMAGE]:
        raise RuntimeError("old image already contains a later migration")
    if "0014_substring_search.py" not in migrations[NEW_IMAGE]:
        raise RuntimeError("new image is missing 0014")


def scan_secrets() -> None:
    leaked = []
    for path in EVIDENCE.rglob("*"):
        if not path.is_file() or path.suffix in {".png", ".gz", ".dump"}:
            continue
        text = path.read_text(errors="ignore")
        for secret in SECRETS:
            if secret in text:
                leaked.append(str(path.relative_to(ROOT)))
                break
    if leaked:
        raise RuntimeError("secret leaked into " + ", ".join(leaked))


def main() -> None:
    os.umask(0o077)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    record_context()
    prepare_tls()
    postgres = run_postgres()
    sqlite = run_sqlite()
    summary = {"date": now(), "postgres": postgres, "sqlite": sqlite, "label": "local"}
    (EVIDENCE / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    scan_secrets()
    stop_nginx()
    remove_project()
    env_file = ROOT / ".env"
    if env_file.exists():
        env_file.unlink()
    print(json.dumps({"ok": True, "summary": str(EVIDENCE / "summary.json")}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        stop_nginx()
        raise
