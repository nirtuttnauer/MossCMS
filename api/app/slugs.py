"""Unicode slugs. NFC, casefold, and UTS #39 script limits. No extra dependencies."""

import json
import re
import unicodedata
import urllib.parse
from pathlib import Path

from .security import CmsError

# Character length stays the column width. The byte limit is the NFC UTF-8 form
# of that slug, counted before percent-encoding, so encoded website paths stay bounded.
SLUG_MAX_CHARS = 220
SLUG_MAX_BYTES = 600
# U+200B–U+200F, U+202A–U+202E, U+2066–U+2069, and U+FEFF. Stripped before NFC.
STRIP_RANGES = ((0x200B, 0x200F), (0x202A, 0x202E), (0x2066, 0x2069), (0xFEFF, 0xFEFF))
_STRIP = {code for start, end in STRIP_RANGES for code in range(start, end + 1)}
_DOUBLE_ENCODED = re.compile(r"%25", re.IGNORECASE)
_BROKEN_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_DASHES = re.compile(r"-+")
_INVALID = "Slug must contain letters or numbers, use at most Latin plus one other script (not Cyrillic or Greek), and stay within 220 characters and 600 UTF-8 bytes."

_SHARED = Path(__file__).resolve().parents[2] / "shared" / "unicode-scripts.json"
_RANGES: list[tuple[int, int, str]] = [
    (int(start), int(end), str(name)) for start, end, name in json.loads(_SHARED.read_text(encoding="utf-8"))["ranges"]
]


def _invalid() -> CmsError:
    return CmsError(_INVALID, field_path="slug", reason="invalid_slug")


def script_of(character: str) -> str | None:
    """Unicode Script property, ignoring Common and Inherited."""
    code = ord(character)
    low, high = 0, len(_RANGES)
    while low < high:
        mid = (low + high) // 2
        start, end, name = _RANGES[mid]
        if code < start:
            high = mid
        elif code > end:
            low = mid + 1
        else:
            return name
    return None


def scripts_of(slug: str) -> set[str]:
    found: set[str] = set()
    for character in slug:
        if character == "-":
            continue
        script = script_of(character)
        if script:
            found.add(script)
    return found


def allows_scripts(scripts: set[str]) -> bool:
    """Latin plus at most one other script. Latin with Cyrillic or Greek is rejected.

    Digits and hyphens are Common and are not part of ``scripts``. Allowing a
    second non-Latin script (Hebrew + Arabic) fails the shared vectors.
    """
    others = scripts - {"Latin"}
    if len(others) > 1:
        return False
    if "Latin" in scripts and others & {"Cyrillic", "Greek"}:
        return False
    return True


def _decode_once(value: str) -> str:
    if _DOUBLE_ENCODED.search(value) or _BROKEN_ESCAPE.search(value):
        raise _invalid()
    if "%" not in value:
        return value
    try:
        return urllib.parse.unquote_to_bytes(value).decode("utf-8")
    except UnicodeDecodeError:
        raise _invalid() from None


def _kept(character: str) -> bool:
    return unicodedata.category(character)[:1] in {"L", "M", "N"}


def _normalize(value: str) -> str:
    text = _decode_once(value)
    stripped = "".join(character for character in text if ord(character) not in _STRIP)
    folded = unicodedata.normalize("NFC", stripped).casefold()
    mapped = "".join(character if _kept(character) else "-" for character in folded)
    return _DASHES.sub("-", mapped).strip("-")


def canonical_slug(value: str) -> str:
    """Normalize without applying the length or script limits."""
    if not isinstance(value, str):
        return ""
    try:
        return _normalize(value)
    except CmsError:
        return ""


def slugify(value: str) -> str:
    if not isinstance(value, str):
        raise _invalid()
    slug = _normalize(value)
    if (
        not slug
        or len(slug) > SLUG_MAX_CHARS
        or len(slug.encode("utf-8")) > SLUG_MAX_BYTES
        or not allows_scripts(scripts_of(slug))
    ):
        raise _invalid()
    return slug


def encode_website_path(path: str) -> str:
    """RFC 3986 percent-encoding with uppercase hex, matching MOSS-031's ``%02X`` form."""
    if not path:
        return path
    return urllib.parse.quote(path, safe="/")
