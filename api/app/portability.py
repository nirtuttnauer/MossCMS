"""Bounded workspace archives and atomic, draft-only imports for operators."""

import hashlib
import json
import mimetypes
import os
import re
import stat
import tempfile
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import boto3
from sqlalchemy import select

from .content import slugify
from .development import DEVELOPMENT_USER_ID
from .images import process_image
from .models import Asset, Audit, ContentType, Entry, Membership, Project, Revision, SchemaRevision, User, now
from .schema import LOCALE, NAME, public_fields, reference_targets, validate_data, validate_fields
from .security import CmsError, audit
from .transforms import transform_data, validate_steps

MAX_BYTES = 512 * 1024 * 1024
MAX_RECORD = 2 * 1024 * 1024
MAX_RECORDS = 50_000
METADATA = {"schemas.json", "entries.ndjson", "assets.ndjson", "revisions.ndjson", "provenance.ndjson"}


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()


def _line(value):
    result = _json(value) + b"\n"
    if len(result) > MAX_RECORD:
        raise CmsError("Archive record exceeds 2 MiB; reduce selected history.")
    return result


def _load(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise CmsError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        return json.loads(
            raw, object_pairs_hook=pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError())
        )
    except (ValueError, UnicodeError, RecursionError):
        raise CmsError("Archive contains malformed JSON.") from None


def operator_identity(session, project_id, email, *, development=False):
    project = session.scalar(select(Project).where(Project.id == project_id).with_for_update())
    user = session.scalar(select(User).where(User.email == email.strip().lower()))
    member = (
        session.scalar(
            select(Membership)
            .where(Membership.project_id == project_id, Membership.user_id == user.id)
            .execution_options(populate_existing=True)
        )
        if user
        else None
    )
    local_admin = development and user and user.id == DEVELOPMENT_USER_ID
    if not project or not (local_admin or (member and member.role == "admin")):
        raise CmsError("The selected account must be an administrator of this workspace.", "FORBIDDEN")
    return project, user


def _redact(fields, data):
    """Remove private paths while retaining unknown historical values."""
    result = deepcopy(data)
    if not isinstance(result, dict):
        return result
    for field in fields:
        name = field.get("name")
        if name not in result:
            continue
        if field.get("private"):
            del result[name]
        else:
            result[name] = _redact_value(field, result[name])
    return result


def _redact_value(field, value):
    if value is None:
        return None
    if field.get("private"):
        return None
    if field.get("localized") and isinstance(value, dict):
        return {k: _redact_value({**field, "localized": False}, v) for k, v in value.items()}
    if field["type"] == "object":
        return _redact(field["fields"], value)
    if field["type"] == "list" and isinstance(value, list):
        return [_redact_value(field["item"], item) for item in value]
    return value


def _private_paths(fields, prefix=""):
    paths = []
    for field in fields:
        path = prefix + field.get("name", "*")
        if field.get("private"):
            paths.append(path)
        elif field["type"] == "object":
            paths.extend(_private_paths(field["fields"], path + (".*." if field.get("localized") else ".")))
        elif field["type"] == "list":
            paths.extend(_private_paths([field["item"]], path + "."))
    return paths


def _redact_provenance(value, depth=0, include_private=False):
    if (
        depth > 8
        or not isinstance(value, dict)
        or not isinstance(value.get("schemas"), list)
        or not isinstance(value.get("entry"), dict)
        or not isinstance(value.get("history", []), list)
        or not isinstance(value.get("previous", []), list)
    ):
        raise CmsError("Invalid or excessively nested import provenance.")
    value = deepcopy(value)
    definitions = value["schemas"]
    if any(not isinstance(d, dict) or not isinstance(d.get("fields"), list) for d in definitions):
        raise CmsError("Invalid provenance schemas.")
    fields = [d["fields"] for d in definitions]
    for snapshot in (value["entry"].get(k) for k in ("draft", "published", "scheduled")):
        if snapshot:
            if not isinstance(snapshot, dict) or not isinstance(snapshot.get("data"), dict):
                raise CmsError("Invalid provenance snapshot.")
            if not include_private:
                for definition in fields:
                    snapshot["data"] = _redact(definition, snapshot["data"])
    for revision in value.get("history", []):
        if (
            not isinstance(revision, dict)
            or not isinstance(revision.get("snapshot"), dict)
            or not isinstance(revision["snapshot"].get("data"), dict)
        ):
            raise CmsError("Invalid provenance history.")
        revision.pop("author", None)
        if not include_private:
            if any(p == "title" or p.startswith("title.") for definition in fields for p in _private_paths(definition)):
                revision["snapshot"].pop("title", None)
            for definition in fields:
                revision["snapshot"]["data"] = _redact(definition, revision["snapshot"]["data"])
    for definition in definitions:
        if not include_private:
            definition["fields"] = public_fields(definition["fields"])
        definition.pop("history", None)
    value["previous"] = [_redact_provenance(p, depth + 1, include_private) for p in value.get("previous", [])]
    return value


def _asset_bytes(settings, asset, key):
    if asset.storage == "s3":
        response = boto3.client("s3", endpoint_url=settings.s3_endpoint).get_object(Bucket=settings.s3_bucket, Key=key)
        try:
            payload = response["Body"].read(settings.max_upload + 1)
        finally:
            response["Body"].close()
    elif asset.storage == "local":
        target = (settings.storage_dir / key).resolve()
        if not target.is_relative_to(settings.storage_dir.resolve()):
            raise CmsError("Asset storage path escapes the media directory.")
        with target.open("rb") as file:
            payload = file.read(settings.max_upload + 1)
    else:
        raise CmsError("Unsupported asset storage backend.")
    if not payload or len(payload) > settings.max_upload:
        raise CmsError(f"Asset {asset.id} exceeds upload limits or is empty.")
    return payload


def export_workspace(factory, settings, project_id, email, destination, *, include_private=False, history=False):
    destination = Path(destination)
    partial = destination.with_name(destination.name + ".partial")
    if destination.exists() or partial.exists():
        raise CmsError("Export path or its .partial file already exists; choose a new path.")
    with factory.begin() as session:
        if session.get_bind().dialect.name == "postgresql":
            session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        elif session.get_bind().dialect.name == "sqlite":
            session.connection().exec_driver_sql("BEGIN")
        project, user = operator_identity(session, project_id, email, development=getattr(settings, "skip_auth", False))
        with tempfile.TemporaryDirectory(prefix="moss-export-") as temporary:
            root = Path(temporary)
            schemas = []
            omissions: list[str] = []
            definitions = {}
            for definition in session.scalars(select(ContentType).where(ContentType.project_id == project_id)):
                versions = session.scalars(
                    select(SchemaRevision)
                    .where(SchemaRevision.type_id == definition.id)
                    .order_by(SchemaRevision.version)
                ).all()
                all_fields = [v.fields for v in versions] + [definition.fields]
                fields = definition.fields if include_private else public_fields(definition.fields)
                validate_fields(fields)
                schemas.append(
                    {
                        "key": definition.key,
                        "name": definition.name,
                        "version": definition.version,
                        "fields": fields,
                        "history": [
                            {"version": v.version, "fields": v.fields if include_private else public_fields(v.fields)}
                            for v in versions
                        ],
                    }
                )
                definitions[definition.id] = (definition, all_fields)
                if not include_private:
                    omissions.extend(f"{definition.key}.{p}" for f in all_fields for p in _private_paths(f))
            (root / "schemas.json").write_bytes(_json(schemas))
            counts = {"schemas": len(schemas), "entries": 0, "assets": 0, "revisions": 0, "provenance": 0}
            with (
                (root / "entries.ndjson").open("wb") as entries,
                (root / "revisions.ndjson").open("wb") as revisions,
                (root / "provenance.ndjson").open("wb") as provenance,
            ):
                for record in session.scalars(select(Entry).where(Entry.project_id == project_id).order_by(Entry.id)):
                    definition, all_fields = definitions[record.type_id]

                    def redact(data):
                        if not include_private:
                            for fields in all_fields:
                                data = _redact(fields, data)
                        return data

                    def snapshot(kind):
                        data = record.data if kind == "draft" else getattr(record, kind + "_data")
                        if data is None:
                            return None
                        result = {
                            "slug": record.slug if kind == "draft" else getattr(record, kind + "_slug"),
                            "data": redact(data),
                        }
                        if kind == "draft":
                            result.update(version=record.version, schemaVersion=definition.version)
                        else:
                            stamp = getattr(record, kind + "_at")
                            result.update(
                                revision=getattr(record, kind + "_revision"),
                                schemaVersion=getattr(record, kind + "_schema_version"),
                                at=stamp.isoformat() + "Z" if stamp else None,
                            )
                        return result

                    row = {
                        "id": record.id,
                        "typeKey": definition.key,
                        "status": record.status,
                        **{k: snapshot(k) for k in ("draft", "published", "scheduled")},
                    }
                    entries.write(_line(row))
                    counts["entries"] += 1
                    for revision in session.scalars(
                        select(Revision).where(Revision.entry_id == record.id).order_by(Revision.number)
                    ):
                        stored = deepcopy(revision.snapshot)
                        imported = stored.pop("imported", None)
                        if imported:
                            imported = _redact_provenance(imported, include_private=include_private)
                            if not include_private:
                                omissions.extend(
                                    f"{definition.key}.{p}"
                                    for d in revision.snapshot["imported"]["schemas"]
                                    for p in _private_paths(d["fields"])
                                )
                            provenance.write(_line({"entryId": record.id, "source": imported}))
                            counts["provenance"] += 1
                        if history:
                            if not include_private:
                                historical_type = stored.get("typeKey", definition.key)
                                for other_definition, historical_fields in definitions.values():
                                    if other_definition.key == historical_type:
                                        for fields in historical_fields:
                                            stored["data"] = _redact(fields, stored["data"])
                                            if any(
                                                p == "title" or p.startswith("title.") for p in _private_paths(fields)
                                            ):
                                                stored.pop("title", None)
                            revisions.write(
                                _line(
                                    {
                                        "entryId": record.id,
                                        "number": revision.number,
                                        "at": revision.created_at.isoformat() + "Z",
                                        "snapshot": stored,
                                    }
                                )
                            )
                            counts["revisions"] += 1
            (root / "assets").mkdir()
            with (root / "assets.ndjson").open("wb") as assets:
                for asset in session.scalars(select(Asset).where(Asset.project_id == project_id)):

                    def blob(key):
                        payload = _asset_bytes(settings, asset, key)
                        digest = hashlib.sha256(payload).hexdigest()
                        path = "assets/" + digest
                        (root / path).write_bytes(payload)
                        return {"path": path, "sha256": digest, "bytes": len(payload)}

                    original = blob(asset.key)
                    if original["bytes"] != asset.size:
                        raise CmsError(f"Asset {asset.id} byte length does not match its metadata.")
                    variants = [
                        {"width": v["width"], "height": v["height"], **blob(v["key"])} for v in asset.variants or []
                    ]
                    assets.write(
                        _line(
                            {
                                "id": asset.id,
                                "name": asset.name,
                                "mime": asset.mime,
                                "width": asset.width,
                                "height": asset.height,
                                "original": original,
                                "variants": variants,
                            }
                        )
                    )
                    counts["assets"] += 1
            files: dict[str, dict[str, Any]] = {}
            for file in sorted(root.rglob("*")):
                if file.is_file():
                    payload = file.read_bytes()
                    files[file.relative_to(root).as_posix()] = {
                        "bytes": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
            if sum(f["bytes"] for f in files.values()) > MAX_BYTES or any(
                count > MAX_RECORDS for count in counts.values()
            ):
                raise CmsError("Workspace exceeds the bounded archive limits.")
            manifest = {
                "format": "mosscms.content",
                "version": 1,
                "exportedAt": now().isoformat() + "Z",
                "workspace": {
                    "id": project.id,
                    "name": project.name,
                    "locales": project.locales,
                    "defaultLocale": project.default_locale,
                },
                "counts": counts,
                "history": history,
                "includePrivate": include_private,
                "omittedFields": sorted(set(omissions)),
                "files": files,
            }
            manifest_bytes = _json(manifest)
            if len(manifest_bytes) > MAX_RECORD:
                raise CmsError("Export manifest exceeds 2 MiB.")
            (root / "manifest.json").write_bytes(manifest_bytes)
            descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with (
                os.fdopen(descriptor, "wb") as output,
                zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive,
            ):
                for file in sorted(root.rglob("*")):
                    if file.is_file():
                        archive.write(file, file.relative_to(root).as_posix())
            # Linking finalizes without overwriting a concurrently created export.
            os.link(partial, destination)
            partial.unlink()
        audit(
            session,
            project_id,
            user.email,
            "workspace.export",
            counts=counts,
            includePrivate=include_private,
            history=history,
        )
    return {
        "path": str(destination),
        "counts": counts,
        "omittedFields": manifest["omittedFields"],
        "includePrivate": include_private,
    }


def _unpack(source, root):
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) > 100_000 or len(names) != len(set(names)) or "manifest.json" not in names:
            raise CmsError("Archive has duplicate names, too many files, or no manifest.")
        total = 0
        for info in infos:
            name = info.filename
            path = PurePosixPath(name)
            mode = info.external_attr >> 16
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in name
                or str(path) != name
                or info.is_dir()
                or (stat.S_IFMT(mode) not in {0, stat.S_IFREG})
            ):
                raise CmsError(f"Unsafe archive path: {name}")
            if name not in METADATA | {"manifest.json"} and not re.fullmatch(r"assets/[0-9a-f]{64}", name):
                raise CmsError(f"Unsupported archive payload: {name}")
            total += info.file_size
            if total > MAX_BYTES or info.file_size > MAX_BYTES or info.file_size / max(info.compress_size, 1) > 200:
                raise CmsError("Archive exceeds decompression limits.")
            if name == "manifest.json" and info.file_size > MAX_RECORD:
                raise CmsError("Manifest exceeds 2 MiB.")
            if info.flag_bits & 1:
                raise CmsError("Encrypted archives are unsupported.")
        manifest = _load(archive.read("manifest.json"))
        if (
            not isinstance(manifest, dict)
            or manifest.get("format") != "mosscms.content"
            or type(manifest.get("version")) is not int
            or manifest.get("version") != 1
        ):
            raise CmsError("Unsupported content archive format or version.")
        files = manifest.get("files")
        if not isinstance(files, dict) or set(files) != set(names) - {"manifest.json"} or not METADATA <= set(files):
            raise CmsError("Manifest must list every payload exactly once.")
        for name, expected in files.items():
            if not isinstance(expected, dict):
                raise CmsError("Invalid file checksum metadata.")
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            digest, size = hashlib.sha256(), 0
            with archive.open(name) as incoming, target.open("xb") as output:
                while chunk := incoming.read(1024 * 1024):
                    digest.update(chunk)
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise CmsError("Archive exceeds decompression limits.")
                    output.write(chunk)
            if size != expected.get("bytes") or digest.hexdigest() != expected.get("sha256"):
                raise CmsError(f"Checksum mismatch: {name}")
        return manifest


def _records(root, name):
    records: list[dict] = []
    with (root / name).open("rb") as file:
        while line := file.readline(MAX_RECORD + 1):
            if len(line) > MAX_RECORD or len(records) >= MAX_RECORDS:
                raise CmsError(f"{name} exceeds record limits.")
            record = _load(line)
            if not isinstance(record, dict):
                raise CmsError(f"{name} records must be objects.")
            records.append(record)
    return records


def _unique(records, key):
    result = {}
    for record in records:
        if not isinstance(record, dict):
            raise CmsError("Archive records must be objects.")
        identity = record.get(key)
        if not isinstance(identity, str) or not 1 <= len(identity) <= 100 or identity in result:
            raise CmsError(f"Duplicate or invalid {key} in archive.")
        result[identity] = record
    return result


def _remap(field, value, entry_ids, asset_ids, path):
    if value is None:
        return None
    if field.get("localized") and isinstance(value, dict):
        return {
            k: _remap({**field, "localized": False}, v, entry_ids, asset_ids, path + "." + k) for k, v in value.items()
        }
    kind = field["type"]
    if kind in {"reference", "asset"}:
        mapping = entry_ids if kind == "reference" else asset_ids
        if not isinstance(value, str) or value not in mapping:
            raise CmsError(f"Unresolved {kind} at {path}.", field_path=path)
        return mapping[value]
    if kind == "object" and isinstance(value, dict):
        return _remap_data(field["fields"], value, entry_ids, asset_ids, path)
    if kind == "list" and isinstance(value, list):
        return [_remap(field["item"], item, entry_ids, asset_ids, f"{path}[{i}]") for i, item in enumerate(value)]
    if kind == "richText" and isinstance(value, str):

        def media(match):
            source = match.group(1)
            if source not in asset_ids:
                raise CmsError(f"Unresolved Markdown asset at {path}: {source}", field_path=path)
            return "asset:" + asset_ids[source]

        return re.sub(r"asset:([A-Za-z0-9_-]{1,100})", media, value)
    return value


def _remap_data(fields, data, entry_ids, asset_ids, path="data"):
    if not isinstance(data, dict):
        raise CmsError(f"{path} must be an object.")
    result = deepcopy(data)
    for field in fields:
        if field["name"] in result:
            result[field["name"]] = _remap(
                field, result[field["name"]], entry_ids, asset_ids, path + "." + field["name"]
            )
    return result


def _stamp(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if not result.tzinfo:
            raise ValueError()
        return result.astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, AttributeError):
        raise CmsError("Source timestamps must include a UTC offset.") from None


def _empty(session, project_id):
    for model in (ContentType, Entry, Asset):
        if session.scalar(select(model.id).where(model.project_id == project_id).limit(1)):
            raise CmsError("Import requires an empty destination workspace.", "CONFLICT")


def _linked_mapping(value, mapping):
    strings = set()

    def walk(item):
        if isinstance(item, str):
            strings.add(item)
            strings.update(re.findall(r"asset:([A-Za-z0-9_-]{1,100})", item))
        elif isinstance(item, dict):
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return {kind: {key: target for key, target in ids.items() if key in strings} for kind, ids in mapping.items()}


def import_workspace(factory, settings, project_id, email, source, *, pipeline=None, apply=False, expected_key=None):
    pipeline = {} if pipeline is None else pipeline
    if (
        not isinstance(pipeline, dict)
        or set(pipeline) - {"schemas", "steps"}
        or not isinstance(pipeline.get("schemas", {}), dict)
    ):
        raise CmsError("Pipeline must contain schemas (keyed overrides) and steps.")
    steps = pipeline.get("steps", [])
    validate_steps(steps)
    if Path(source).stat().st_size > MAX_BYTES + 16 * 1024 * 1024:
        raise CmsError("Archive exceeds file size limits.")
    stored_keys = []
    try:
        with tempfile.TemporaryDirectory(prefix="moss-import-") as temporary:
            root = Path(temporary)
            staged_archive = root / "source.zip"
            digest, size = hashlib.sha256(), 0
            with Path(source).open("rb") as incoming, staged_archive.open("xb") as outgoing:
                while chunk := incoming.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_BYTES + 16 * 1024 * 1024:
                        raise CmsError("Archive exceeds file size limits.")
                    digest.update(chunk)
                    outgoing.write(chunk)
            bundle_hash = digest.hexdigest()
            import_key = hashlib.sha256(_json({"bundle": bundle_hash, "pipeline": pipeline})).hexdigest()
            if expected_key is not None and expected_key != import_key:
                raise CmsError("Archive or pipeline changed. Validate again before importing.", "CONFLICT")
            manifest = _unpack(staged_archive, root)
            if not isinstance(manifest.get("includePrivate"), bool) or not isinstance(manifest.get("history"), bool):
                raise CmsError("Manifest private/history flags must be booleans.")
            schemas = _load((root / "schemas.json").read_bytes())
            if not isinstance(schemas, list) or len(schemas) > MAX_RECORDS:
                raise CmsError("Schemas must be a bounded list.")
            definitions = _unique(schemas, "key")
            for definition in definitions.values():
                validate_fields(definition.get("fields"))
                if not isinstance(definition.get("history", []), list):
                    raise CmsError("Invalid schema history.")
                for old in definition.get("history", []):
                    if not isinstance(old, dict) or not isinstance(old.get("fields"), list):
                        raise CmsError("Invalid schema history.")
                    if old["fields"]:
                        validate_fields(old["fields"])
            entries = _unique(_records(root, "entries.ndjson"), "id")
            assets = _unique(_records(root, "assets.ndjson"), "id")
            history = _records(root, "revisions.ndjson")
            provenance = _records(root, "provenance.ndjson")
            counts = {
                "schemas": len(schemas),
                "entries": len(entries),
                "assets": len(assets),
                "revisions": len(history),
                "provenance": len(provenance),
            }
            if manifest.get("counts") != counts:
                raise CmsError("Manifest record counts do not match payloads.")
            workspace = manifest.get("workspace", {})
            if not isinstance(workspace, dict):
                raise CmsError("Invalid source workspace.")
            locales = workspace.get("locales")
            if (
                not isinstance(locales, list)
                or not 1 <= len(locales) <= 40
                or any(not isinstance(v, str) or not LOCALE.fullmatch(v) for v in locales)
                or len(set(locales)) != len(locales)
                or workspace.get("defaultLocale") not in locales
            ):
                raise CmsError("Invalid source workspace locales.")
            if set(pipeline.get("schemas", {})) - set(definitions) or any(
                step.get("typeKey", next(iter(definitions), None)) not in definitions for step in steps
            ):
                raise CmsError("Pipeline names an unknown content type.")
            target_schemas = deepcopy(definitions)
            for key, override in pipeline.get("schemas", {}).items():
                if not isinstance(override, dict) or set(override) - {"name", "fields"}:
                    raise CmsError("Schema overrides support name and fields.")
                target_schemas[key].update(override)
            for key, definition in target_schemas.items():
                if (
                    not NAME.fullmatch(key)
                    or not isinstance(definition.get("name"), str)
                    or not 1 <= len(definition["name"].strip()) <= 100
                ):
                    raise CmsError("Invalid content type key or name.")
                validate_fields(definition.get("fields"))
                if reference_targets(definition["fields"]) - set(definitions):
                    raise CmsError("Schema contains an unresolved reference target.")
            entry_ids = {
                key: str(uuid5(NAMESPACE_URL, f"moss:{project_id}:{import_key}:entry:{key}")) for key in entries
            }
            asset_ids = {
                key: str(uuid5(NAMESPACE_URL, f"moss:{project_id}:{import_key}:asset:{key}")) for key in assets
            }
            report = {
                "bundleSha256": bundle_hash,
                "importKey": import_key,
                "counts": counts,
                "publication": "drafts; source trash stays trashed; published/scheduled states retained in revision provenance",
                "omittedFields": manifest.get("omittedFields", []),
                "includePrivate": manifest.get("includePrivate", False),
                "schemas": {k: {"sourceVersion": v.get("version"), "targetVersion": 1} for k, v in definitions.items()},
                "sourceSchemas": schemas,
                "mapping": {"entries": entry_ids, "assets": asset_ids},
                "transformations": [],
                "applied": False,
            }
            with factory.begin() as session:
                if session.get_bind().dialect.name == "sqlite":
                    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                project, user = operator_identity(
                    session, project_id, email, development=getattr(settings, "skip_auth", False)
                )
                receipts = session.scalars(
                    select(Audit).where(Audit.project_id == project_id, Audit.action == "workspace.import")
                )
                if any(receipt.details.get("importKey") == import_key for receipt in receipts):
                    return {**report, "applied": True, "alreadyImported": True}
                _empty(session, project_id)
                types = {}
                for key, definition in target_schemas.items():
                    type_record = ContentType(
                        project_id=project_id, key=key, name=definition["name"], fields=definition["fields"]
                    )
                    session.add(type_record)
                    types[key] = type_record
                session.flush()
                for type_record in types.values():
                    session.add(SchemaRevision(type_id=type_record.id, version=1, fields=type_record.fields))
                backend = "s3" if settings.s3_bucket else "local"
                planned_files = []
                for source_id, asset in assets.items():
                    name, mime = asset.get("name"), asset.get("mime")
                    if (
                        not isinstance(name, str)
                        or not 1 <= len(name) <= 254
                        or Path(name).name != name
                        or not isinstance(mime, str)
                        or not 1 <= len(mime) <= 100
                        or mime != (mimetypes.guess_type(name)[0] or "application/octet-stream")
                    ):
                        raise CmsError("Invalid asset name or MIME type.")

                    def check_blob(blob):
                        if (
                            not isinstance(blob, dict)
                            or blob.get("path") != "assets/" + str(blob.get("sha256"))
                            or blob.get("path") not in manifest["files"]
                        ):
                            raise CmsError("Invalid asset payload path.")
                        expected = manifest["files"][blob["path"]]
                        if (
                            blob.get("sha256") != expected["sha256"]
                            or blob.get("bytes") != expected["bytes"]
                            or not 0 < expected["bytes"] <= settings.max_upload
                        ):
                            raise CmsError("Asset integrity or upload size validation failed.")
                        return root / blob["path"]

                    original = check_blob(asset.get("original"))
                    width, height, _ = process_image(original.read_bytes(), mime)
                    if asset.get("width") != width or asset.get("height") != height:
                        raise CmsError("Asset dimensions do not match its bytes.")
                    target_key = project_id + "/" + asset_ids[source_id]
                    planned_files.append((target_key, original, mime))
                    variants, widths = [], set()
                    if not isinstance(asset.get("variants"), list) or len(asset["variants"]) > 4:
                        raise CmsError("Asset variants must be a list of at most four images.")
                    for variant in asset["variants"]:
                        payload = check_blob(variant)
                        vw, vh, _ = process_image(payload.read_bytes(), "image/webp")
                        if width is None or vw != variant.get("width") or vh != variant.get("height") or vw in widths:
                            raise CmsError("Invalid or duplicate asset variant dimensions.")
                        widths.add(vw)
                        variant_key = f"{target_key}.{vw}.webp"
                        planned_files.append((variant_key, payload, "image/webp"))
                        variants.append({"width": vw, "height": vh, "size": variant["bytes"], "key": variant_key})
                    session.add(
                        Asset(
                            id=asset_ids[source_id],
                            project_id=project_id,
                            name=name,
                            mime=mime,
                            key=target_key,
                            storage=backend,
                            size=asset["original"]["bytes"],
                            width=width,
                            height=height,
                            variants=variants,
                        )
                    )
                records, slugs = {}, set()
                for source_id, entry in entries.items():
                    key, draft = entry.get("typeKey"), entry.get("draft")
                    if not isinstance(entry.get("status"), str) or entry["status"] not in {
                        "draft",
                        "published",
                        "scheduled",
                        "deleted",
                    }:
                        raise CmsError(f"Invalid source status for entry {source_id}.")
                    if (
                        not isinstance(key, str)
                        or key not in types
                        or not isinstance(draft, dict)
                        or not isinstance(draft.get("slug"), str)
                        or slugify(draft["slug"]) != draft["slug"]
                    ):
                        raise CmsError(f"Invalid draft/type/slug for entry {source_id}.")
                    if (key, draft["slug"]) in slugs:
                        raise CmsError(f"Duplicate slug for type {key}: {draft['slug']}")
                    slugs.add((key, draft["slug"]))
                    record = Entry(
                        id=entry_ids[source_id],
                        project_id=project_id,
                        type_id=types[key].id,
                        slug=draft["slug"],
                        title=draft["slug"],
                        data={},
                        status="deleted" if entry["status"] == "deleted" else "draft",
                        author_id=user.id,
                    )
                    records[source_id] = record
                    session.add(record)
                session.flush()
                source_history: dict[str, list[dict]] = {key: [] for key in entries}
                source_provenance: dict[str, list[dict]] = {key: [] for key in entries}
                numbers = set()
                for item in history:
                    key, number = item.get("entryId"), item.get("number")
                    if (
                        not isinstance(key, str)
                        or key not in entries
                        or type(number) is not int
                        or not 1 <= number < 2_000_000_000
                        or (key, number) in numbers
                        or not isinstance(item.get("snapshot"), dict)
                        or not isinstance(item["snapshot"].get("data"), dict)
                        or ("typeKey" in item["snapshot"] and not isinstance(item["snapshot"]["typeKey"], str))
                    ):
                        raise CmsError("Invalid, duplicate, or orphaned history record.")
                    _stamp(item.get("at"))
                    numbers.add((key, number))
                    source_history[key].append(item)
                for item in provenance:
                    if (
                        not isinstance(item.get("entryId"), str)
                        or item["entryId"] not in entries
                        or not isinstance(item.get("source"), dict)
                    ):
                        raise CmsError("Invalid or orphaned provenance record.")
                    # Provenance is content only, never an executable configuration.
                    _redact_provenance(item["source"])
                    source_provenance[item["entryId"]].append(item["source"])
                for source_id, entry in entries.items():
                    definition = types[entry["typeKey"]]
                    transformed = {}
                    for kind in ("draft", "published", "scheduled"):
                        snapshot = entry.get(kind)
                        if snapshot is None and kind != "draft":
                            continue
                        if (
                            not isinstance(snapshot, dict)
                            or not isinstance(snapshot.get("slug"), str)
                            or slugify(snapshot["slug"]) != snapshot["slug"]
                            or not isinstance(snapshot.get("data"), dict)
                        ):
                            raise CmsError(f"Invalid {kind} snapshot for {source_id}.")
                        if kind != "draft" and snapshot.get("at") is not None:
                            _stamp(snapshot["at"])
                        changes: list[dict] = []
                        try:
                            data = transform_data(snapshot["data"], steps, entry["typeKey"], changes)
                            data = _remap_data(definition.fields, data, entry_ids, asset_ids)
                            validate_data(definition.fields, data, session, project_id)
                        except CmsError as error:
                            raise CmsError(
                                f"Entry {source_id}, {kind}: {error}", error.code, error.field_path, error.reason
                            ) from None
                        transformed[kind] = data
                        report["transformations"].extend(
                            {"entryId": source_id, "snapshot": kind, **change} for change in changes
                        )
                    record = records[source_id]
                    record.data = transformed["draft"]
                    title = record.data.get("title", record.slug)
                    if isinstance(title, dict):
                        title = title.get(workspace["defaultLocale"]) or next(iter(title.values()), record.slug)
                    record.title = str(title)[:200]
                    session.flush()
                    schema_keys = {entry["typeKey"]} | {
                        h["snapshot"].get("typeKey", entry["typeKey"]) for h in source_history[source_id]
                    }
                    imported = {
                        "bundleSha256": bundle_hash,
                        "workspace": workspace,
                        "entry": entry,
                        "schemas": [
                            d
                            for k in sorted(schema_keys)
                            if k in definitions
                            for d in [definitions[k], *definitions[k].get("history", [])]
                        ],
                        "history": source_history[source_id],
                        "mapping": _linked_mapping([entry, source_history[source_id]], report["mapping"]),
                        "previous": source_provenance[source_id],
                    }
                    _line({"entryId": record.id, "source": imported})
                    session.add(
                        Revision(
                            project_id=project_id,
                            entry_id=record.id,
                            number=record.version,
                            author="workspace import",
                            snapshot={
                                "typeKey": definition.key,
                                "slug": record.slug,
                                "title": record.title,
                                "data": record.data,
                                "status": record.status,
                                "imported": imported,
                            },
                        )
                    )
                project.locales, project.default_locale = locales, workspace["defaultLocale"]
                session.flush()
                if not apply:
                    session.rollback()
                else:
                    # No files are written until every snapshot/reference validates.
                    operator_identity(session, project_id, email, development=getattr(settings, "skip_auth", False))
                    for key, payload, mime in planned_files:
                        if backend == "s3":
                            stored_keys.append((backend, key))
                            boto3.client("s3", endpoint_url=settings.s3_endpoint).put_object(
                                Bucket=settings.s3_bucket, Key=key, Body=payload.read_bytes(), ContentType=mime
                            )
                        else:
                            target = settings.storage_dir / key
                            target.parent.mkdir(parents=True, exist_ok=True)
                            if target.exists():
                                if target.is_symlink() or target.read_bytes() != payload.read_bytes():
                                    raise CmsError(
                                        "Interrupted import media differs from this archive; remove the reported import mapping before retrying."
                                    )
                                stored_keys.append((backend, key))
                                continue
                            with target.open("xb") as output:
                                stored_keys.append((backend, key))
                                output.write(payload.read_bytes())
                    audit(
                        session,
                        project_id,
                        user.email,
                        "workspace.import",
                        importKey=import_key,
                        bundleSha256=bundle_hash,
                        mapping=report["mapping"],
                        counts=counts,
                    )
                    report["applied"] = True
            return report
    except Exception:
        for backend, key in reversed(stored_keys):
            if backend == "local":
                (settings.storage_dir / key).unlink(missing_ok=True)
            else:
                boto3.client("s3", endpoint_url=settings.s3_endpoint).delete_object(Bucket=settings.s3_bucket, Key=key)
        raise
