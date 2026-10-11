"""Read-only record checks; website rendering and indexing are not verified."""

import base64
import hashlib
import json
import unicodedata
from collections import defaultdict
from dataclasses import asdict
from typing import Any

import strawberry
from markdown_it import MarkdownIt
from sqlalchemy import select

from .content import scoped
from .models import Asset, ContentType, Entry, Project, now
from .security import CmsError, require

PAGES = {"sitePage", "sitePost", "siteProject"}
SUPPORTING = {"siteProfile", "siteSlide"}
SEVERITIES = {"critical": 0, "warning": 1, "info": 2}
NOT_CHECKED = [
    "Website HTML",
    "Canonical tags",
    "Robots",
    "Sitemaps",
    "Performance",
    "External links",
    "Indexing",
    "Captured schedules",
]
# Ignore HTML tokens, matching ReactMarkdown's skipHtml. Never render audit input.
MARKDOWN = MarkdownIt("commonmark", {"breaks": True})


@strawberry.type
class SeoFinding:
    code: str
    severity: str
    entry_id: strawberry.ID
    entry_title: str
    type_key: str
    snapshot: str
    revision: int
    locale: str | None
    field_path: str | None
    explanation: str
    guidance: str


@strawberry.type
class SeoMapping:
    type_key: str
    name: str
    kind: str
    title_path: str | None
    description_path: str | None


@strawberry.type
class SeoReport:
    snapshot: str
    generated_at: str
    record_count: int
    page_count: int
    supporting_count: int
    needs_mapping_count: int
    no_live_count: int
    critical_count: int
    warning_count: int
    info_count: int
    mappings: list[SeoMapping]
    not_checked: list[str]
    findings: list[SeoFinding]
    total: int
    end_cursor: str | None
    has_next_page: bool
    revision: int | None = None


def field_at(fields, path):
    field = None
    for name in path.split("."):
        field = next((f for f in fields if f["name"] == name and not f.get("private")), None)
        if not field:
            return None
        fields = field.get("fields", [])
    return field if field and field["type"] in {"text", "richText"} else None


def detect(definition):
    builtin = definition.key in PAGES
    title = next(
        (p for p in (["title"] if builtin else ["seo.title", "seoTitle", "title"]) if field_at(definition.fields, p)),
        None,
    )
    description = next(
        (
            p
            for p in (["description"] if builtin else ["seo.description", "metaDescription", "description", "excerpt"])
            if field_at(definition.fields, p)
        ),
        None,
    )
    kind = (
        "supporting"
        if definition.key in SUPPORTING
        else "page"
        if (title and description) or builtin
        else "needs_mapping"
    )
    return SeoMapping(
        type_key=definition.key, name=definition.name, kind=kind, title_path=title, description_path=description
    )


def value_at(fields, data, path, locale):
    if not path:
        return None, None
    actual = "data"
    for name in path.split("."):
        field = next((f for f in fields if f["name"] == name and not f.get("private")), None)
        if not field:
            return None, None
        data = data.get(name) if isinstance(data, dict) else None
        actual += "." + name
        if field.get("localized"):
            data = data.get(locale) if isinstance(data, dict) else None
            actual += "." + locale
        fields = field.get("fields", [])
    return data, actual


def public_walk(fields, data, locales, path="data", locale=None):
    for field in fields:
        if not field.get("private"):
            value = data.get(field["name"]) if isinstance(data, dict) else None
            yield from walk_value(field, value, locales, path + "." + field["name"], locale)


def walk_value(field, value, locales, path, locale):
    if field.get("private"):
        return
    if field.get("localized"):
        translations = value if isinstance(value, dict) else {}
        for language in sorted(set(locales) | set(translations)):
            yield from walk_value(
                {**field, "localized": False}, translations.get(language), locales, path + "." + language, language
            )
        return
    yield field, value, path, locale
    if field["type"] == "object":
        yield from public_walk(field["fields"], value, locales, path, locale)
    elif field["type"] == "list" and isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk_value(field["item"], item, locales, f"{path}[{index}]", locale)


def text(value):
    return value.strip() if isinstance(value, str) else ""


def normalized(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def audit_records(
    session, identity, snapshot="live", type_key=None, severity=None, first=20, after=None, entry_id=None
):
    require(identity)
    if identity.get("delivery"):
        raise CmsError("SEO audits are editorial only.", "FORBIDDEN")
    if snapshot not in {"draft", "live"} or (severity and severity not in SEVERITIES) or not 1 <= first <= 100:
        raise CmsError("Choose draft or live, a supported severity, and a page size of 1–100.")
    definitions = {t.id: t for t in session.scalars(scoped(session, ContentType, identity)).all()}
    if type_key and not any(t.key == type_key for t in definitions.values()):
        raise CmsError("Content type not found.", "NOT_FOUND")
    records = session.scalars(scoped(session, Entry, identity).order_by(Entry.id)).all()
    by_id = {r.id: r for r in records}
    if entry_id and (entry_id not in by_id or by_id[entry_id].status == "deleted"):
        raise CmsError("Entry not found.", "NOT_FOUND")
    active = [r for r in records if r.status != "deleted"]
    selected = [r for r in active if snapshot == "draft" or r.published_slug is not None]
    assets = dict(session.execute(select(Asset.id, Asset.mime).where(Asset.project_id == identity["project_id"])).all())
    project = session.get(Project, identity["project_id"])
    locales = list(dict.fromkeys([project.default_locale, *project.locales]))
    mappings = {id: detect(t) for id, t in definitions.items()}
    findings: list[SeoFinding] = []
    seen = set()
    duplicates: dict[Any, list] = defaultdict(list)

    def data_for(record):
        return record.data if snapshot == "draft" else record.published_data or {}

    profiles = sorted(
        [r for r in selected if definitions[r.type_id].key == "siteProfile"],
        key=lambda r: (r.updated_at if snapshot == "draft" else r.published_at, r.id),
        reverse=True,
    )
    profile = next(
        (r for r in profiles if (r.slug if snapshot == "draft" else r.published_slug) == "profile"),
        profiles[0] if profiles else None,
    )

    def emit(record, code, level, path, language, explanation, guidance):
        key = (record.id, code, path, language)
        if key in seen:
            return
        seen.add(key)
        findings.append(
            SeoFinding(
                code=code,
                severity=level,
                entry_id=strawberry.ID(record.id),
                entry_title=record.title if snapshot == "draft" else record.published_title or record.published_slug,
                type_key=definitions[record.type_id].key,
                snapshot=snapshot,
                revision=record.version if snapshot == "draft" else record.published_revision or 0,
                locale=language,
                field_path=path,
                explanation=explanation,
                guidance=guidance,
            )
        )

    def check_asset(record, asset_id, path, language, markdown=False):
        if asset_id not in assets or (
            markdown and assets.get(asset_id) not in {"image/jpeg", "image/png", "image/webp"}
        ):
            emit(
                record,
                "unavailable_asset",
                "critical",
                path,
                language,
                "A referenced asset is missing or cannot be used by the image renderer.",
                "Select an available workspace asset. Markdown images require JPEG, PNG, or WebP.",
            )

    for record in selected:
        definition, mapping = definitions[record.type_id], mappings[record.type_id]
        data = data_for(record)
        values = list(public_walk(definition.fields, data, locales))
        languages = (
            sorted(set(locales) | {language for _, _, _, language in values if language})
            if any(language for _, _, _, language in values)
            else [project.default_locale]
        )
        if mapping.kind == "needs_mapping":
            emit(
                record,
                "needs_mapping",
                "warning",
                None,
                None,
                "Needs mapping: a public title or description field could not be recognized.",
                "Add conventional public SEO fields in Content types. Review the detected mappings.",
            )
        if mapping.kind != "supporting":
            for language in languages:
                title, title_path = value_at(definition.fields, data, mapping.title_path, language)
                description, description_path = value_at(definition.fields, data, mapping.description_path, language)
                effective_title, effective_description = text(title), text(description)
                if definition.key in PAGES:
                    kind, _ = value_at(definition.fields, data, "kind", language)
                    profile_name = headline = None
                    if profile:
                        profile_definition, profile_data = definitions[profile.type_id], data_for(profile)
                        profile_name, _ = value_at(profile_definition.fields, profile_data, "name", language)
                        headline, _ = value_at(profile_definition.fields, profile_data, "headline", language)
                    chosen_title = profile_name if kind == "home" else title
                    effective_title = text(chosen_title) if chosen_title else "Example website"
                    effective_description = text(description or headline or "A example website.")
                    if kind == "home" and not text(profile_name):
                        if profile:
                            _, name_path = value_at(
                                definitions[profile.type_id].fields, data_for(profile), "name", language
                            )
                            emit(
                                profile,
                                "missing_profile_name",
                                "warning",
                                name_path,
                                language,
                                "The homepage title uses a generic fallback because the website profile name is missing.",
                                "Fill in the public website profile name, then publish it to update the homepage title.",
                            )
                        else:
                            emit(
                                record,
                                "missing_homepage_profile",
                                "warning",
                                None,
                                language,
                                "The homepage title uses a generic fallback because no website profile is available.",
                                "Create a website profile with a public name and publish it for live delivery.",
                            )
                for label, path, raw, effective in [
                    ("title", title_path, title, effective_title),
                    ("description", description_path, description, effective_description),
                ]:
                    mapped = mapping.title_path if label == "title" else mapping.description_path
                    if not text(raw) and (mapped or definition.key in PAGES):
                        emit(
                            record,
                            "missing_" + label,
                            "warning" if effective else "critical",
                            path,
                            language,
                            f"Page-specific {label} is missing."
                            + (" The website uses a fallback." if effective else ""),
                            f"Write a descriptive, unique {label} for this page."
                            + (" Review homepage profile values where applicable." if definition.key in PAGES else ""),
                        )
                    if effective:
                        duplicates[(label, language, normalized(effective))].append((record, path))
                        limit = 60 if label == "title" else 160
                        if len(effective) > limit:
                            emit(
                                record,
                                "long_" + label,
                                "info",
                                path,
                                language,
                                f"The effective {label} has {len(effective)} characters (review guide: {limit}).",
                                "Consider making it more concise. This is a display heuristic, not a search-engine limit.",
                            )
        if (definition.key == "sitePost" or (mapping.kind == "page" and definition.key not in PAGES)) and field_at(
            definition.fields, "body"
        ):
            for language in languages:
                body, body_path = value_at(definition.fields, data, "body", language)
                if not text(body):
                    emit(
                        record,
                        "empty_article",
                        "warning",
                        body_path,
                        language,
                        "This record has no article body.",
                        "Add useful article content before publishing.",
                    )
        for field, value, path, language in values:
            if field["type"] == "asset" and value:
                check_asset(record, value, path, language)
            elif field["type"] == "reference" and value:
                target = by_id.get(value)
                if not target or target.status == "deleted" or (snapshot == "live" and target.published_slug is None):
                    emit(
                        record,
                        "unavailable_reference",
                        "critical",
                        path,
                        language,
                        "The referenced record is unavailable in this snapshot.",
                        "Choose an available record, or publish the referenced record for live delivery.",
                    )
            elif field["type"] == "object" and isinstance(value, dict):
                asset_fields = [f for f in field["fields"] if f["type"] == "asset" and not f.get("private")]
                alt_field = next((f for f in field["fields"] if f["name"] == "alt" and not f.get("private")), None)
                for asset_field in asset_fields:
                    asset_value = value.get(asset_field["name"])
                    if not isinstance(asset_value, str) or not assets.get(asset_value, "").startswith("image/"):
                        continue
                    if not alt_field:
                        emit(
                            record,
                            "image_needs_mapping",
                            "info",
                            path,
                            language,
                            "This image object has no recognized public alt field.",
                            "Review how your frontend supplies descriptions; add a public alt field if appropriate.",
                        )
                    else:
                        for alt_locale in locales if alt_field.get("localized") else [language]:
                            alt_value = value.get("alt")
                            if alt_field.get("localized"):
                                alt_value = alt_value.get(alt_locale) if isinstance(alt_value, dict) else None
                            if not text(alt_value):
                                alt_path = path + ".alt" + ("." + alt_locale if alt_field.get("localized") else "")
                                emit(
                                    record,
                                    "missing_image_description",
                                    "warning",
                                    alt_path,
                                    alt_locale,
                                    "An image has no description; it may be intentionally decorative.",
                                    "Add meaningful alt text for an informative image. Leave decorative images empty.",
                                )
            elif field["type"] == "richText" and text(value):
                tokens = MARKDOWN.parse(value)
                headings = [int(t.tag[1:]) for t in tokens if t.type == "heading_open"]
                if headings.count(1) > (0 if definition.key in PAGES else 1):
                    emit(
                        record,
                        "extra_h1",
                        "warning",
                        path,
                        language,
                        "The content contains extra H1 headings"
                        + ("; the website already renders the page heading." if definition.key in PAGES else "."),
                        "Use H2 for main article sections and H3 for subsections.",
                    )
                levels = ([1] if definition.key in PAGES else []) + headings
                if any(b > a + 1 for a, b in zip(levels, levels[1:])):
                    emit(
                        record,
                        "skipped_heading_level",
                        "info",
                        path,
                        language,
                        "The content skips a heading level.",
                        "Keep headings in a logical hierarchy.",
                    )
                for token in tokens:
                    for child in token.children or []:
                        if child.type != "image":
                            continue
                        if not text(child.content):
                            emit(
                                record,
                                "missing_image_description",
                                "warning",
                                path,
                                language,
                                "A Markdown image has empty alt text; it may be decorative.",
                                "Describe informative images inside ![description](url); leave decorative images empty.",
                            )
                        source = child.attrGet("src") or ""
                        if isinstance(source, str) and source.startswith("asset:"):
                            check_asset(record, source[6:], path, language, markdown=True)

    for (label, language, _), group in duplicates.items():
        if len(group) > 1:
            for record, path in group:
                emit(
                    record,
                    "duplicate_" + label,
                    "warning",
                    path,
                    language,
                    f"This effective {label} is shared by {len(group)} pages in this snapshot and locale.",
                    f"Give each page a distinct {label}. Review shared profile fallbacks if present.",
                )
    counts = {level: sum(f.severity == level for f in findings) for level in SEVERITIES}
    filtered = [
        f
        for f in findings
        if (not type_key or f.type_key == type_key)
        and (not severity or f.severity == severity)
        and (not entry_id or f.entry_id == entry_id)
    ]
    filtered.sort(key=lambda f: (SEVERITIES[f.severity], f.entry_id, f.code, f.locale or "", f.field_path or ""))
    fingerprint = hashlib.sha256(
        json.dumps(
            [identity["project_id"], snapshot, type_key, severity, entry_id, [asdict(f) for f in filtered]],
            sort_keys=True,
        ).encode()
    ).hexdigest()[:24]
    offset = 0
    if after:
        try:
            cursor = json.loads(base64.b64decode(after, validate=True))
            if cursor[0] != fingerprint or type(cursor[1]) is not int or not 0 <= cursor[1] <= len(filtered):
                raise ValueError()
            offset = cursor[1]
        except (ValueError, TypeError, IndexError, KeyError):
            raise CmsError("Audit results changed or the cursor is invalid. Rerun the audit.", "CONFLICT") from None
    target_records = [r for r in selected if not entry_id or r.id == entry_id]
    report_mappings = [
        m for m in mappings.values() if not entry_id or m.type_key == definitions[by_id[entry_id].type_id].key
    ]
    if entry_id:
        counts = {level: sum(f.severity == level for f in filtered) for level in SEVERITIES}
    end = min(offset + first, len(filtered))
    return SeoReport(
        snapshot=snapshot,
        generated_at=now().isoformat() + "Z",
        record_count=len(target_records),
        page_count=sum(mappings[r.type_id].kind == "page" for r in target_records),
        supporting_count=sum(mappings[r.type_id].kind == "supporting" for r in target_records),
        needs_mapping_count=sum(mappings[r.type_id].kind == "needs_mapping" for r in target_records),
        no_live_count=sum(r.published_slug is None for r in active if not entry_id or r.id == entry_id),
        critical_count=counts["critical"],
        warning_count=counts["warning"],
        info_count=counts["info"],
        mappings=sorted(report_mappings, key=lambda m: m.name),
        not_checked=NOT_CHECKED,
        findings=filtered[offset:end],
        total=len(filtered),
        has_next_page=end < len(filtered),
        end_cursor=base64.b64encode(json.dumps([fingerprint, end]).encode()).decode() if end < len(filtered) else None,
        revision=(by_id[entry_id].version if snapshot == "draft" else by_id[entry_id].published_revision)
        if entry_id
        else None,
    )
