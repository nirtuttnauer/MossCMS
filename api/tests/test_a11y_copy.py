"""UI and doc strings must not use the forbidden accessibility spelling."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Assembled so this file does not contain the spelling it rejects.
NEEDLE = "compl" + "iant"
SUFFIXES = {".py", ".ts", ".tsx", ".md", ".html", ".mjs", ".css", ".json"}
SCAN = [
    ROOT / "docs",
    ROOT / "web" / "src",
    ROOT / "example-site" / "src",
    ROOT / "example-site" / "server",
    ROOT / "example-site" / "index.html",
    ROOT / "example-site" / "README.md",
    ROOT / "api" / "app",
]


def test_ui_and_docs_omit_forbidden_word():
    hits = []
    for target in SCAN:
        paths = [target] if target.is_file() else target.rglob("*")
        for path in paths:
            if not path.is_file() or path.suffix not in SUFFIXES or "node_modules" in path.parts:
                continue
            if NEEDLE in path.read_text(encoding="utf-8", errors="ignore"):
                hits.append(str(path.relative_to(ROOT)))
    assert hits == []
