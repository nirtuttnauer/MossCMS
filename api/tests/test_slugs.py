"""Unicode slug rules, shared with the admin and example-site suites."""

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import Entry
from app.security import CmsError
from app.slugs import (
    SLUG_MAX_BYTES,
    SLUG_MAX_CHARS,
    STRIP_RANGES,
    allows_scripts,
    canonical_slug,
    encode_website_path,
    slugify,
)
from conftest import define, entry, gql
from test_cms import delivery

VECTORS = json.loads((Path(__file__).resolve().parents[2] / "shared" / "slug-vectors.json").read_text(encoding="utf-8"))
CASEFOLD = json.loads((Path(__file__).resolve().parents[2] / "shared" / "casefold.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", VECTORS["cases"], ids=[item["id"] for item in VECTORS["cases"]])
def test_shared_slug_vectors(case):
    if "slug" in case:
        assert slugify(case["input"]) == case["slug"]
        assert canonical_slug(case["input"]) == case["slug"]
        assert slugify(case["slug"]) == case["slug"]
    else:
        assert case["error"] == "invalid_slug"
        with pytest.raises(CmsError) as caught:
            slugify(case["input"])
        assert caught.value.reason == "invalid_slug"
    if "encoded" in case:
        assert encode_website_path(case["slug"]) == case["encoded"]
    if "websitePath" in case:
        prefix = "/blog/" if case["websitePath"].startswith("/blog/") else "/"
        assert encode_website_path(prefix + case["slug"]) == case["websitePath"]


def test_vector_limits_match_the_server():
    assert VECTORS["limits"] == {"characters": SLUG_MAX_CHARS, "utf8Bytes": SLUG_MAX_BYTES}
    assert [(int(start, 16), int(end, 16)) for start, end in VECTORS["stripRanges"]] == list(STRIP_RANGES)


@pytest.mark.parametrize("start,end", STRIP_RANGES, ids=["200B-200F", "202A-202E", "2066-2069", "FEFF"])
def test_each_bidi_and_zero_width_range_is_stripped(start, end):
    for code in range(start, end + 1):
        assert slugify(f"ab{chr(code)}cd") == "abcd"


def test_allowing_two_scripts_is_rejected():
    """Hebrew + Arabic must fail. A mutation that allows any two scripts fails here."""
    assert allows_scripts({"Latin", "Hebrew"})
    assert allows_scripts({"Cyrillic"})
    assert allows_scripts({"Greek"})
    assert allows_scripts(set())
    assert not allows_scripts({"Hebrew", "Arabic"})
    assert not allows_scripts({"Latin", "Cyrillic"})
    assert not allows_scripts({"Latin", "Greek"})
    assert not allows_scripts({"Latin", "Hebrew", "Arabic"})
    with pytest.raises(CmsError) as caught:
        slugify("שלוםمرحبا")
    assert caught.value.reason == "invalid_slug"
    assert slugify("nextjs-מדריך") == "nextjs-מדריך"


def test_byte_limit_is_nfc_utf8_before_percent_encoding():
    exact = "一" * 200
    assert len(exact.encode("utf-8")) == SLUG_MAX_BYTES
    assert len(encode_website_path(exact)) > SLUG_MAX_BYTES
    assert slugify(exact) == exact
    over = exact + "a"
    assert len(over.encode("utf-8")) == SLUG_MAX_BYTES + 1
    assert len(over) <= SLUG_MAX_CHARS
    assert slugify("一a") == "一a"
    with pytest.raises(CmsError) as caught:
        slugify(over)
    assert caught.value.reason == "invalid_slug"
    assert slugify("a" * SLUG_MAX_CHARS) == "a" * SLUG_MAX_CHARS
    with pytest.raises(CmsError) as caught:
        slugify("a" * (SLUG_MAX_CHARS + 1))
    assert caught.value.reason == "invalid_slug"
    hebrew = "א" * SLUG_MAX_CHARS
    assert len(hebrew.encode("utf-8")) < SLUG_MAX_BYTES
    assert slugify(hebrew) == hebrew
    with pytest.raises(CmsError) as caught:
        slugify(hebrew + "א")
    assert caught.value.reason == "invalid_slug"


def test_casefold_table_matches_python():
    expected = {}
    for code in range(0x110000):
        character = chr(code)
        folded = character.casefold()
        if folded != character:
            expected[format(code, "x")] = folded
    assert CASEFOLD["folds"] == expected


def test_encoded_and_raw_forms_are_one_entry_and_double_encoding_is_rejected(client, admin):
    define(client, admin)
    saved = entry(client, admin, slug="מדריך-התקנה", status="published")
    assert saved["data"]["saveEntry"]["slug"] == "מדריך-התקנה"
    encoded = "%D7%9E%D7%93%D7%A8%D7%99%D7%9A-%D7%94%D7%AA%D7%A7%D7%A0%D7%94"
    conflict = entry(client, admin, slug=encoded, status="published")
    assert conflict["errors"][0]["extensions"]["reason"] == "slug_conflict"
    rejected = entry(client, admin, slug="%25D7%259E")
    assert rejected["errors"][0]["extensions"]["reason"] == "invalid_slug"
    listed = gql(client, admin, "{entries{total nodes{slug}}}")["data"]["entries"]
    assert listed["total"] == 1
    assert listed["nodes"][0]["slug"] == "מדריך-התקנה"


def test_zero_width_and_nfd_slugs_collide_with_the_normalized_slug(client, admin):
    define(client, admin)
    first = entry(client, admin, slug="\ufb2a")
    assert first["data"]["saveEntry"]["slug"] == "\u05e9\u05c1"
    collided = entry(client, admin, slug="\u05e9\u05c1")
    assert collided["errors"][0]["extensions"]["reason"] == "slug_conflict"
    plain = entry(client, admin, slug="hello")
    assert "errors" not in plain
    for code in {start for start, _end in STRIP_RANGES} | {end for _start, end in STRIP_RANGES}:
        dirty = entry(client, admin, slug=f"hello{chr(code)}")
        assert dirty["errors"][0]["extensions"]["reason"] == "slug_conflict"
    assert gql(client, admin, "{entries{total}}")["data"]["entries"]["total"] == 2


def test_hebrew_slug_publishes_and_website_paths_are_percent_encoded(client, admin):
    define(client, admin, "sitePost", [{"name": "title", "type": "text"}])
    saved = entry(client, admin, key="sitePost", slug="מדריך התקנה", data={"title": "מדריך"}, status="published")
    assert saved["data"]["saveEntry"]["slug"] == "מדריך-התקנה"
    token = delivery(client, admin)
    delivered = gql(
        client,
        token,
        "{entries{nodes{slug}} websiteReservedPaths websiteRedirects}",
        delivery=True,
    )["data"]
    assert delivered["entries"]["nodes"][0]["slug"] == "מדריך-התקנה"
    encoded = "/blog/%D7%9E%D7%93%D7%A8%D7%99%D7%9A-%D7%94%D7%AA%D7%A7%D7%A0%D7%94"
    assert delivered["websiteReservedPaths"] == [encoded]
    assert delivered["websiteRedirects"] == []
    assert client.get("/delivery/website/reserved-paths", headers=token).json() == [encoded]
    renamed = entry(
        client,
        admin,
        key="sitePost",
        slug="nextjs-מדריך",
        data={"title": "Next"},
        status="published",
        id=saved["data"]["saveEntry"]["id"],
        version=saved["data"]["saveEntry"]["version"],
    )["data"]["saveEntry"]
    redirects = gql(client, token, "{websiteRedirects}", delivery=True)["data"]["websiteRedirects"]
    assert redirects == [
        {"from": encoded, "to": "/blog/nextjs-%D7%9E%D7%93%D7%A8%D7%99%D7%9A", "entryId": renamed["id"]}
    ]


def test_stored_slugs_are_not_rewritten_on_read(app, client, admin):
    define(client, admin)
    saved = entry(client, admin, slug="hello")["data"]["saveEntry"]
    with app.state.db.begin() as session:
        record = session.scalar(select(Entry).where(Entry.id == saved["id"]))
        record.slug = "Not-Normalized"
    loaded = gql(client, admin, "query($id:ID!){entry(id:$id){slug}}", {"id": saved["id"]})
    assert loaded["data"]["entry"]["slug"] == "Not-Normalized"


def test_traversal_inputs_cannot_remain_in_a_slug():
    assert slugify("foo/bar") == "foo-bar"
    assert slugify("foo%2Fbar") == "foo-bar"
    for sample in ("..", "%2F", "..%2F..", "%2e%2e%2f%2e%2e"):
        with pytest.raises(CmsError) as caught:
            slugify(sample)
        assert caught.value.reason == "invalid_slug"
    slug = slugify("safe")
    assert "/" not in slug and "%" not in slug and ".." not in slug
