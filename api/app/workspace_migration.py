"""Authenticated browser access to portable workspace archives."""

import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer
from starlette.background import BackgroundTask

from .accounts import context
from .portability import MAX_BYTES, _load, export_workspace, import_workspace
from .security import CmsError, require

router = APIRouter(prefix="/api/migration")
MAX_ARCHIVE_UPLOAD = 64 * 1024 * 1024
MAX_PIPELINE_BYTES = 256 * 1024
VALIDATION_TTL = 15 * 60


def _identity(request):
    with request.app.state.db() as session:
        identity = context(request, session)
        require(identity, "admin", write=True)
        return identity["project_id"], identity["user"].email, identity["user"].id


def _signer(settings):
    return URLSafeTimedSerializer(settings.secret, salt="moss-workspace-import")


@router.get("/limits")
def limits(request: Request):
    with request.app.state.db() as session:
        require(context(request, session), "admin")
    return {"archiveBytes": MAX_ARCHIVE_UPLOAD, "payloadBytes": MAX_BYTES, "pipelineBytes": MAX_PIPELINE_BYTES}


@router.post("/export")
def download(request: Request, history: bool = Form(False), includePrivate: bool = Form(False)):
    project_id, email, _ = _identity(request)
    temporary = tempfile.TemporaryDirectory(prefix="moss-download-")
    destination = Path(temporary.name) / "workspace.zip"
    try:
        export_workspace(
            request.app.state.db,
            request.app.state.settings,
            project_id,
            email,
            destination,
            include_private=includePrivate,
            history=history,
        )
        return FileResponse(
            destination,
            media_type="application/zip",
            filename=f"moss-workspace-{project_id}.zip",
            background=BackgroundTask(temporary.cleanup),
        )
    except Exception:
        temporary.cleanup()
        raise


@router.post("/import")
def upload(
    request: Request,
    file: UploadFile,
    pipeline: str = Form("{}"),
    apply: bool = Form(False),
    validation: str = Form(""),
):
    project_id, email, user_id = _identity(request)
    settings = request.app.state.settings
    if len(pipeline.encode()) > MAX_PIPELINE_BYTES:
        raise HTTPException(413, "Transform pipeline exceeds 256 KiB.")
    expected_key = None
    if apply:
        try:
            claim = _signer(settings).loads(validation, max_age=VALIDATION_TTL)
        except BadSignature:
            raise CmsError("Validation expired or is missing. Validate again before importing.", "CONFLICT") from None
        if not isinstance(claim, dict) or claim.get("project") != project_id or claim.get("user") != user_id:
            raise CmsError("This validation belongs to another workspace or account.", "FORBIDDEN")
        expected_key = claim["importKey"]
    with tempfile.TemporaryDirectory(prefix="moss-upload-") as temporary:
        source = Path(temporary) / "workspace.zip"
        size = 0
        with source.open("xb") as output:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_ARCHIVE_UPLOAD:
                    raise HTTPException(
                        413, "Browser imports support archives up to 64 MiB. Use the operator CLI for larger archives."
                    )
                output.write(chunk)
        if not size:
            raise CmsError("Choose a workspace ZIP archive.")
        try:
            report = import_workspace(
                request.app.state.db,
                settings,
                project_id,
                email,
                source,
                pipeline=_load(pipeline),
                apply=apply,
                expected_key=expected_key,
            )
        except zipfile.BadZipFile:
            raise CmsError("Choose a valid workspace ZIP archive.") from None
    report["validation"] = _signer(settings).dumps(
        {"project": project_id, "user": user_id, "importKey": report["importKey"]}
    )
    return report
