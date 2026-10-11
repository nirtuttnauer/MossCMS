import base64
import json
from datetime import timedelta

import pytest

from app.models import Asset, Entry, now
from conftest import define, entry, gql
from test_cms import delivery, invited

FIELDS = [
    {"name": "title", "type": "text"},
    {"name": "description", "type": "text"},
    {"name": "body", "type": "richText"},
]
REPORT = "snapshot revision recordCount pageCount supportingCount needsMappingCount noLiveCount criticalCount warningCount infoCount total endCursor hasNextPage notChecked mappings{typeKey kind titlePath descriptionPath} findings{code severity entryId typeKey snapshot revision fieldPath locale explanation}"


def report(client, headers, snapshot="draft", **variables):
    result = gql(
        client,
        headers,
        "query($snapshot:String!,$after:String,$first:Int!,$type:String,$severity:String){seoAudit(snapshot:$snapshot,after:$after,first:$first,typeKey:$type,severity:$severity){"
        + REPORT
        + "}}",
        {"snapshot": snapshot, "first": 100, **variables},
    )
    assert "errors" not in result, result
    return result["data"]["seoAudit"]


def saved(client, headers, **kwargs):
    result = entry(client, headers, **kwargs)
    assert "errors" not in result, result
    return result["data"]["saveEntry"]


def codes(result):
    return {f["code"] for f in result["findings"]}


def test_draft_fixes_do_not_hide_live_issues_and_schedules_are_excluded(client, admin):
    define(client, admin, fields=FIELDS)
    live = saved(client, admin, status="published", data={"title": "", "description": ""})
    changed = saved(
        client,
        admin,
        id=live["id"],
        version=1,
        status="scheduled",
        scheduledAt=(now() + timedelta(days=1)).isoformat(),
        data={"title": "Captured", "description": "Captured"},
    )
    saved(
        client,
        admin,
        id=live["id"],
        version=changed["version"],
        data={"title": "Good draft", "description": "Useful summary"},
    )
    assert "missing_title" not in codes(report(client, admin))
    result = report(client, admin, "live")
    assert {"missing_title", "missing_description"} <= codes(result)
    assert {f["revision"] for f in result["findings"]} == {1}
    assert {f["snapshot"] for f in result["findings"]} == {"live"}
    assert "Captured schedules" in result["notChecked"]
    live_entry = gql(
        client, admin, "query($id:ID!){entry(id:$id){publishedData scheduledRevision}}", {"id": live["id"]}
    )["data"]["entry"]
    assert live_entry["publishedData"]["title"] == ""
    assert live_entry["scheduledRevision"] == 2


def test_no_live_snapshot_and_trash(client, admin):
    define(client, admin, fields=FIELDS)
    draft = saved(client, admin, data={"title": "Draft", "description": "Summary"})
    trashed = saved(client, admin, slug="trash", data={"title": "Trash"})
    gql(client, admin, "mutation($id:ID!){deleteEntry(id:$id,version:1)}", {"id": trashed["id"]})
    assert report(client, admin, "live")["recordCount"] == 0
    assert report(client, admin, "live")["noLiveCount"] == 1
    assert report(client, admin)["recordCount"] == 1
    result = gql(
        client, admin, 'query($id:ID!){seoEntryAudit(id:$id,snapshot:"live"){' + REPORT + "}}", {"id": draft["id"]}
    )["data"]["seoEntryAudit"]
    assert result["revision"] is None and result["total"] == 0


def test_duplicates_cover_complete_workspace_before_filters_and_pagination(app, client, admin):
    definition = define(client, admin, fields=FIELDS)
    with app.state.db.begin() as session:
        session.add_all(
            [
                Entry(
                    project_id=admin["x-moss-project"],
                    type_id=definition["id"],
                    slug=f"page-{i}",
                    title="Shared title",
                    data={"title": "Shared title", "description": f"Description {i}", "body": "Useful content"},
                )
                for i in range(105)
            ]
        )
    first = report(client, admin, first=20, severity="warning")
    assert first["recordCount"] == first["warningCount"] == first["total"] == 105
    assert len(first["findings"]) == 20 and first["hasNextPage"]
    found = set()
    current = first
    while True:
        found.update(f["entryId"] for f in current["findings"])
        assert all("105 pages" in f["explanation"] for f in current["findings"])
        if not current["hasNextPage"]:
            break
        current = report(client, admin, first=20, severity="warning", after=current["endCursor"])
    assert len(found) == 105
    single = gql(
        client, admin, "query($id:ID!){seoEntryAudit(id:$id){findings{code} total}}", {"id": next(iter(found))}
    )["data"]["seoEntryAudit"]
    assert single["total"] == 1 and single["findings"][0]["code"] == "duplicate_title"


def test_nested_localized_mapping_and_private_values_are_excluded(client, admin):
    define(
        client,
        admin,
        fields=[
            {
                "name": "seo",
                "type": "object",
                "localized": True,
                "fields": [{"name": "title", "type": "text"}, {"name": "description", "type": "text"}],
            },
            {"name": "seoTitle", "type": "text"},
            {"name": "secret", "type": "richText", "private": True},
            {
                "name": "items",
                "type": "list",
                "item": {"type": "object", "fields": [{"name": "copy", "type": "richText", "localized": True}]},
            },
        ],
    )
    saved(
        client,
        admin,
        data={
            "seo": {"en": {"title": "", "description": "Unique"}, "he": {"title": "כותרת", "description": "תיאור"}},
            "seoTitle": "Lower priority",
            "secret": "# Secret\n![hidden](asset:missing)",
            "items": [{"copy": {"he": "## כותרת\n#### תת כותרת\n![](asset:missing)"}}],
        },
    )
    result = report(client, admin)
    assert result["mappings"][0]["titlePath"] == "seo.title"
    assert any(f["code"] == "missing_title" and f["fieldPath"] == "data.seo.en.title" for f in result["findings"])
    assert any(
        f["code"] == "unavailable_asset" and f["fieldPath"] == "data.items[0].copy.he" and f["locale"] == "he"
        for f in result["findings"]
    )
    assert not any((f["fieldPath"] or "").startswith("data.secret") for f in result["findings"])
    assert not any(f["code"] == "extra_h1" for f in result["findings"])


def test_supporting_types_unknown_mapping_and_private_parent(client, admin):
    define(client, admin, key="siteSlide", fields=FIELDS)
    saved(client, admin, key="siteSlide", data={"body": "![](asset:missing)"})
    define(
        client,
        admin,
        key="unknown",
        fields=[
            {
                "name": "seo",
                "type": "object",
                "private": True,
                "fields": [{"name": "title", "type": "text"}, {"name": "description", "type": "text"}],
            }
        ],
    )
    saved(client, admin, key="unknown", data={"seo": {"title": "Secret", "description": "Secret"}})
    result = report(client, admin)
    assert result["supportingCount"] == result["needsMappingCount"] == 1
    slide = [f for f in result["findings"] if f["typeKey"] == "siteSlide"]
    assert not any(f["code"] == "missing_title" for f in slide)
    assert "needs_mapping" in codes(result) and "unavailable_asset" in codes(result)
    mapping = next(m for m in result["mappings"] if m["typeKey"] == "unknown")
    assert mapping["titlePath"] is mapping["descriptionPath"] is None


def test_website_profile_fallbacks_are_compared_but_not_missing_effective_metadata(client, admin):
    define(
        client,
        admin,
        key="siteProfile",
        fields=[{"name": "name", "type": "text"}, {"name": "headline", "type": "text"}],
    )
    saved(
        client,
        admin,
        key="siteProfile",
        slug="profile",
        status="published",
        data={"name": "Nir", "headline": "Shared website headline"},
    )
    define(
        client, admin, key="sitePage", fields=FIELDS + [{"name": "kind", "type": "enum", "options": ["home", "page"]}]
    )
    saved(client, admin, key="sitePage", slug="home", status="published", data={"title": "Home", "kind": "home"})
    saved(client, admin, key="sitePage", slug="about", status="published", data={"title": "About", "kind": "page"})
    result = report(client, admin, "live")
    missing = [f for f in result["findings"] if f["code"] == "missing_description"]
    assert len(missing) == 2 and all(f["severity"] == "warning" and "fallback" in f["explanation"] for f in missing)
    assert "duplicate_description" in codes(result) and result["criticalCount"] == 0


def test_generic_website_fallbacks_match_the_example_site(client, admin):
    define(client, admin, key="sitePage", fields=FIELDS)
    saved(client, admin, key="sitePage", slug="empty", data={"title": "", "description": ""})
    saved(
        client,
        admin,
        key="sitePage",
        slug="explicit",
        data={"title": "Example website", "description": "A example website."},
    )
    result = report(client, admin)
    assert {"duplicate_title", "duplicate_description"} <= codes(result)
    assert result["criticalCount"] == 0


def test_markdown_reference_images_setext_headings_and_code_blocks(client, admin):
    define(client, admin, key="sitePost", fields=FIELDS)
    saved(
        client,
        admin,
        key="sitePost",
        data={
            "title": "Post",
            "description": "Post summary",
            "body": "Article heading\n=====\n\n#### Skipped\n\n![][cover]\n\n[cover]: asset:missing\n\n```md\n# ignored\n![ignored](asset:ignored)\n```\n\n<img src='asset:ignored'>",
        },
    )
    result = report(client, admin)
    assert {"extra_h1", "skipped_heading_level", "missing_image_description", "unavailable_asset"} <= codes(result)
    assert sum(f["code"] == "unavailable_asset" for f in result["findings"]) == 1


def test_assets_and_references_are_scoped_and_live_availability_is_checked(app, client, admin):
    image_fields = [{"name": "asset", "type": "asset"}, {"name": "alt", "type": "text"}]
    definition = define(
        client,
        admin,
        fields=FIELDS
        + [
            {"name": "gallery", "type": "list", "item": {"type": "object", "fields": image_fields}},
            {"name": "related", "type": "reference"},
        ],
    )
    target = saved(client, admin, slug="target", data={"title": "Target", "description": "Target summary"})
    with app.state.db.begin() as session:
        asset = Asset(
            project_id=admin["x-moss-project"], name="Image", key="image", storage="local", mime="image/png", size=1
        )
        session.add(asset)
        session.flush()
        asset_id = asset.id
    source = saved(
        client,
        admin,
        slug="source",
        status="published",
        data={
            "title": "Source",
            "description": "Source summary",
            "gallery": [{"asset": asset_id, "alt": ""}],
            "related": target["id"],
        },
    )
    result = report(client, admin, "live")
    assert "unavailable_reference" in codes(result)
    assert any(
        f["code"] == "missing_image_description" and f["fieldPath"] == "data.gallery[0].alt" for f in result["findings"]
    )
    assert "unavailable_reference" not in codes(report(client, admin))
    with app.state.db.begin() as session:
        session.delete(session.get(Asset, asset_id))
    assert "unavailable_asset" in codes(report(client, admin))
    assert definition["id"] and source["id"]


def test_reader_access_delivery_rejection_and_workspace_isolation(app, client, admin):
    define(client, admin, fields=FIELDS)
    original = saved(client, admin, status="published", data={"title": "", "description": ""})
    reader, headers, _ = invited(app, client, admin, role="reader")
    assert report(reader, headers)["recordCount"] == 1
    token = delivery(client, admin)
    response = gql(client, token, "{seoAudit{total}}", delivery=True)
    assert response["errors"][0]["extensions"]["code"] == "FORBIDDEN"
    response = gql(client, token, "query($id:ID!){seoEntryAudit(id:$id){total}}", {"id": original["id"]}, delivery=True)
    assert response["errors"][0]["extensions"]["code"] == "FORBIDDEN"
    second = client.post("/api/projects", headers=admin, json={"name": "Separate"}).json()
    other_headers = {**admin, "x-moss-project": second["id"]}
    assert report(client, other_headers)["recordCount"] == 0
    response = gql(client, other_headers, "query($id:ID!){seoEntryAudit(id:$id){total}}", {"id": original["id"]})
    assert response["errors"][0]["extensions"]["code"] == "NOT_FOUND"
    assert (
        saved(client, admin, slug="still-publishable", status="published", data={"title": "", "description": ""})[
            "status"
        ]
        == "published"
    )


@pytest.mark.parametrize(
    "variables",
    [
        {"snapshot": "scheduled"},
        {"first": 0},
        {"severity": "unknown"},
        {"after": "invalid"},
        {"after": base64.b64encode(json.dumps(["x", -1]).encode()).decode()},
    ],
)
def test_invalid_inputs_and_cursors_are_rejected(client, admin, variables):
    result = gql(
        client,
        admin,
        "query($snapshot:String!,$first:Int!,$severity:String,$after:String){seoAudit(snapshot:$snapshot,first:$first,severity:$severity,after:$after){total}}",
        {"snapshot": "draft", "first": 20, **variables},
    )
    assert "errors" in result


def test_cursor_detects_changed_results(app, client, admin):
    define(client, admin, fields=FIELDS)
    saved(client, admin, data={"title": "", "description": ""})
    first = report(client, admin, first=1)
    saved(client, admin, slug="new", data={"title": "", "description": ""})
    result = gql(
        client,
        admin,
        'query($after:String!){seoAudit(snapshot:"draft",after:$after){total}}',
        {"after": first["endCursor"]},
    )
    assert result["errors"][0]["extensions"]["code"] == "CONFLICT"


def test_homepage_profile_selection_matches_delivery_order_and_whitespace_is_missing(app, client, admin):
    define(
        client,
        admin,
        key="siteProfile",
        fields=[{"name": "name", "type": "text"}, {"name": "headline", "type": "text"}],
    )
    saved(
        client,
        admin,
        key="siteProfile",
        slug="older",
        status="published",
        data={"name": "Old name", "headline": "Old description"},
    )
    profile = saved(
        client, admin, key="siteProfile", slug="newer", status="published", data={"name": "", "headline": "   "}
    )
    define(
        client, admin, key="sitePage", fields=FIELDS + [{"name": "kind", "type": "enum", "options": ["home", "page"]}]
    )
    saved(
        client,
        admin,
        key="sitePage",
        slug="home",
        status="published",
        data={"title": "Unused home title", "kind": "home"},
    )
    result = report(client, admin, "live")
    assert any(f["code"] == "missing_profile_name" and f["entryId"] == profile["id"] for f in result["findings"])
    assert any(f["code"] == "missing_description" and f["severity"] == "critical" for f in result["findings"])


def test_locale_missing_values_and_private_body_are_checked_without_private_findings(client, admin):
    define(
        client,
        admin,
        key="sitePost",
        fields=[
            {"name": "title", "type": "text", "localized": True},
            {"name": "description", "type": "text", "localized": True},
            {"name": "body", "type": "richText", "private": True},
        ],
    )
    assert (
        client.patch(
            "/api/projects/" + admin["x-moss-project"],
            headers=admin,
            json={"locales": ["en", "he"], "defaultLocale": "en"},
        ).status_code
        == 200
    )
    saved(
        client,
        admin,
        key="sitePost",
        data={
            "title": {"en": "English"},
            "description": {"en": "English description"},
            "body": "# Secret\n![](asset:missing)",
        },
    )
    result = report(client, admin)
    assert any(
        f["code"] == "missing_title" and f["locale"] == "he" and f["fieldPath"] == "data.title.he"
        for f in result["findings"]
    )
    assert not any((f["fieldPath"] or "").startswith("data.body") for f in result["findings"])


def test_private_list_items_and_their_children_are_not_audited(client, admin):
    define(
        client,
        admin,
        key="siteSlide",
        fields=[
            {"name": "privateItems", "type": "list", "item": {"type": "richText", "private": True}},
            {
                "name": "privateObjects",
                "type": "list",
                "item": {"type": "object", "private": True, "fields": [{"name": "body", "type": "richText"}]},
            },
        ],
    )
    saved(
        client,
        admin,
        key="siteSlide",
        data={"privateItems": ["![](asset:missing)"], "privateObjects": [{"body": "![](asset:missing)"}]},
    )
    result = report(client, admin)
    assert result["supportingCount"] == 1 and result["total"] == 0
