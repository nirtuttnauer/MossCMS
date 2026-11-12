"""Secret-shaped example, default, and description samples stay out of the OpenAPI document."""

import json
import re
from typing import Any

import pytest

from app.openapi_schema import OPENAPI_PATH, build_openapi

# Fake markers are split across string parts so this source file has no contiguous
# secret-shaped literal. The scan looks at document text, not at these parts.

_SAMPLE_KEYS = frozenset({"example", "examples", "default"})


def _marker(*parts: str) -> str:
    return "".join(parts)


def _patterns() -> tuple[tuple[str, re.Pattern[str]], ...]:
    api_key = (
        r"(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9][A-Za-z0-9_\-]{3,}|sk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{8,}"
    )
    github = r"(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{4,}"
    cloud = r"(?:AKIA|ASIA|ABIA|ACCA)[A-Z0-9]{16}|AIza[0-9A-Za-z_\-]{10,}|ya29\.[0-9A-Za-z_\-]+"
    chat_bot = r"xox[baprs]-[A-Za-z0-9\-]{4,}|\b\d{6,12}:[A-Za-z0-9_\-]{8,}"
    password = (
        r"""(?i)(?<![A-Za-z0-9])["']?(?:password|passwd|pwd)["']?(?![A-Za-z0-9])"""
        r"""\s*[:=]\s*["']?[^\s"']{4,}"""
    )
    private_key = "-----BEGIN " + r"(?:(?:RSA|DSA|EC|OPENSSH|ENCRYPTED) )?PRIVATE KEY-----"
    compiled = (
        ("api-key", api_key),
        ("github-token", github),
        ("cloud-token", cloud),
        ("chat-bot-token", chat_bot),
        ("password-assignment", password),
        ("private-key-armor", private_key),
    )
    return tuple((kind, re.compile(expression)) for kind, expression in compiled)


_PATTERNS = _patterns()


def _token(key: object) -> str:
    return "/" + str(key).replace("~", "~0").replace("/", "~1")


def _scan_text(text: str, pointer: str, found: list[tuple[str, str]]) -> None:
    for kind, pattern in _PATTERNS:
        if pattern.search(text):
            found.append((kind, pointer))


def _scan_sample(node: Any, pointer: str, found: list[tuple[str, str]]) -> None:
    if isinstance(node, str):
        _scan_text(node, pointer, found)
    elif isinstance(node, dict):
        for key, value in node.items():
            _scan_sample(value, pointer + _token(key), found)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _scan_sample(value, f"{pointer}/{index}", found)


def _walk(node: Any, pointer: str, found: list[tuple[str, str]]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            child = pointer + _token(key)
            if key in _SAMPLE_KEYS:
                _scan_sample(value, child, found)
            elif key == "description" and isinstance(value, str):
                _scan_text(value, child, found)
            else:
                _walk(value, child, found)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _walk(value, f"{pointer}/{index}", found)


def find_secret_shaped_samples(document: Any) -> list[tuple[str, str]]:
    """Return (kind, JSON pointer) for secret-shaped example, default, or description text."""
    found: list[tuple[str, str]] = []
    _walk(document, "", found)
    return found


def assert_no_secret_shaped_samples(document: Any) -> None:
    findings = find_secret_shaped_samples(document)
    rendered = "\n".join(f"{kind} at {pointer}" for kind, pointer in findings)
    assert not findings, "Secret-shaped OpenAPI sample\n" + rendered


def _plant(location: str, value: str) -> dict[str, Any]:
    if location == "examples":
        field: dict[str, Any] = {"type": "string", "examples": {"sample": {"value": value}}}
    elif location == "example-object":
        field = {"type": "string", "example": {"nested": value}}
    elif location == "description":
        field = {"type": "string", "description": "Sample " + value}
    else:
        field = {"type": "string", location: value}
    return {"components": {"schemas": {"Sample": {"properties": {"field": field}}}}}


def _pointer_has(message: str, location: str) -> bool:
    if location == "examples":
        return "/examples" in message
    if location in {"example", "example-object"}:
        return "/example" in message
    return f"/{location}" in message


def test_committed_and_generated_openapi_have_no_secret_shaped_samples(app):
    assert OPENAPI_PATH.name == "openapi.json"
    assert OPENAPI_PATH.is_file()
    committed = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert_no_secret_shaped_samples(committed)
    assert_no_secret_shaped_samples(build_openapi(app))


def test_ordinary_copy_and_non_sample_fields_stay():
    marker = _marker("sk_", "live_", "example")
    document = {
        "info": {"title": marker, "summary": marker},
        "paths": {"/items": {"get": {"operationId": marker, "summary": marker}}},
        "components": {
            "schemas": {
                "Sample": {
                    "description": "A delivery token is required. The password field is a string.",
                    "properties": {
                        "name": {
                            "type": "string",
                            "title": marker,
                            "pattern": marker,
                            "example": "article",
                            "default": "updated_desc",
                            "description": "Optional content type key.",
                        },
                        "limit": {"type": "integer", "default": 20},
                        "flag": {"type": "boolean", "default": False},
                        "note": {"type": "string", "default": ""},
                    },
                }
            }
        },
    }
    assert_no_secret_shaped_samples(document)
    assert_no_secret_shaped_samples({})


@pytest.mark.parametrize(
    ("location", "kind", "value"),
    [
        ("example", "api-key", _marker("sk_", "live_", "example")),
        ("example", "api-key", _marker("sk-", "examplemarker")),
        ("example", "private-key-armor", _marker("-----BEGIN ", "PRIVATE KEY-----")),
        ("default", "github-token", _marker("ghp_", "example")),
        ("example", "github-token", _marker("github_pat_", "example")),
        ("example", "cloud-token", _marker("AKIA", "EXAMPLEKEY000000")),
        ("example", "cloud-token", _marker("AIza", "examplemark")),
        ("example", "cloud-token", _marker("ya29.", "example")),
        ("description", "chat-bot-token", _marker("xoxb-", "example")),
        ("example", "chat-bot-token", _marker("123456:", "examplemarker")),
        ("example", "password-assignment", _marker("password=", "example-marker")),
        ("description", "password-assignment", _marker("password", ": ", "example-marker")),
        ("examples", "private-key-armor", _marker("-----BEGIN ", "RSA ", "PRIVATE KEY-----")),
        ("example-object", "api-key", _marker("pk_", "live_", "example")),
    ],
    ids=[
        "api-key-example",
        "api-key-sk-prefix-example",
        "private-key-example",
        "github-token-default",
        "github-pat-example",
        "cloud-access-key-example",
        "cloud-api-key-example",
        "cloud-oauth-example",
        "chat-bot-token-description",
        "chat-bot-numeric-example",
        "password-assignment-example",
        "password-assignment-description",
        "private-key-examples-value",
        "api-key-nested-example",
    ],
)
def test_planted_secret_shaped_sample_fails_the_scan(location, kind, value):
    with pytest.raises(AssertionError, match=re.escape(kind)) as caught:
        assert_no_secret_shaped_samples(_plant(location, value))
    message = str(caught.value)
    assert value not in message
    assert _pointer_has(message, location)
