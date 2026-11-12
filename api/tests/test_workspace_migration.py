import json
import os
import tempfile
import uuid
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models import Asset, Entry, Membership, Project, User
from app.workspace_migration import _signer
from conftest import define, entry


def bundle(client, admin):
    define(client, admin)
    entry(client, admin, status="published")
    asset = client.post("/api/assets", headers=admin, files={"file": ("note.txt", b"media bytes", "text/plain")})
    assert asset.status_code == 200
    result = client.post("/api/migration/export", headers=admin, data={"history": "true"})
    assert result.status_code == 200, result.text
    assert result.headers["content-type"] == "application/zip"
    assert result.headers["cache-control"] == "no-store"
    assert "attachment" in result.headers["content-disposition"]
    return result.content


def destination(app, admin):
    with app.state.db.begin() as session:
        project = Project(name="Imported workspace")
        session.add(project)
        session.flush()
        user = session.scalar(select(User).where(User.email == "admin@example.com"))
        session.add(Membership(project_id=project.id, user_id=user.id, role="admin"))
        return {**admin, "x-moss-project": project.id}


def preview(client, headers, archive, filename="workspace.zip", **fields):
    return client.post(
        "/api/migration/import",
        headers=headers,
        files={"file": (filename, archive, "application/zip")},
        data=fields,
    )


def _plant(label):
    path = Path(tempfile.gettempdir()) / f"moss080-{uuid.uuid4().hex}-{label}"
    path.write_bytes(b"OUTSIDE-SECRET")
    return path


def _member_name(kind, outside):
    name = outside.name
    if kind == "dotdot":
        return f"../{name}"
    if kind == "absolute":
        return outside.as_posix()
    if kind == "encoded-dotdot":
        return f"%2e%2e/%2e%2e/{name}"
    if kind == "encoded-slash":
        return f"..%2f..%2f{name}"
    if kind == "double-encoded":
        return f"%252e%252e/%252e%252e/{name}"
    if kind == "backslash":
        return "..\\" + name
    raise AssertionError(kind)


def _hostile(member):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", b"{}")
        archive.writestr(member, b"from-archive")
    return buffer.getvalue()


TRAVERSAL = ["dotdot", "absolute", "encoded-dotdot", "encoded-slash", "double-encoded", "backslash"]


def test_browser_export_validate_import_and_retry(client, admin, app):
    archive = bundle(client, admin)
    with zipfile.ZipFile(BytesIO(archive)) as file:
        assert b"hidden" not in file.read("entries.ndjson")
        assert b"media bytes" in b"".join(file.read(n) for n in file.namelist() if n.startswith("assets/"))
    target = destination(app, admin)
    response = preview(client, target, archive)
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["applied"] is False
    assert report["sourceSchemas"][0]["key"] == "article"
    assert report["validation"]
    with app.state.db() as session:
        assert (
            session.scalar(select(func.count()).select_from(Entry).where(Entry.project_id == target["x-moss-project"]))
            == 0
        )
        assert (
            session.scalar(select(func.count()).select_from(Asset).where(Asset.project_id == target["x-moss-project"]))
            == 0
        )
    response = preview(client, target, archive, apply="true", validation=report["validation"])
    assert response.status_code == 200, response.text
    assert response.json()["applied"] is True
    response = preview(client, target, archive, apply="true", validation=report["validation"])
    assert response.status_code == 200, response.text
    assert response.json()["alreadyImported"] is True
    with app.state.db() as session:
        record = session.scalar(select(Entry).where(Entry.project_id == target["x-moss-project"]))
        assert record.status == "draft"
        assert record.published_data is None
        assert record.scheduled_at is None


def test_apply_requires_review_of_same_archive_pipeline_workspace_and_user(client, admin, app):
    archive = bundle(client, admin)
    target = destination(app, admin)
    report = preview(client, target, archive).json()
    assert preview(client, target, archive, apply="true").status_code == 409
    assert preview(client, target, archive, apply="true", validation=report["validation"] + "tamper").status_code == 409
    pipeline = json.dumps({"steps": [{"op": "drop", "path": "body"}]})
    response = preview(client, target, archive, apply="true", validation=report["validation"], pipeline=pipeline)
    assert response.status_code == 409, response.text
    with zipfile.ZipFile(BytesIO(archive)) as original:
        changed = BytesIO()
        with zipfile.ZipFile(changed, "w", compression=zipfile.ZIP_DEFLATED) as file:
            for name in original.namelist():
                file.writestr(name, original.read(name))
    assert preview(client, target, changed.getvalue(), apply="true", validation=report["validation"]).status_code == 409
    other = destination(app, admin)
    assert preview(client, other, archive, apply="true", validation=report["validation"]).status_code == 403
    claim = _signer(app.state.settings).dumps(
        {"project": target["x-moss-project"], "user": "another-user", "importKey": report["importKey"]}
    )
    assert preview(client, target, archive, apply="true", validation=claim).status_code == 403


@pytest.mark.parametrize("role", ["editor", "reader"])
def test_migration_endpoints_require_admin_membership(client, admin, app, role):
    with app.state.db.begin() as session:
        user = session.scalar(select(User).where(User.email == "admin@example.com"))
        session.get(Membership, (admin["x-moss-project"], user.id)).role = role
    assert client.get("/api/migration/limits", headers=admin).status_code == 403
    assert client.post("/api/migration/export", headers=admin).status_code == 403
    assert preview(client, admin, b"invalid").status_code == 403


def test_csrf_body_limits_and_invalid_archive_errors(client, admin, monkeypatch):
    import app.workspace_migration as migration

    missing = {"x-moss-project": admin["x-moss-project"]}
    assert client.post("/api/migration/export", headers=missing).status_code == 403
    assert preview(client, missing, b"bad").status_code == 403
    assert preview(client, admin, b"not a ZIP").status_code == 422
    assert preview(client, admin, b"").status_code == 422
    limits = client.get("/api/migration/limits", headers=admin).json()
    assert limits["archiveBytes"] == 64 * 1024 * 1024
    monkeypatch.setattr(migration, "MAX_ARCHIVE_UPLOAD", 4)
    assert preview(client, admin, b"longer than limit").status_code == 413
    monkeypatch.setattr(migration, "MAX_PIPELINE_BYTES", 4)
    assert preview(client, admin, b"bad", pipeline='{"steps":[]}').status_code == 413


def test_local_development_admin_can_export_without_persistent_membership(client, admin, app):
    from app.development import initialize_development

    initialize_development(app.state.db)
    app.state.settings.skip_auth = True
    headers = {"x-moss-project": admin["x-moss-project"], "x-moss-csrf": app.state.development_csrf}
    assert client.post("/api/migration/export", headers=headers).status_code == 200


def _reject_archive_routes(http, headers, archive):
    limits = http.get("/api/migration/limits", headers=headers)
    assert limits.status_code == 401
    assert limits.json()["detail"] == "Sign in required."
    exported = http.post("/api/migration/export", headers=headers)
    assert exported.status_code == 401
    assert exported.json()["detail"] == "Sign in required."
    uploaded = preview(http, headers, archive)
    assert uploaded.status_code == 401
    assert uploaded.json()["detail"] == "Sign in required."
    assert b"OUTSIDE-SECRET" not in limits.content + exported.content + uploaded.content


def test_missing_session_and_delivery_token_cannot_download_or_upload(client, admin, app):
    issued = client.post("/api/tokens", headers=admin, json={"name": "site", "scopes": [], "days": 1})
    assert issued.status_code == 200, issued.text
    token = issued.json()["token"]
    project = {"x-moss-project": admin["x-moss-project"]}
    session_cookie = client.cookies.get("moss_session")
    assert session_cookie
    client.cookies.clear()
    try:
        _reject_archive_routes(client, {}, b"not a zip")
        _reject_archive_routes(client, project, b"not a zip")
        _reject_archive_routes(client, {**project, "Authorization": "Bearer " + token}, b"not a zip")
        client.cookies.set("moss_session", token)
        _reject_archive_routes(client, project, b"not a zip")
    finally:
        client.cookies.clear()
        client.cookies.set("moss_session", session_cookie)
    assert client.get("/api/migration/limits", headers=admin).status_code == 200


@pytest.mark.parametrize("kind", TRAVERSAL)
def test_archive_member_traversal_stays_inside_the_archive_directory(client, admin, kind):
    outside = _plant(kind)
    deeper = Path("/") / outside.name
    member = _member_name(kind, outside)
    try:
        response = preview(client, admin, _hostile(member))
        assert response.status_code == 422, response.text
        assert b"from-archive" not in response.content
        assert b"OUTSIDE-SECRET" not in response.content
        assert outside.read_bytes() == b"OUTSIDE-SECRET"
        assert not deeper.exists()
    finally:
        outside.unlink(missing_ok=True)
        if deeper.is_file():
            deeper.unlink()


@pytest.mark.parametrize("kind", TRAVERSAL)
def test_upload_filename_traversal_does_not_write_outside(client, admin, app, kind):
    outside = _plant(kind)
    deeper = Path("/") / outside.name
    archive = bundle(client, admin)
    target = destination(app, admin)
    try:
        response = preview(client, target, archive, filename=_member_name(kind, outside))
        assert response.status_code == 200, response.text
        assert response.json()["applied"] is False
        assert outside.read_bytes() == b"OUTSIDE-SECRET"
        assert not deeper.exists()
        assert b"OUTSIDE-SECRET" not in response.content
    finally:
        outside.unlink(missing_ok=True)
        if deeper.is_file():
            deeper.unlink()


@pytest.mark.parametrize("kind", ["dotdot", "absolute"])
def test_export_does_not_read_outside_the_media_directory(client, admin, app, tmp_path, kind):
    define(client, admin)
    created = entry(client, admin, status="published")
    assert "errors" not in created, created
    uploaded = client.post("/api/assets", headers=admin, files={"file": ("note.txt", b"media bytes", "text/plain")})
    assert uploaded.status_code == 200, uploaded.text
    secret = tmp_path / "secret.bin"
    secret.write_bytes(b"OUTSIDE-SECRET")
    storage = app.state.settings.storage_dir.resolve()
    relative = Path(os.path.relpath(secret, storage)).as_posix()
    assert relative.startswith("../")
    key = relative if kind == "dotdot" else secret.as_posix()
    with app.state.db.begin() as session:
        asset = session.scalar(select(Asset).where(Asset.project_id == admin["x-moss-project"]))
        asset.key = key
    response = client.post("/api/migration/export", headers=admin)
    assert response.status_code == 422, response.text
    assert b"OUTSIDE-SECRET" not in response.content
    assert secret.read_bytes() == b"OUTSIDE-SECRET"


def test_hebrew_names_and_content_round_trip(client, admin, app):
    define(client, admin)
    saved = entry(
        client,
        admin,
        slug="מדריך-התקנה",
        data={"title": "שלום עולם", "body": "תוכן בעברית", "secret": "סודי"},
        status="published",
    )
    assert "errors" not in saved, saved
    uploaded = client.post(
        "/api/assets",
        headers=admin,
        files={"file": ("שלום.txt", "תוכן הקובץ".encode(), "text/plain")},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["name"] == "שלום.txt"
    with app.state.db.begin() as session:
        session.get(Project, admin["x-moss-project"]).name = "סטודיו"
    exported = client.post("/api/migration/export", headers=admin, data={"history": "true"})
    assert exported.status_code == 200, exported.text
    assert exported.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(BytesIO(exported.content)) as archive:
        entries = archive.read("entries.ndjson")
        assets = archive.read("assets.ndjson")
        manifest = archive.read("manifest.json")
        blobs = b"".join(archive.read(name) for name in archive.namelist() if name.startswith("assets/"))
    assert "שלום עולם".encode() in entries
    assert "תוכן בעברית".encode() in entries
    assert "מדריך-התקנה".encode() in entries
    assert "סודי".encode() not in entries
    assert "שלום.txt".encode() in assets
    assert "תוכן הקובץ".encode() in blobs
    assert "סטודיו".encode() in manifest
    rejected = BytesIO()
    with zipfile.ZipFile(rejected, "w") as archive:
        archive.writestr("manifest.json", b"{}")
        archive.writestr("שלום.txt", "תוכן".encode())
    hebrew_member = preview(client, admin, rejected.getvalue(), filename="ארכיון-שלום.zip")
    assert hebrew_member.status_code == 422, hebrew_member.text
    target = destination(app, admin)
    checked = preview(client, target, exported.content, filename="ארכיון-שלום.zip")
    assert checked.status_code == 200, checked.text
    applied = preview(
        client,
        target,
        exported.content,
        filename="ארכיון-שלום.zip",
        apply="true",
        validation=checked.json()["validation"],
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["applied"] is True
    with app.state.db() as session:
        record = session.scalar(select(Entry).where(Entry.project_id == target["x-moss-project"]))
        assert record.slug == "מדריך-התקנה"
        assert record.data["title"] == "שלום עולם"
        assert record.data["body"] == "תוכן בעברית"
        stored = session.scalar(select(Asset).where(Asset.project_id == target["x-moss-project"]))
        assert stored.name == "שלום.txt"
        assert (app.state.settings.storage_dir / stored.key).read_bytes() == "תוכן הקובץ".encode()
