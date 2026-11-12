"""Classify every FastAPI route as public or private and render the doc table.

A route that matches no rule is unclassified. The public rules are an allowlist.
Everything else that this module names is private. Run from api/:

    uv run python scripts/classify_routes.py --check
    uv run python scripts/classify_routes.py --write
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
DOC = ROOT / "docs" / "client-hardening.md"
START = "<!-- moss-route-classification:start -->"
END = "<!-- moss-route-classification:end -->"

PUBLIC = "public"
PRIVATE = "private"


class UnclassifiedRoute(Exception):
    """A router entry matches neither the public allowlist nor a private rule."""


class MissingRoute(Exception):
    """A classified route is not on the router."""


@dataclass(frozen=True, order=True)
class RouteKey:
    method: str
    path: str

    def label(self):
        return f"{self.method} {self.path}"


def _join(prefix, path):
    if not prefix:
        return path
    return prefix.rstrip("/") + "/" + path.lstrip("/")


def _collect(route, prefix, found):
    if type(route).__name__ == "_IncludedRouter":
        nested = getattr(route.include_context, "prefix", "") or ""
        for child in route.original_router.routes:
            _collect(child, _join(prefix, nested), found)
        return
    path = getattr(route, "path", None)
    if not path:
        return
    full = _join(prefix, path)
    methods = getattr(route, "methods", None) or {"GET", "HEAD"}
    for method in methods:
        found.add(RouteKey(method, full))


def route_keys(app):
    found = set()
    for route in app.routes:
        _collect(route, "", found)
    return sorted(found)


def exposure(method, path):
    """Return public, private, or None when the route has no class."""
    if path == "/health" and method == "GET":
        return PUBLIC
    if method == "GET" and path in {"/media/{id}", "/media/{id}/variant/{width}"}:
        return PUBLIC
    if path == "/delivery" or path.startswith("/delivery/"):
        return PUBLIC
    if path == "/":
        return PRIVATE
    private_roots = (
        "/auth",
        "/api/",
        "/graphql",
        "/metrics",
        "/ready",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/assets",
        "/brand",
    )
    for root in private_roots:
        if path == root or path.startswith(root + "/") or (root.endswith("/") and path.startswith(root)):
            return PRIVATE
    return None


def classify(keys):
    classified = {}
    for key in keys:
        kind = exposure(key.method, key.path)
        if kind is None:
            raise UnclassifiedRoute(key.label())
        classified[key] = kind
    return classified


def assert_closed(classification, keys):
    """Fail when a router route has no class, or a class has left the router."""
    live = classify(keys)
    missing = [key.label() for key in classification if key not in live]
    if missing:
        raise MissingRoute(", ".join(sorted(missing)))
    extra = [key.label() for key in live if key not in classification]
    if extra:
        raise UnclassifiedRoute(", ".join(sorted(extra)))
    return live


def render_table(classification):
    lines = ["| Method | Path | Exposure |", "| --- | --- | --- |"]
    for key in sorted(classification):
        lines.append(f"| {key.method} | `{key.path}` | {classification[key]} |")
    return "\n".join(lines) + "\n"


def documented_table(text=None):
    body = DOC.read_text() if text is None else text
    start = body.index(START) + len(START)
    end = body.index(END)
    return body[start:end].strip() + "\n"


def load_app():
    storage = Path(os.environ.get("MOSS_CLASSIFY_STORAGE", "/tmp/moss-route-classify"))
    storage.mkdir(parents=True, exist_ok=True)
    from app.config import Settings
    from app.main import create_app

    # Settings carries every value, so the caller's environment is left unchanged.
    # Setting MOSS_USE_SQLITE here would switch later Settings() in the same process to SQLite.
    return create_app(
        Settings(
            secret=os.environ.get("MOSS_SECRET_KEY") or "s" * 40,
            setup_token=os.environ.get("MOSS_SETUP_TOKEN") or "t" * 30,
            storage_dir=storage,
            use_sqlite=True,
        )
    )


def current_table():
    app = load_app()
    return render_table(classify(route_keys(app)))


def write_doc(table):
    body = DOC.read_text()
    start = body.index(START) + len(START)
    end = body.index(END)
    updated = body[:start] + "\n" + table + body[end:]
    DOC.write_text(updated)


def main(argv):
    table = current_table()
    if "--write" in argv:
        write_doc(table)
        return 0
    if "--check" in argv:
        documented = documented_table()
        if documented != table:
            sys.stderr.write("route table in docs/client-hardening.md does not match the router\n")
            return 1
        return 0
    sys.stdout.write(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
