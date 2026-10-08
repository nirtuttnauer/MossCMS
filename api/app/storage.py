import hashlib
import hmac
import mimetypes
import time
from pathlib import Path

import boto3
from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from .accounts import context
from .graphql import asset_node
from .models import Asset, uid
from .security import audit, require

router = APIRouter()


@router.post("/api/assets")
def upload(request: Request, file: UploadFile):
    settings = request.app.state.settings
    with request.app.state.db.begin() as session:
        c = context(request, session)
        require(c, "editor", write=True)
        data = file.file.read(settings.max_upload + 1)
        if not data or len(data) > settings.max_upload:
            raise HTTPException(413, "Upload a file of 1 byte to 20 MiB.")
        name = Path(file.filename or "asset").name[:254]
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        id = uid()
        key = c["project_id"] + "/" + id
        backend = "s3" if settings.s3_bucket else "local"
        if backend == "s3":
            boto3.client("s3", endpoint_url=settings.s3_endpoint).put_object(
                Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=mime
            )
        else:
            target = settings.storage_dir / key
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(".upload")
            temporary.write_bytes(data)
            temporary.replace(target)
        asset = Asset(id=id, project_id=c["project_id"], name=name, key=key, storage=backend, mime=mime, size=len(data))
        session.add(asset)
        audit(session, c["project_id"], c["actor"], "asset.upload", assetId=id, name=name)
        return asset_node(asset, settings).__dict__


@router.get("/media/{id}")
def media(id: str, expires: int, signature: str, request: Request):
    settings = request.app.state.settings
    expected = hmac.new(settings.secret.encode(), f"{id}:{expires}".encode(), hashlib.sha256).hexdigest()
    if expires < time.time() or expires > time.time() + 901 or not hmac.compare_digest(expected, signature):
        raise HTTPException(403, "This asset link is expired or invalid.")
    with request.app.state.db() as session:
        asset = session.get(Asset, id)
        if not asset:
            raise HTTPException(404, "Asset not found.")
        if asset.storage == "s3":
            url = boto3.client("s3", endpoint_url=settings.s3_endpoint).generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.s3_bucket, "Key": asset.key, "ResponseContentDisposition": "attachment"},
                ExpiresIn=min(900, max(1, expires - int(time.time()))),
            )
            return RedirectResponse(url)
        return FileResponse(
            settings.storage_dir / asset.key,
            filename=asset.name,
            media_type=asset.mime,
            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=60"},
        )
