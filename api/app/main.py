"""MossCMS HTTP service. Editorial and delivery GraphQL have distinct permissions."""

import asyncio
import hashlib
import json
import logging
import secrets
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from graphql import FragmentSpreadNode, FragmentDefinitionNode, OperationDefinitionNode, parse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from starlette.middleware.sessions import SessionMiddleware

from .accounts import context, router as account_router
from .config import Settings
from .content import publish_due, scoped
from .development import initialize_development
from .graphql import generated_schema
from .migrate import migrate
from .models import ContentType, database
from .oauth import configure_oauth, router as oauth_router
from .preview import router as preview_router
from .security import CmsError, identify, require
from .storage import router as storage_router

load_dotenv()
logger = logging.getLogger("mosscms")


class GraphQLRequest(BaseModel):
    query: str = Field(min_length=1, max_length=30000)
    variables: dict | None = None
    operationName: str | None = None


def bounded_query(query):
    document = parse(query)
    fragments = {d.name.value: d for d in document.definitions if isinstance(d, FragmentDefinitionNode)}
    count = 0

    def walk(selection_set, depth=0, seen=frozenset()):
        nonlocal count
        if not selection_set:
            return
        if depth > 12:
            raise CmsError("Query depth limit exceeded.", "QUERY_LIMIT")
        for node in selection_set.selections:
            count += 1
            if count > 200:
                raise CmsError("Query complexity limit exceeded.", "QUERY_LIMIT")
            if isinstance(node, FragmentSpreadNode):
                name = node.name.value
                if name in seen:
                    raise CmsError("Recursive fragment.", "QUERY_LIMIT")
                if name in fragments:
                    walk(fragments[name].selection_set, depth, seen | {name})
            else:
                walk(getattr(node, "selection_set", None), depth + 1, seen)

    for definition in document.definitions:
        if isinstance(definition, OperationDefinitionNode):
            walk(definition.selection_set)


def create_app(settings=None):
    settings = (settings or Settings()).validate()
    engine, factory = database(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        await asyncio.to_thread(migrate, engine)
        if settings.skip_auth:
            await asyncio.to_thread(initialize_development, factory)

        async def scheduler():
            while True:
                try:
                    await asyncio.to_thread(publish_due, factory)
                except Exception:
                    logger.exception("Publishing scheduler failed")
                await asyncio.sleep(5)

        job = asyncio.create_task(scheduler())
        yield
        job.cancel()
        with suppress(asyncio.CancelledError):
            await job
        engine.dispose()

    app = FastAPI(title="MossCMS", version="0.2.0", lifespan=lifespan)
    app.state.settings, app.state.engine, app.state.db = settings, engine, factory
    app.state.started = time.monotonic()
    app.state.login_attempts = {}
    app.state.development_csrf = secrets.token_urlsafe(32)
    app.state.metrics = {"requests": 0, "errors": 0, "seconds": 0.0}
    configure_oauth(app)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret,
        session_cookie="moss_oauth",
        https_only=settings.environment == "production",
        same_site="lax",
        max_age=600,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Moss-Project", "X-Moss-CSRF", "If-None-Match"],
        expose_headers=["ETag", "X-Request-ID"],
    )

    @app.middleware("http")
    async def requests(request, call_next):
        request_id = str(uuid4())
        started = time.monotonic()
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin.rstrip("/") not in settings.origins:
            return JSONResponse({"detail": "Untrusted browser origin."}, status_code=403)
        try:
            length = int(request.headers.get("content-length", 0))
        except ValueError:
            return JSONResponse({"detail": "Invalid Content-Length."}, status_code=400)
        if length > settings.max_upload + 1024 * 1024:
            return JSONResponse({"detail": "Request body is too large."}, status_code=413)
        response = await call_next(request)
        duration = time.monotonic() - started
        app.state.metrics["requests"] += 1
        app.state.metrics["errors"] += int(response.status_code >= 400)
        app.state.metrics["seconds"] += duration
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith(("/auth", "/api")):
            response.headers["Cache-Control"] = "no-store"
        logger.info(
            json.dumps(
                {
                    "requestId": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "seconds": round(duration, 4),
                }
            )
        )
        return response

    @app.exception_handler(CmsError)
    async def content_error(request, exc):
        return JSONResponse(
            {"detail": str(exc), "code": exc.code},
            status_code={"FORBIDDEN": 403, "NOT_FOUND": 404, "CONFLICT": 409}.get(exc.code, 422),
        )

    @app.exception_handler(IntegrityError)
    async def constraint_error(request, exc):
        return JSONResponse(
            {"detail": "This value conflicts with an existing record.", "code": "CONFLICT"}, status_code=409
        )

    @app.exception_handler(StaleDataError)
    async def concurrency_error(request, exc):
        return JSONResponse(
            {"detail": "This record changed. Reload before saving.", "code": "CONFLICT"}, status_code=409
        )

    app.include_router(account_router)
    app.include_router(oauth_router)
    app.include_router(storage_router)
    app.include_router(preview_router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/ready")
    def ready():
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return {"status": "ready"}
        except Exception:
            return JSONResponse({"status": "unavailable"}, status_code=503)

    @app.get("/metrics")
    def metrics(request: Request):
        with factory() as session:
            require(context(request, session), "admin")
        values = app.state.metrics
        return PlainTextResponse(
            f"moss_requests_total {values['requests']}\nmoss_errors_total {values['errors']}\nmoss_request_duration_seconds_sum {values['seconds']}\nmoss_uptime_seconds {time.monotonic() - app.state.started}\n"
        )

    @app.get("/graphql")
    def explorer():
        return RedirectResponse("/#explorer")

    @app.post("/graphql")
    @app.post("/delivery/graphql")
    def graphql(body: GraphQLRequest, request: Request):
        delivery = request.url.path.startswith("/delivery/")
        with factory() as session:
            c = {**identify(request, session, delivery), "session": session, "settings": settings, "request": request}
            require(c)
            try:
                bounded_query(body.query)
                definitions = session.scalars(scoped(session, ContentType, c)).all()
                schema = generated_schema(definitions, delivery, c.get("scopes"))
                result = schema.execute_sync(
                    body.query, variable_values=body.variables, operation_name=body.operationName, context_value=c
                )
                errors = []
                for error in result.errors or []:
                    original = error.original_error
                    if isinstance(original, CmsError):
                        message, code = str(original), original.code
                    elif original is None:
                        message, code = error.message, "GRAPHQL_VALIDATION"
                    elif isinstance(original, (IntegrityError, StaleDataError)):
                        message, code = "This record conflicts with an existing or newer record.", "CONFLICT"
                    else:
                        message, code = "The operation could not be completed.", "INTERNAL"
                    errors.append({"message": message, "path": error.path, "extensions": {"code": code}})
                if errors:
                    session.rollback()
                    payload = {"data": None, "errors": errors}
                else:
                    session.commit()
                    payload = {"data": result.data}
            except CmsError as exc:
                session.rollback()
                payload = {"data": None, "errors": [{"message": str(exc), "extensions": {"code": exc.code}}]}
            except (IntegrityError, StaleDataError):
                session.rollback()
                payload = {
                    "data": None,
                    "errors": [
                        {
                            "message": "This record conflicts with an existing or newer record.",
                            "extensions": {"code": "CONFLICT"},
                        }
                    ],
                }
            except Exception:
                session.rollback()
                logger.exception("GraphQL operation failed")
                payload = {
                    "data": None,
                    "errors": [
                        {"message": "The operation could not be completed.", "extensions": {"code": "INTERNAL"}}
                    ],
                }
        headers = {
            "Cache-Control": "private, no-cache" if delivery and not payload.get("errors") else "no-store",
            "Vary": "Authorization, Origin",
        }
        if delivery and not payload.get("errors"):
            etag = '"' + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest() + '"'
            headers["ETag"] = etag
            if request.headers.get("if-none-match") == etag:
                from fastapi import Response

                return Response(status_code=304, headers=headers)
        return JSONResponse(payload, headers=headers)

    static = Path(__file__).resolve().parents[1] / "static"
    if (static / "assets").exists():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    def admin():
        if (static / "index.html").exists():
            return FileResponse(static / "index.html", headers={"Cache-Control": "no-cache"})
        return {"service": "MossCMS", "admin": "Run the Vite dev server on port 5173."}

    return app


app = create_app()
