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
from .images import process_image
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
        width, height, images = process_image(data, mime)
        id = uid()
        key = c["project_id"] + "/" + id
        backend = "s3" if settings.s3_bucket else "local"
        stored = []
        variants = []
        try:
            for variant_width, variant_height, payload in [(None, None, data)] + images:
                object_key = key if variant_width is None else f"{key}.{variant_width}.webp"
                content_type = mime if variant_width is None else "image/webp"
                if backend == "s3":
                    boto3.client("s3", endpoint_url=settings.s3_endpoint).put_object(
                        Bucket=settings.s3_bucket, Key=object_key, Body=payload, ContentType=content_type
                    )
                else:
                    target = settings.storage_dir / object_key
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temporary = target.with_suffix(target.suffix + ".upload")
                    temporary.write_bytes(payload)
                    temporary.replace(target)
                stored.append(object_key)
                if variant_width is not None:
                    variants.append(
                        {"width": variant_width, "height": variant_height, "size": len(payload), "key": object_key}
                    )
        except Exception:
            for object_key in stored:
                if backend == "local":
                    (settings.storage_dir / object_key).unlink(missing_ok=True)
                else:
                    boto3.client("s3", endpoint_url=settings.s3_endpoint).delete_object(
                        Bucket=settings.s3_bucket, Key=object_key
                    )
            raise
        asset = Asset(
            id=id,
            project_id=c["project_id"],
            name=name,
            key=key,
            storage=backend,
            mime=mime,
            size=len(data),
            width=width,
            height=height,
            variants=variants,
        )
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
        if not (settings.storage_dir / asset.key).is_file():
            raise HTTPException(404, "Asset file is missing. Restore it from backup.")
        return FileResponse(
            settings.storage_dir / asset.key,
            filename=asset.name,
            media_type=asset.mime,
            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=60"},
        )


@router.get("/media/{id}/variant/{width}")
def variant(id: str, width: int, expires: int, signature: str, request: Request):
    settings = request.app.state.settings
    expected = hmac.new(settings.secret.encode(), f"{id}:{width}:{expires}".encode(), hashlib.sha256).hexdigest()
    if expires < time.time() or expires > time.time() + 901 or not hmac.compare_digest(expected, signature):
        raise HTTPException(403, "This variant link is expired or invalid.")
    with request.app.state.db() as session:
        asset = session.get(Asset, id)
        image = next((v for v in (asset.variants or []) if v["width"] == width), None) if asset else None
        if not image:
            raise HTTPException(404, "Image variant not found.")
        if asset.storage == "s3":
            url = boto3.client("s3", endpoint_url=settings.s3_endpoint).generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.s3_bucket, "Key": image["key"], "ResponseContentType": "image/webp"},
                ExpiresIn=min(900, max(1, expires - int(time.time()))),
            )
            return RedirectResponse(url)
        target = settings.storage_dir / image["key"]
        if not target.is_file():
            raise HTTPException(404, "Image variant is missing. Restore it from backup.")
        return FileResponse(
            target,
            media_type="image/webp",
            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=60"},
        )
