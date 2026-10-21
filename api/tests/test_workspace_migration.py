import json
import zipfile
from io import BytesIO

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


def preview(client, headers, archive, **fields):
    return client.post(
        "/api/migration/import",
        headers=headers,
        files={"file": ("workspace.zip", archive, "application/zip")},
        data=fields,
    )


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
