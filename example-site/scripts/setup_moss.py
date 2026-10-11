#!/usr/bin/env python3
"""Create or upgrade the editable example website workspace in local MossCMS."""

import argparse
import copy
import getpass
import http.cookiejar
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path


def text_field(name, kind="text", **options):
    label = re.sub(r"([A-Z])", r" \1", name).capitalize()
    return {"name": name, "label": label, "type": kind, **options}


def merge_fields(existing, desired):
    """Add optional fields/options while retaining existing custom schema fields."""
    fields = copy.deepcopy(existing)
    by_name = {field["name"]: field for field in fields}
    for field in desired:
        old = by_name.get(field["name"])
        if old is None:
            fields.append(field)
        elif old["type"] == field["type"] == "object":
            old["fields"] = merge_fields(old["fields"], field["fields"])
        elif old["type"] == field["type"] == "enum":
            old["options"] = list(dict.fromkeys(old["options"] + field["options"]))
        elif old["type"] != field["type"]:
            raise SystemExit(f"Cannot upgrade custom field {field['name']}: its type differs.")
    return fields


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cms-url", default="http://localhost:8001")
    parser.add_argument(
        "--email",
        default=os.getenv("MOSS_ADMIN_EMAIL"),
        help="Administrator email; prompted if omitted.",
    )
    parser.add_argument("--name", default="Moss Example")
    parser.add_argument("--headline", default="A working example of a website powered by MossCMS.")
    parser.add_argument(
        "--website-url",
        help="Trusted website origin for the public site and saved-draft previews.",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    defaults = json.loads((root / "src/content-defaults.json").read_text())
    headers = {"Content-Type": "application/json"}
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(path, body=None, method=None):
        req = urllib.request.Request(
            args.cms_url.rstrip("/") + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
            method=method,
        )
        try:
            with opener.open(req, timeout=20) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            detail = json.loads(error.read()).get("detail", f"HTTP {error.code}")
            raise SystemExit(str(detail)) from None

    def gql(query, variables=None):
        result = request("/graphql", {"query": query, "variables": variables})
        if result.get("errors"):
            raise SystemExit("; ".join(error["message"] for error in result["errors"]))
        return result["data"]

    def all_entries(key):
        entries, cursor = [], None
        while True:
            page = gql(
                "query($key:String!,$after:String){entries(typeKey:$key,first:100,after:$after){nodes{id slug data status version scheduledAt} endCursor hasNextPage}}",
                {"key": key, "after": cursor},
            )["entries"]
            entries.extend(page["nodes"])
            if not page["hasNextPage"]:
                return {entry["slug"]: entry for entry in entries}
            cursor = page["endCursor"]

    def save_entry(key, slug, data, existing=None):
        return gql(
            "mutation($key:String!,$slug:String!,$data:JSON!,$id:ID,$version:Int,$status:String!,$scheduledAt:String){saveEntry(typeKey:$key,slug:$slug,data:$data,id:$id,version:$version,status:$status,scheduledAt:$scheduledAt){id slug data status version scheduledAt}}",
            {
                "key": key,
                "slug": slug,
                "data": data,
                "id": existing["id"] if existing else None,
                "version": existing["version"] if existing else None,
                "status": existing["status"] if existing else "published",
                "scheduledAt": existing["scheduledAt"] if existing else None,
            },
        )["saveEntry"]

    status = request("/auth/status")
    if status.get("authSkipped"):
        raise SystemExit("Disable MOSS_SKIP_AUTH before setup so the website belongs to your administrator account.")
    if not status.get("initialized"):
        raise SystemExit("Create your first administrator in the CMS before initializing the website.")
    try:
        email = args.email or input("Administrator email: ").strip()
        password = os.getenv("MOSS_ADMIN_PASSWORD") or getpass.getpass("Administrator password: ")
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("Provide --email and enter your administrator password to continue.") from None
    request("/auth/login", {"email": email, "password": password})
    account = request("/auth/me")
    headers["X-Moss-CSRF"] = account["csrf"]
    project = next((p for p in account["projects"] if p["name"] == "Example website"), None)
    if not project:
        project = request("/api/projects", {"name": "Example website"})
    elif project.get("role") != "admin":
        raise SystemExit("An administrator of Example website must run setup.")
    headers["X-Moss-Project"] = project["id"]
    env_file = root / ".env"
    values = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key] = value
    website_url = args.website_url or values.get("SITE_PUBLIC_URL", "http://localhost:5174")
    if not project.get("previewOrigin"):
        request("/api/project/preview", {"origin": website_url}, "PATCH")

    profile_fields = [
        text_field("name", required=True),
        text_field("headline", required=True),
        text_field("intro", "richText"),
        text_field("heroName"),
        text_field("location"),
        text_field("email"),
        text_field("availability"),
        {
            "name": "links",
            "type": "list",
            "item": {
                "type": "object",
                "fields": [
                    text_field("label", required=True),
                    text_field("url", required=True),
                ],
            },
        },
        {
            "name": "appearance",
            "label": "Website colors (six-digit hex)",
            "type": "object",
            "fields": [text_field(name) for name in defaults["appearance"]],
        },
        {
            "name": "labels",
            "label": "Website wording",
            "type": "object",
            "fields": [text_field(name) for name in defaults["labels"]],
        },
        text_field("carouselSeconds", "number"),
        text_field("carouselAutoplay", "boolean"),
    ]
    page_fields = [
        text_field("title", required=True),
        text_field("description"),
        text_field("body", "richText"),
        text_field("order", "number", required=True),
        {
            "name": "kind",
            "type": "enum",
            "options": ["home", "page", "contact", "projects", "blog", "about"],
        },
        text_field("parentSlug"),
        text_field("url"),
        text_field("linkLabel"),
        {
            "name": "items",
            "type": "list",
            "item": {
                "type": "object",
                "fields": [
                    text_field("title", required=True),
                    text_field("description", "richText"),
                    text_field("url"),
                    text_field("label"),
                ],
            },
        },
    ]
    image_fields = [
        text_field("asset", "asset", imageOnly=True),
        text_field("alt"),
        text_field("focalX", "number"),
        text_field("focalY", "number"),
        {"name": "fit", "type": "enum", "options": ["cover", "contain"]},
    ]
    cover_field = {
        "name": "cover",
        "label": "Cover image",
        "type": "object",
        "fields": image_fields,
    }
    gallery_field = {
        "name": "gallery",
        "label": "Project gallery",
        "type": "list",
        "item": {
            "type": "object",
            "fields": image_fields + [text_field("caption", "richText")],
        },
    }
    slide_fields = [
        text_field("title", required=True),
        {
            "name": "kind",
            "type": "enum",
            "required": True,
            "options": ["liquid", "three", "promotion", "blog"],
        },
        text_field("eyebrow"),
        text_field("description", "richText"),
        text_field("linkUrl"),
        text_field("linkLabel"),
        text_field("primaryColor"),
        text_field("secondaryColor"),
        text_field("backgroundColor"),
        text_field("textColor"),
        text_field("duration", "number"),
        text_field("speed", "number"),
        text_field("enabled", "boolean"),
    ]
    types = {t["key"]: t for t in gql("{contentTypes{key name fields version}}")["contentTypes"]}
    website_fields = merge_fields(types.get("sitePage", {}).get("fields", []), page_fields)
    for key, name, fields in [
        ("siteProfile", "Website profile", profile_fields),
        ("sitePage", "Website page", page_fields),
        ("siteSlide", "Homepage slide", slide_fields),
        ("siteProject", "Projects", website_fields + [cover_field, gallery_field]),
        ("sitePost", "Blog posts", website_fields + [cover_field]),
    ]:
        existing = types.get(key)
        merged = merge_fields(existing["fields"], fields) if existing else fields
        if existing and merged == existing["fields"]:
            continue
        gql(
            "mutation($key:String!,$name:String!,$fields:JSON!,$version:Int){saveContentType(key:$key,name:$name,fields:$fields,version:$version){key}}",
            {
                "key": key,
                "name": existing["name"] if existing else name,
                "fields": merged,
                "version": existing["version"] if existing else None,
            },
        )

    entries = {key: all_entries(key) for key in ["siteProfile", "sitePage", "siteSlide", "siteProject", "sitePost"]}
    profile = entries["siteProfile"].get("profile")
    profile_data = (
        copy.deepcopy(profile["data"])
        if profile
        else {
            "name": args.name,
            "headline": args.headline,
            "intro": "Explore sample projects, blog posts, and pages. Every section is managed in MossCMS; replace this starter content with your own.",
            "links": [],
        }
    )
    for key in ["labels", "appearance"]:
        profile_data[key] = {**defaults[key], **(profile_data.get(key) or {})}
    profile_data.setdefault("carouselSeconds", 12)
    profile_data.setdefault("carouselAutoplay", True)
    if not profile or profile_data != profile["data"]:
        save_entry("siteProfile", "profile", profile_data, profile)

    # Rename the existing pages by ID; retain their content, publication state and revisions.
    for old_slug, new_slug, title, kind in [
        ("notes", "blog", "Blog", "blog"),
        ("contact", "about", "About me", "about"),
    ]:
        old = entries["sitePage"].get(old_slug)
        if old and new_slug not in entries["sitePage"]:
            data = {**old["data"], "title": title, "kind": kind}
            if old_slug == "contact" and data.get("description") == "Say hello. I’d love to hear from you.":
                data["description"] = "A little about me, and the things I’m building."
            if old_slug == "contact" and data.get("body") == "For a question, an idea, or simply a conversation.":
                data["body"] = (
                    f"{profile_data['name']} demonstrates editable pages, projects, and blog posts powered by MossCMS."
                )
            entries["sitePage"][new_slug] = save_entry("sitePage", new_slug, data, old)
            del entries["sitePage"][old_slug]
    projects = entries["sitePage"].get("projects")
    if projects and projects["data"].get("kind") == "page":
        entries["sitePage"]["projects"] = save_entry(
            "sitePage", "projects", {**projects["data"], "kind": "projects"}, projects
        )

    parents = {
        kind: {entry["slug"] for entry in entries["sitePage"].values() if entry["data"].get("kind") == kind} | {kind}
        for kind in ["projects", "blog"]
    }
    for slug, entry in list(entries["sitePage"].items()):
        parent = entry["data"].get("parentSlug")
        target = "siteProject" if parent in parents["projects"] else "sitePost" if parent in parents["blog"] else None
        if target:
            if slug in entries[target]:
                raise SystemExit(
                    f"Cannot move {slug}: a {target} entry already uses this slug. Rename one entry first."
                )
            moved = gql(
                "mutation($id:ID!,$key:String!,$version:Int!){moveEntry(id:$id,typeKey:$key,version:$version){id slug data status version scheduledAt}}",
                {"id": entry["id"], "key": target, "version": entry["version"]},
            )["moveEntry"]
            entries[target][slug] = moved
            del entries["sitePage"][slug]

    page_seeds = [
        (
            "home",
            {
                "title": "Home",
                "description": "A little introduction.",
                "order": 10,
                "kind": "home",
            },
        ),
        (
            "projects",
            {
                "title": "Projects",
                "description": "Sample projects published from MossCMS.",
                "body": "Create project entries in the admin to add to this collection.",
                "order": 20,
                "kind": "projects",
            },
        ),
        (
            "blog",
            {
                "title": "Blog",
                "description": "Example posts with Markdown and scheduled publishing.",
                "body": "Publish a post in MossCMS to see it appear here.",
                "order": 30,
                "kind": "blog",
            },
        ),
        (
            "about",
            {
                "title": "About",
                "description": "How this example connects to MossCMS.",
                "body": f"{profile_data['name']} demonstrates editable pages, projects, and blog posts powered by MossCMS.",
                "order": 40,
                "kind": "about",
            },
        ),
        (
            "mosscms",
            {
                "title": "MossCMS",
                "description": "A self-hosted, data-first CMS for independent frontends.",
                "body": "A CMS built with Python and GraphQL, with a React admin and Docker deployment. It supplies the published content for this website.",
                "order": 10,
                "kind": "page",
                "parentSlug": "projects",
            },
        ),
        (
            "example-website",
            {
                "title": "Moss Example",
                "description": "A sample frontend you can customize for your own content.",
                "body": "A Vite and React frontend with a rotating home showcase. The content, projects, blog, and appearance are managed in MossCMS.",
                "order": 20,
                "kind": "page",
                "parentSlug": "projects",
            },
        ),
        (
            "building-this-space",
            {
                "title": "Publishing your first website",
                "description": "A sample post demonstrating published content from MossCMS.",
                "body": "This example frontend reads published content through the MossCMS delivery API. Its sidebar brings together projects, a blog, and editable pages.\n\nThe homepage includes configurable showcase slides.\n\nEdit this post in the admin, save a draft, and publish it to see the change on the website.",
                "order": 10,
                "kind": "page",
                "parentSlug": "blog",
            },
        ),
    ]
    for slug, data in page_seeds:
        key = (
            "siteProject"
            if data.get("parentSlug") == "projects"
            else "sitePost"
            if data.get("parentSlug") == "blog"
            else "sitePage"
        )
        if slug not in entries[key]:
            save_entry(key, slug, {**data, "items": []})

    slide_seeds = [
        (
            "liquid",
            {
                "title": "A little less static.",
                "kind": "liquid",
                "eyebrow": "An experiment in motion",
                "description": "A surface that shifts, ripples, and responds. Move your pointer and leave a little trace.",
                "primaryColor": "#A1F2D5",
                "secondaryColor": "#78A3F0",
                "backgroundColor": "#11202A",
            },
        ),
        (
            "three",
            {
                "title": "Ideas, in another dimension.",
                "kind": "three",
                "eyebrow": "Playing with form",
                "description": "An ongoing exploration of shape, light, and the things a browser can become.",
                "primaryColor": "#C4ACFA",
                "secondaryColor": "#E493BA",
                "backgroundColor": "#171622",
            },
        ),
        (
            "moss",
            {
                "title": "Your content.\nYour frontend.",
                "kind": "promotion",
                "eyebrow": "Powered by MossCMS",
                "description": "A self-hosted CMS with a published-content API. This example shows how to connect your own frontend.",
                "linkUrl": "#mosscms",
                "linkLabel": "Explore MossCMS",
                "primaryColor": "#D5E7AD",
                "secondaryColor": "#779868",
                "backgroundColor": "#202B22",
            },
        ),
        (
            "from-the-blog",
            {
                "title": "From the blog",
                "kind": "blog",
                "eyebrow": "A note from the blog",
                "linkLabel": "Read the story",
                "primaryColor": "#F1D4A9",
                "secondaryColor": "#A58263",
                "backgroundColor": "#2A221D",
            },
        ),
    ]
    for slug, data in slide_seeds:
        if slug not in entries["siteSlide"]:
            save_entry(
                "siteSlide",
                slug,
                {**data, "textColor": "#F2F4F6", "enabled": True, "speed": 1},
            )

    scopes = {"siteProfile", "sitePage", "siteSlide", "siteProject", "sitePost"}
    token = values.get("MOSS_DELIVERY_TOKEN", "") if values.get("MOSS_PROJECT_ID") == project["id"] else ""
    if token:
        req = urllib.request.Request(
            args.cms_url.rstrip("/") + "/delivery/graphql",
            data=json.dumps({"query": "{contentTypes{key}}"}).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                result = json.load(response)
                if result.get("errors") or not scopes.issubset({t["key"] for t in result["data"]["contentTypes"]}):
                    token = ""
        except urllib.error.URLError:
            token = ""
    if not token:
        token = request(
            "/api/tokens",
            {"name": "Example website", "scopes": sorted(scopes), "days": 365},
        )["token"]
    values.update(
        MOSS_API_URL=args.cms_url.rstrip("/"),
        MOSS_PROJECT_ID=project["id"],
        MOSS_DELIVERY_TOKEN=token,
    )
    values.setdefault("PORT", "5174")
    values["SITE_PUBLIC_URL"] = website_url
    env_file.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")
    env_file.chmod(0o600)
    print("Example website workspace: " + project["id"])
    print(
        "Website schemas upgraded. Projects and blog posts have their own content types; IDs, content, schedules and history are retained."
    )
    print("Server-only connection saved to " + str(env_file))


if __name__ == "__main__":
    main()
