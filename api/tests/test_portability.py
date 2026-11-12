import hashlib
import json
import stat
import sys
import zipfile
from datetime import datetime
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image
from sqlalchemy import event, func, select

from app import cli
from app.images import process_image
from app.models import (
    Asset,
    Audit,
    Base,
    ContentType,
    Entry,
    Membership,
    Project,
    Revision,
    SchemaRevision,
    User,
    database,
)
from app.portability import export_workspace, import_workspace
from app.security import CmsError


@pytest.fixture
def workspace(tmp_path):
    engine, factory = database(f"sqlite:///{tmp_path}/cms.db")
    Base.metadata.create_all(engine)
    settings = SimpleNamespace(
        storage_dir=tmp_path / "media", s3_bucket="", s3_endpoint=None, max_upload=20 * 1024 * 1024
    )
    with factory.begin() as session:
        session.add(User(id="admin", email="admin@example.com", name="Admin", password_hash="never exported"))
        session.add_all(
            [
                Project(id="source", name="Source", locales=["en", "he"], default_locale="he"),
                Project(id="target", name="Target"),
                Project(id="second", name="Second"),
            ]
        )
        session.flush()
        session.add_all(
            [Membership(project_id=p, user_id="admin", role="admin") for p in ("source", "target", "second")]
        )
    yield SimpleNamespace(
        engine=engine, factory=factory, settings=settings, root=tmp_path, archive=tmp_path / "bundle.zip"
    )
    engine.dispose()


def seed(w, count=1):
    fields = [
        {"name": "title", "type": "text", "localized": True, "required": True},
        {"name": "amount", "type": "text"},
        {"name": "secret", "type": "text", "private": True},
        {"name": "body", "type": "richText"},
        {
            "name": "related",
            "type": "list",
            "item": {
                "type": "object",
                "fields": [
                    {"name": "entry", "type": "reference", "target": "article"},
                    {"name": "asset", "type": "asset", "imageOnly": True},
                    {"name": "secret", "type": "text", "private": True},
                ],
            },
        },
    ]
    output = BytesIO()
    Image.new("RGB", (8, 6), "red").save(output, format="PNG")
    payload = output.getvalue()
    width, height, variants = process_image(payload, "image/png")
    (w.settings.storage_dir / "source").mkdir(parents=True)
    (w.settings.storage_dir / "source/image").write_bytes(payload)
    stored_variants = []
    for vw, vh, body in variants:
        key = f"source/image.{vw}.webp"
        (w.settings.storage_dir / key).write_bytes(body)
        stored_variants.append({"width": vw, "height": vh, "size": len(body), "key": key})
    with w.factory.begin() as session:
        definition = ContentType(id="type", project_id="source", key="article", name="Article", fields=fields)
        session.add(definition)
        session.flush()
        session.add(SchemaRevision(type_id="type", version=1, fields=fields))
        session.add(
            Asset(
                id="image",
                project_id="source",
                name="picture.png",
                key="source/image",
                storage="local",
                mime="image/png",
                size=len(payload),
                width=width,
                height=height,
                variants=stored_variants,
            )
        )
        for i in range(count):
            data = {
                "title": {"en": f"Draft {i}", "he": f"Hebrew {i}"},
                "amount": "12",
                "secret": "private sentinel",
                "body": "![image](asset:image)",
                "related": [
                    {"entry": f"entry-{(i + 1) % count}", "asset": "image", "secret": "nested private sentinel"}
                ],
            }
            session.add(
                Entry(
                    id=f"entry-{i}",
                    project_id="source",
                    type_id="type",
                    slug=f"post-{i}",
                    title=f"Draft {i}",
                    data=data,
                    published_data={**data, "amount": "10"},
                    published_slug=f"live-{i}",
                    published_title=f"Live {i}",
                    published_at=datetime(2026, 1, 1),
                    published_revision=1,
                    published_schema_version=1,
                    scheduled_data={**data, "amount": "11"},
                    scheduled_slug=f"due-{i}",
                    scheduled_title=f"Due {i}",
                    scheduled_at=datetime(2026, 1, 2),
                    scheduled_revision=2,
                    scheduled_schema_version=1,
                    status="published",
                )
            )
        session.flush()
        for i in range(count):
            session.add(
                Revision(
                    project_id="source",
                    entry_id=f"entry-{i}",
                    number=1,
                    snapshot={
                        "typeKey": "article",
                        "slug": f"post-{i}",
                        "data": {"obsolete": "historical value", "secret": "historical private sentinel"},
                    },
                    author="personal author",
                )
            )
    return payload, fields


def export(w, **options):
    return export_workspace(w.factory, w.settings, "source", "admin@example.com", w.archive, **options)


def transfer(w, **options):
    return import_workspace(w.factory, w.settings, "target", "admin@example.com", w.archive, **options)


def assert_empty(w):
    with w.factory() as session:
        for model in (ContentType, Entry, Asset, Revision):
            assert session.scalar(select(func.count()).select_from(model).where(model.project_id == "target")) == 0
        assert session.get(Project, "target").default_locale == "en"
    assert not (w.settings.storage_dir / "target").exists() or not list((w.settings.storage_dir / "target").iterdir())


def rewrite(w, mutate):
    with zipfile.ZipFile(w.archive) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    mutate(files)
    manifest = json.loads(files["manifest.json"])
    manifest["files"] = {
        name: {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
        for name, body in files.items()
        if name != "manifest.json"
    }
    files["manifest.json"] = json.dumps(manifest).encode()
    with zipfile.ZipFile(w.archive, "w") as archive:
        for name, body in files.items():
            archive.writestr(name, body)


def test_1000_entry_round_trip_private_projection_dry_run_and_retry(workspace):
    w = workspace
    payload, _ = seed(w, 1000)
    report = export(w, history=True)
    assert stat.S_IMODE(w.archive.stat().st_mode) == 0o600
    assert report["counts"]["entries"] == 1000
    assert set(report["omittedFields"]) == {"article.secret", "article.related.*.secret"}
    with zipfile.ZipFile(w.archive) as archive:
        metadata = b"".join(archive.read(name) for name in archive.namelist() if not name.startswith("assets/"))
        assert b"private sentinel" not in metadata
        assert b"personal author" not in metadata
        assert b"never exported" not in metadata
    planned = transfer(w)
    assert planned["applied"] is False
    assert_empty(w)
    applied = transfer(w, apply=True)
    assert applied["mapping"] == planned["mapping"]
    assert applied["applied"] is True
    with w.factory() as session:
        entries = session.scalars(select(Entry).where(Entry.project_id == "target")).all()
        assert len(entries) == 1000
        first = session.get(Entry, applied["mapping"]["entries"]["entry-0"])
        assert first.title == "Hebrew 0"
        assert first.data["related"][0]["entry"] == applied["mapping"]["entries"]["entry-1"]
        assert first.data["body"] == f"![image](asset:{applied['mapping']['assets']['image']})"
        assert all(e.status == "draft" and e.published_data is None and e.scheduled_at is None for e in entries)
        revision = session.scalar(select(Revision).where(Revision.entry_id == first.id))
        assert revision.number == first.version
        imported = revision.snapshot["imported"]
        assert imported["entry"]["published"]["data"]["amount"] == "10"
        assert imported["entry"]["scheduled"]["data"]["amount"] == "11"
        assert imported["history"][0]["snapshot"]["data"]["obsolete"] == "historical value"
        assert imported["mapping"]["assets"]["image"] == applied["mapping"]["assets"]["image"]
        asset = session.get(Asset, applied["mapping"]["assets"]["image"])
        assert (w.settings.storage_dir / asset.key).read_bytes() == payload
        assert asset.variants
        assert session.get(Project, "target").locales == ["en", "he"]
    retried = transfer(w, apply=True)
    assert retried["alreadyImported"] is True
    assert retried["mapping"] == applied["mapping"]
    with w.factory() as session:
        assert session.scalar(select(func.count()).select_from(Audit).where(Audit.action == "workspace.import")) == 1


def test_pipeline_runs_in_order_for_every_snapshot_and_preserves_source(workspace):
    w = workspace
    _, fields = seed(w)
    export(w)
    fields = [
        {**f, "type": "number", "name": "count"} if f["name"] == "amount" else f for f in fields if not f.get("private")
    ]
    fields[-1]["item"]["fields"] = [f for f in fields[-1]["item"]["fields"] if not f.get("private")]
    pipeline = {
        "schemas": {"article": {"fields": fields}},
        "steps": [
            {"op": "rename", "path": "amount", "to": "count"},
            {"op": "convert", "path": "count", "to": "number"},
        ],
    }
    planned = transfer(w, pipeline=pipeline)
    assert [(c["snapshot"], c["op"]) for c in planned["transformations"]] == [
        (k, op) for k in ("draft", "published", "scheduled") for op in ("rename", "convert")
    ]
    report = transfer(w, pipeline=pipeline, apply=True)
    with w.factory() as session:
        record = session.get(Entry, report["mapping"]["entries"]["entry-0"])
        assert record.data["count"] == 12
        original = session.scalar(select(Revision).where(Revision.entry_id == record.id)).snapshot["imported"]
        assert original["entry"]["draft"]["data"]["amount"] == "12"
    with pytest.raises(CmsError, match="empty destination"):
        transfer(w, apply=True)


@pytest.mark.parametrize(
    "failure", ["checksum", "version", "path", "duplicate_id", "reference", "slug", "json", "schedule"]
)
def test_invalid_archives_never_activate_content(workspace, failure):
    w = workspace
    seed(w, 2)
    export(w)

    def mutate(files):
        if failure == "version":
            manifest = json.loads(files["manifest.json"])
            manifest["version"] = 999
            files["manifest.json"] = json.dumps(manifest).encode()
        elif failure == "path":
            files["../outside"] = b"unsafe"
        elif failure == "json":
            files["entries.ndjson"] = b'{"id":"one","id":"two"}\n'
        else:
            rows = [json.loads(line) for line in files["entries.ndjson"].splitlines()]
            if failure == "duplicate_id":
                rows[1]["id"] = rows[0]["id"]
            elif failure == "reference":
                rows[0]["published"]["data"]["related"][0]["entry"] = "absent"
            elif failure == "slug":
                rows[1]["draft"]["slug"] = rows[0]["draft"]["slug"]
            elif failure == "schedule":
                rows[0]["scheduled"]["at"] = "not-a-time"
            files["entries.ndjson"] = b"\n".join(json.dumps(row).encode() for row in rows) + b"\n"

    if failure == "checksum":
        with zipfile.ZipFile(w.archive) as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
        files["entries.ndjson"] += b" "
        with zipfile.ZipFile(w.archive, "w") as archive:
            for name, body in files.items():
                archive.writestr(name, body)
    else:
        rewrite(w, mutate)
    with pytest.raises(CmsError):
        transfer(w, apply=True)
    assert_empty(w)


def test_commit_failure_rolls_back_database_and_media_then_retry_succeeds(workspace):
    w = workspace
    seed(w)
    export(w)

    def fail_commit(connection):
        raise RuntimeError("simulated commit failure")

    event.listen(w.engine, "commit", fail_commit)
    try:
        with pytest.raises(RuntimeError, match="simulated commit failure"):
            transfer(w, apply=True)
    finally:
        event.remove(w.engine, "commit", fail_commit)
    assert_empty(w)
    assert transfer(w, apply=True)["applied"]


def test_reexport_keeps_source_states_and_redacts_imported_private_history(workspace):
    w = workspace
    seed(w)
    export(w, include_private=True, history=True)
    transfer(w, apply=True)
    second_archive = w.root / "second.zip"
    export_workspace(w.factory, w.settings, "target", "admin@example.com", second_archive)
    with zipfile.ZipFile(second_archive) as archive:
        assert b"private sentinel" not in archive.read("provenance.ndjson")
        assert b"historical value" in archive.read("provenance.ndjson")
    result = import_workspace(w.factory, w.settings, "second", "admin@example.com", second_archive, apply=True)
    with w.factory() as session:
        revision = session.scalar(select(Revision).where(Revision.project_id == "second"))
        assert revision.snapshot["imported"]["previous"][0]["entry"]["published"]["data"]["amount"] == "10"
        first_mapping = revision.snapshot["imported"]["previous"][0]["mapping"]
        assert first_mapping["assets"]["image"] in revision.snapshot["imported"]["mapping"]["assets"]
    assert result["applied"]


def test_admin_required_and_export_never_overwrites(workspace):
    w = workspace
    seed(w)
    with w.factory.begin() as session:
        session.get(Membership, ("source", "admin")).role = "editor"
    with pytest.raises(CmsError, match="administrator"):
        export(w)
    with w.factory.begin() as session:
        session.get(Membership, ("source", "admin")).role = "admin"
    export(w)
    original = w.archive.read_bytes()
    with pytest.raises(CmsError, match="already exists"):
        export(w)
    assert original == w.archive.read_bytes()
    with w.factory.begin() as session:
        session.get(Membership, ("target", "admin")).role = "reader"
    with pytest.raises(CmsError, match="administrator"):
        transfer(w, apply=True)
    assert_empty(w)


def test_cli_export_and_default_dry_run(workspace, monkeypatch, capsys):
    w = workspace
    seed(w)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    w.settings.database_url = "test"
    w.settings.validate = lambda: w.settings
    monkeypatch.setattr(cli, "Settings", lambda: w.settings)
    monkeypatch.setattr(cli, "database", lambda url: (w.engine, w.factory))
    monkeypatch.setattr(
        sys, "argv", ["moss", "export", "--project", "source", "--email", "admin@example.com", "--file", str(w.archive)]
    )
    cli.main()
    assert json.loads(capsys.readouterr().out)["counts"]["entries"] == 1
    monkeypatch.setattr(
        sys, "argv", ["moss", "import", "--project", "target", "--email", "admin@example.com", "--file", str(w.archive)]
    )
    cli.main()
    assert json.loads(capsys.readouterr().out)["applied"] is False
    assert_empty(w)


def test_interrupted_import_reuses_verified_media(workspace):
    w = workspace
    payload, _ = seed(w)
    export(w)
    plan = transfer(w)
    target = w.settings.storage_dir / "target" / plan["mapping"]["assets"]["image"]
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)
    assert transfer(w, apply=True)["applied"]
    assert target.read_bytes() == payload


@pytest.mark.parametrize("unsafe", ["duplicate", "symlink", "bomb", "oversized"])
def test_archive_structure_limits(workspace, unsafe):
    w = workspace
    seed(w)
    export(w)
    with zipfile.ZipFile(w.archive) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    if unsafe == "duplicate":
        with pytest.warns(UserWarning, match="Duplicate name"), zipfile.ZipFile(w.archive, "a") as archive:
            archive.writestr("manifest.json", files["manifest.json"])
    elif unsafe == "symlink":
        with zipfile.ZipFile(w.archive, "w") as archive:
            for name, body in files.items():
                info = zipfile.ZipInfo(name)
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, body)
    elif unsafe == "bomb":
        with zipfile.ZipFile(w.archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, body in files.items():
                archive.writestr(name, b"0" * 3_000_000 if name == "entries.ndjson" else body)
    else:
        rewrite(w, lambda files: files.update({"entries.ndjson": b"0" * (2 * 1024 * 1024 + 1)}))
    with pytest.raises(CmsError):
        transfer(w, apply=True)
    assert_empty(w)


def test_media_write_failure_cleans_up_and_can_retry(workspace, monkeypatch):
    from pathlib import Path

    w = workspace
    seed(w)
    export(w)
    original = Path.open

    def fail_variant(path, *args, **kwargs):
        if path.parent.name == "target" and path.suffix == ".webp" and args and args[0] == "xb":
            raise OSError("simulated storage failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_variant)
    with pytest.raises(OSError, match="simulated storage failure"):
        transfer(w, apply=True)
    assert_empty(w)
    monkeypatch.setattr(Path, "open", original)
    assert transfer(w, apply=True)["applied"]


def test_s3_exports_and_imports_include_originals_and_variants(workspace, monkeypatch):
    from unittest.mock import MagicMock
    from app import portability

    w = workspace
    payload, _ = seed(w)
    with w.factory.begin() as session:
        session.get(Asset, "image").storage = "s3"
    s3 = MagicMock()

    def get_object(**kwargs):
        return {"Body": BytesIO((w.settings.storage_dir / kwargs["Key"]).read_bytes())}

    s3.get_object.side_effect = get_object
    monkeypatch.setattr(portability.boto3, "client", lambda *args, **kwargs: s3)
    w.settings.s3_bucket = "private-bucket"
    export(w)
    assert s3.get_object.call_count == 2
    s3.reset_mock()
    transfer(w)
    s3.put_object.assert_not_called()
    transfer(w, apply=True)
    assert s3.put_object.call_count == 2
    assert s3.put_object.call_args_list[0].kwargs["Body"] == payload


def test_private_history_uses_its_original_content_type_after_move(workspace):
    w = workspace
    seed(w)
    with w.factory.begin() as session:
        other = ContentType(
            id="other", project_id="source", key="other", name="Other", fields=[{"name": "title", "type": "text"}]
        )
        session.add(other)
        session.flush()
        record = session.get(Entry, "entry-0")
        record.type_id = "other"
        record.data = {"title": "Moved"}
        record.published_data = record.scheduled_data = None
    export(w, history=True)
    with zipfile.ZipFile(w.archive) as archive:
        assert b"historical private sentinel" not in archive.read("revisions.ndjson")
    w.archive.unlink()
    export(w, history=True, include_private=True)
    transfer(w, apply=True)
    second = w.root / "moved.zip"
    export_workspace(w.factory, w.settings, "target", "admin@example.com", second)
    with zipfile.ZipFile(second) as archive:
        assert b"historical private sentinel" not in archive.read("provenance.ndjson")


def _replace_slugs(slug):
    def mutate(files):
        rows = [json.loads(line) for line in files["entries.ndjson"].splitlines()]
        for row in rows:
            for kind in ("draft", "published", "scheduled"):
                row[kind]["slug"] = slug
        files["entries.ndjson"] = b"\n".join(json.dumps(row, ensure_ascii=False).encode() for row in rows) + b"\n"

    return mutate


def test_import_accepts_normalized_hebrew_and_rejects_unnormalized_slugs(workspace):
    w = workspace
    seed(w, 1)
    export(w)
    rewrite(w, _replace_slugs("מדריך-התקנה"))
    applied = transfer(w, apply=True)
    with w.factory() as session:
        record = session.get(Entry, applied["mapping"]["entries"]["entry-0"])
        assert record.slug == "מדריך-התקנה"
        imported = session.scalar(select(Revision).where(Revision.entry_id == record.id)).snapshot["imported"]["entry"]
        assert imported["published"]["slug"] == "מדריך-התקנה"
        assert imported["scheduled"]["slug"] == "מדריך-התקנה"
    second = w.root / "unnormalized.zip"
    export_workspace(w.factory, w.settings, "source", "admin@example.com", second)
    w.archive = second
    rewrite(w, _replace_slugs("מדריך\u200bהתקנה"))
    with pytest.raises(CmsError, match="Invalid draft/type/slug"):
        import_workspace(w.factory, w.settings, "second", "admin@example.com", second, apply=True)
    assert_empty_project(w, "second")


def assert_empty_project(w, project_id):
    with w.factory() as session:
        assert session.scalar(select(func.count()).select_from(Entry).where(Entry.project_id == project_id)) == 0


def test_trash_stays_trashed_and_public_history_titles_are_preserved(workspace):
    w = workspace
    seed(w)
    with w.factory.begin() as session:
        session.get(Entry, "entry-0").status = "deleted"
        revision = session.scalar(select(Revision).where(Revision.entry_id == "entry-0"))
        revision.snapshot = {**revision.snapshot, "title": "Historical title"}
    export(w, history=True)
    with pytest.raises(CmsError, match="reference"):
        transfer(w, apply=True)
    result = transfer(
        w,
        apply=True,
        pipeline={"steps": [{"op": "drop", "path": "related"}, {"op": "default", "path": "related", "value": []}]},
    )
    with w.factory() as session:
        record = session.get(Entry, result["mapping"]["entries"]["entry-0"])
        assert record.status == "deleted"
        original = session.scalar(select(Revision).where(Revision.entry_id == record.id)).snapshot["imported"]
        assert original["history"][0]["snapshot"]["title"] == "Historical title"
