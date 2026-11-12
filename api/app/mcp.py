"""Stdio MCP server for published MossCMS entries.

Start it from the api directory:

    MOSS_DELIVERY_TOKEN=... python -m app.mcp

The delivery token is read from ``MOSS_DELIVERY_TOKEN``. A value on the command
line is rejected and is not written to stderr. ``MOSS_PROJECT``, when set, must
be the token's workspace; a token for another workspace is refused.

``list_published_entries`` and ``get_published_entry`` read published entries.
Drafts and scheduled entries are left out. Titles and bodies are returned as
stored, including Hebrew letters and niqqud. The server does not edit content.
``MOSS_SKIP_AUTH`` does not authenticate this process.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any, TextIO

from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import Settings
from .content import entry_dict, entry_page
from .content import get_entry as load_entry
from .models import Project, Token, database, now
from .security import CmsError, digest, require

TOKEN_ENV = "MOSS_DELIVERY_TOKEN"
PROJECT_ENV = "MOSS_PROJECT"
AUTH_MESSAGE = "A valid delivery token is required."
PAGE_SIZE = "Use a page size of 1–100 and a supported sort order."
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_NAME = "mosscms"
SERVER_VERSION = "0.1.0"
MAX_TOKEN_LENGTH = 4096
LOG = logging.getLogger("mosscms.mcp")

LIST_TOOL = "list_published_entries"
GET_TOOL = "get_published_entry"
SORTS = ("updated_desc", "updated_asc", "title_asc", "title_desc")
LIST_FIELDS = {
    "typeKey": str,
    "search": str,
    "sort": str,
    "first": int,
    "after": str,
    "projectId": str,
}
GET_FIELDS = {"id": str, "projectId": str}

TOOLS = (
    {
        "name": LIST_TOOL,
        "description": (
            "List published entries visible to this delivery token. "
            "Drafts and scheduled entries are left out. "
            "Titles and bodies are returned as stored, including Hebrew letters and niqqud."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "typeKey": {"type": "string"},
                "search": {"type": "string"},
                "sort": {"type": "string", "enum": list(SORTS)},
                "first": {"type": "integer", "minimum": 1, "maximum": 100},
                "after": {"type": "string"},
                "projectId": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    },
    {
        "name": GET_TOOL,
        "description": (
            "Get one published entry by id. "
            "Drafts and scheduled entries are left out. "
            "Titles and bodies are returned as stored, including Hebrew letters and niqqud."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "projectId": {"type": "string"}},
            "required": ["id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    },
)


class RedactingFormatter(logging.Formatter):
    """Render log lines and strip the raw delivery token from them."""

    def __init__(self, secret: str) -> None:
        super().__init__("%(message)s")
        self._secret = secret if len(secret) >= 16 else ""

    def __repr__(self) -> str:
        return "RedactingFormatter()"

    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        if self._secret:
            return rendered.replace(self._secret, "[redacted]")
        return rendered


def redact(value: str, secret: str) -> str:
    if secret and len(secret) >= 16:
        return value.replace(secret, "[redacted]")
    return value


def configure_logging(secret: str) -> None:
    LOG.handlers.clear()
    LOG.setLevel(logging.INFO)
    LOG.propagate = False
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(RedactingFormatter(secret))
    LOG.addHandler(handler)


def same_text(left: str, right: str) -> bool:
    if len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


def log_result(method: str, result: str, tool: str = "") -> None:
    if tool:
        LOG.info("mcp method=%s tool=%s result=%s", method, tool, result)
    else:
        LOG.info("mcp method=%s result=%s", method, result)


def connect() -> tuple[Any, Any, str]:
    settings = Settings().validate()
    engine, factory = database(settings.database_url)
    return engine, factory, settings.database_url


def lock_reader(session: Session, url: str) -> None:
    if url.startswith("sqlite"):
        session.execute(text("PRAGMA query_only=ON"))
    else:
        session.execute(text("SET TRANSACTION READ ONLY"))


@contextmanager
def reader(factory: Any, url: str) -> Iterator[Session]:
    session = factory()
    try:
        lock_reader(session, url)
        yield session
    finally:
        session.close()


def authenticate(session: Session, raw: str, expected_project: str | None) -> dict[str, Any] | None:
    if not raw or raw.strip() == "" or len(raw) > MAX_TOKEN_LENGTH:
        return None
    token = session.get(Token, digest(raw))
    if token is None or token.kind != "delivery" or token.expires_at <= now():
        return None
    if not isinstance(token.scopes, list):
        return None
    project_id = token.project_id or ""
    if not project_id or session.get(Project, project_id) is None:
        return None
    if expected_project is not None and not same_text(expected_project, project_id):
        return None
    return {
        "project_id": project_id,
        "delivery": True,
        "scopes": list(token.scopes),
        "role": "reader",
        "actor": token.name,
        "session": session,
    }


def _blank(value: str, label: str) -> None:
    if value.strip() == "":
        raise CmsError(f"{label} is required.")


def _arguments(
    payload: Mapping[str, Any] | None, fields: Mapping[str, type], required: tuple[str, ...] = ()
) -> dict[str, Any]:
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise CmsError("Tool arguments must be an object.")
    unknown = sorted(set(payload) - set(fields))
    if unknown:
        raise CmsError("Unknown parameter.")
    parsed: dict[str, Any] = {}
    for name, kind in fields.items():
        if name not in payload:
            if name in required:
                raise CmsError(f"{name} is required.")
            continue
        value = payload[name]
        if kind is int:
            if isinstance(value, bool) or not isinstance(value, int):
                raise CmsError(PAGE_SIZE)
            parsed[name] = value
            continue
        if not isinstance(value, str):
            raise CmsError(f"{name} must be a string.")
        parsed[name] = value
    for name in required:
        _blank(parsed.get(name, ""), name)
    if "typeKey" in parsed:
        _blank(parsed["typeKey"], "typeKey")
    if "projectId" in parsed:
        _blank(parsed["projectId"], "projectId")
    if "sort" in parsed and parsed["sort"] not in SORTS:
        raise CmsError(PAGE_SIZE)
    if "first" in parsed and not 1 <= parsed["first"] <= 100:
        raise CmsError(PAGE_SIZE)
    return parsed


def _project_pin(identity: Mapping[str, Any], arguments: Mapping[str, Any]) -> None:
    requested = arguments.get("projectId")
    if isinstance(requested, str) and not same_text(requested, identity["project_id"]):
        raise CmsError(AUTH_MESSAGE, "FORBIDDEN")


def list_published(session: Session, identity: dict[str, Any], arguments: Mapping[str, Any]) -> dict[str, Any]:
    page = entry_page(
        session,
        identity,
        type_key=arguments.get("typeKey"),
        search=arguments.get("search") or "",
        sort=arguments.get("sort") or "updated_desc",
        first=arguments.get("first", 20),
        after=arguments.get("after"),
        include_total=False,
    )
    return {"nodes": page["nodes"], "endCursor": page["endCursor"], "hasNextPage": page["hasNextPage"]}


def get_published(session: Session, identity: dict[str, Any], arguments: Mapping[str, Any]) -> dict[str, Any]:
    require(identity)
    record = load_entry(session, identity, arguments["id"])
    return entry_dict(session, identity, record)


def tool_result(request_id: Any, payload: Any, *, error: bool = False) -> dict[str, Any]:
    if error:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"content": [{"type": "text", "text": str(payload)}], "isError": True},
        }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}],
            "structuredContent": payload,
        },
    }


def call_tool(
    factory: Any,
    url: str,
    request_id: Any,
    params: Mapping[str, Any],
    raw_token: str,
    expected_project: str | None,
) -> dict[str, Any]:
    name = params.get("name")
    if not isinstance(name, str) or name not in {LIST_TOOL, GET_TOOL}:
        log_result("tools/call", "rejected", name if isinstance(name, str) else "")
        return tool_result(request_id, "Unknown tool.", error=True)
    try:
        with reader(factory, url) as session:
            identity = authenticate(session, raw_token, expected_project)
            if identity is None:
                log_result("tools/call", "denied", name)
                return tool_result(request_id, AUTH_MESSAGE, error=True)
            fields = LIST_FIELDS if name == LIST_TOOL else GET_FIELDS
            required = ("id",) if name == GET_TOOL else ()
            arguments = _arguments(params.get("arguments"), fields, required)
            _project_pin(identity, arguments)
            payload = (
                list_published(session, identity, arguments)
                if name == LIST_TOOL
                else get_published(session, identity, arguments)
            )
    except CmsError as exc:
        result = "denied" if str(exc) == AUTH_MESSAGE or exc.code == "FORBIDDEN" else "rejected"
        log_result("tools/call", result, name)
        return tool_result(request_id, AUTH_MESSAGE if result == "denied" else str(exc), error=True)
    except Exception as exc:
        LOG.error("mcp tool error type=%s", type(exc).__name__)
        log_result("tools/call", "error", name)
        return tool_result(request_id, "The request could not be completed.", error=True)
    log_result("tools/call", "ok", name)
    return tool_result(request_id, payload)


def _request_id(message: Mapping[str, Any]) -> Any:
    if "id" not in message:
        return None
    value = message["id"]
    if value is None or isinstance(value, str) or (isinstance(value, int) and not isinstance(value, bool)):
        return value
    return None


def object_params(message: Mapping[str, Any]) -> dict[str, Any]:
    params = message.get("params")
    if isinstance(params, dict):
        return params
    return {}


def handle(message: Any, factory: Any, url: str, raw_token: str, expected_project: str | None) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid request."}}
    method = message.get("method")
    request_id = _request_id(message)
    notification = "id" not in message
    if not isinstance(method, str):
        if notification:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32600, "message": "Invalid request."}}
    if method == "notifications/initialized" or method == "notifications/cancelled":
        return None
    if notification:
        return None
    if method == "ping":
        log_result(method, "ok")
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "initialize":
        params = object_params(message)
        version = params.get("protocolVersion")
        if version not in PROTOCOL_VERSIONS:
            version = PROTOCOL_VERSIONS[0]
        log_result(method, "ok")
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": (
                    "Read published entries for the configured delivery token. "
                    "Drafts and scheduled entries are not returned. "
                    "Titles and bodies are returned as stored, including Hebrew letters and niqqud. "
                    "This server does not edit content."
                ),
            },
        }
    if method == "tools/list":
        log_result(method, "ok")
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": list(TOOLS)}}
    if method == "tools/call":
        if factory is None:
            log_result(method, "error")
            return tool_result(request_id, "The request could not be completed.", error=True)
        return call_tool(factory, url, request_id, object_params(message), raw_token, expected_project)
    log_result(method, "unknown")
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found."}}


def emit(stdout: TextIO, message: dict[str, Any], secret: str) -> None:
    error = message.get("error")
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        error["message"] = redact(error["message"], secret)
    result = message.get("result")
    if isinstance(result, dict) and result.get("isError") is True:
        for block in result.get("content") or []:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                block["text"] = redact(block["text"], secret)
    stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
    stdout.flush()


def serve(stdin: TextIO, stdout: TextIO) -> None:
    raw_token = os.environ.get(TOKEN_ENV, "")
    configure_logging(raw_token)
    expected_project = os.environ.get(PROJECT_ENV, "").strip() or None
    engine = None
    factory = None
    url = ""
    try:
        try:
            engine, factory, url = connect()
        except Exception as exc:
            LOG.error("mcp database unavailable type=%s", type(exc).__name__)
        for line in stdin:
            if not line.strip():
                continue
            try:
                incoming = json.loads(line)
            except json.JSONDecodeError:
                emit(
                    stdout,
                    {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error."}},
                    raw_token,
                )
                continue
            outgoing = handle(incoming, factory, url, raw_token, expected_project)
            if outgoing is not None:
                emit(stdout, outgoing, raw_token)
    finally:
        if engine is not None:
            engine.dispose()


def main() -> None:
    if len(sys.argv) > 1:
        sys.stderr.write("MOSS_DELIVERY_TOKEN is read from the environment.\n")
        raise SystemExit(2)
    from dotenv import load_dotenv

    load_dotenv(override=False)
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (AttributeError, OSError, ValueError):
            pass
    try:
        serve(sys.stdin, sys.stdout)
    except BrokenPipeError:
        raise SystemExit(0) from None
    except Exception as exc:
        logging.getLogger("mosscms.mcp").error("mcp stopped type=%s", type(exc).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
