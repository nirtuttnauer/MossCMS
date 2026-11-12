"""X-Forwarded-For and Forwarded do not choose the rate-limit key or the audit client."""

import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx
from sqlalchemy import select

from app.models import Audit

API = Path(__file__).resolve().parents[1]
EMAIL = "peer-admin@example.com"
PASSWORD = "secure-test-password"
SPOOF = "203.0.113.50"


def _spoof(host):
    return {"X-Forwarded-For": host, "Forwarded": f"for={host}"}


def test_testclient_keeps_the_peer_for_limits_and_audit(client, app):
    setup = client.post(
        "/auth/setup",
        json={"token": "t" * 30, "email": EMAIL, "password": PASSWORD, "name": "Peer"},
        headers=_spoof(SPOOF),
    )
    assert setup.status_code == 200, setup.text
    logged_in = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=_spoof(SPOOF))
    assert logged_in.status_code == 200, logged_in.text
    with app.state.db() as session:
        row = session.scalar(select(Audit).where(Audit.action == "account.login"))
    assert row.details["client"] == "testclient"
    assert SPOOF not in json.dumps(row.details)

    for index in range(7):
        failed = client.post(
            "/auth/login",
            json={"email": EMAIL, "password": "wrong-password-value"},
            headers=_spoof(f"203.0.113.{index}"),
        )
        assert failed.status_code == 401, failed.text
    blocked = client.post(
        "/auth/login",
        json={"email": EMAIL, "password": "wrong-password-value"},
        headers=_spoof("198.51.100.8"),
    )
    assert blocked.status_code == 429, blocked.text

    health = client.get("/health", headers=_spoof("198.51.100.9"))
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert "203.0.113" not in health.text
    assert "198.51.100" not in health.text


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_serve_ignores_forwarded_headers_from_a_trusted_peer(tmp_path):
    """Uvicorn would trust X-Forwarded-For from 127.0.0.1 unless proxy headers are off."""
    port = _free_port()
    env = os.environ.copy()
    env.update(
        {
            "PORT": str(port),
            "MOSS_USE_SQLITE": "true",
            "MOSS_STORAGE_DIR": str(tmp_path),
            "MOSS_SECRET_KEY": "s" * 40,
            "MOSS_SETUP_TOKEN": "t" * 30,
            "MOSS_ENV": "development",
            "MOSS_SKIP_AUTH": "false",
            "FORWARDED_ALLOW_IPS": "*",
        }
    )
    for name in ("DATABASE_URL", "POSTGRES_HOST", "MOSS_TEST_DATABASE_URL"):
        env.pop(name, None)
    log = tmp_path / "serve.log"
    with log.open("w") as handle:
        process = subprocess.Popen(
            [sys.executable, "-m", "app.cli", "serve"],
            cwd=API,
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
    try:
        deadline = time.monotonic() + 40
        health = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError(log.read_text()[-4000:])
            try:
                health = httpx.get(f"http://127.0.0.1:{port}/health", headers=_spoof(SPOOF), timeout=1)
                if health.status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        else:
            raise AssertionError(log.read_text()[-4000:])
        assert health.json() == {"status": "ok"}
        body = health.text.lower()
        for needle in ("version", "sqlite", "postgres", "secret", "database", "0.2.0"):
            assert needle not in body

        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as http:
            setup = http.post(
                "/auth/setup",
                json={"token": "t" * 30, "email": EMAIL, "password": PASSWORD, "name": "Peer"},
                headers=_spoof(SPOOF),
            )
            assert setup.status_code == 200, setup.text
            logged_in = http.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}, headers=_spoof(SPOOF))
            assert logged_in.status_code == 200, logged_in.text
            for index in range(7):
                failed = http.post(
                    "/auth/login",
                    json={"email": EMAIL, "password": "wrong-password-value"},
                    headers=_spoof(f"198.51.100.{index}"),
                )
                assert failed.status_code == 401, failed.text
            blocked = http.post(
                "/auth/login",
                json={"email": EMAIL, "password": "wrong-password-value"},
                headers=_spoof("203.0.113.77"),
            )
            assert blocked.status_code == 429, blocked.text

        details = json.loads(
            sqlite3.connect(tmp_path / "mosscms.db")
            .execute("select details from audit where action = 'account.login'")
            .fetchone()[0]
        )
        assert details["client"] == "127.0.0.1"
        assert "203.0.113" not in json.dumps(details)
        assert "198.51.100" not in json.dumps(details)
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
