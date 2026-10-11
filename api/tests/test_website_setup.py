import argparse
import copy
import importlib.util
import io
import json
import sys
import urllib.request
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "personal-site/scripts/setup_moss.py"
TYPE_KEYS = ["siteProfile", "sitePage", "siteSlide", "siteProject", "sitePost"]


def load_script():
    spec = importlib.util.spec_from_file_location("website_setup", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_import_has_no_cli_network_or_file_side_effects(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Import must not parse arguments, contact the CMS, or read/write setup files")

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", unexpected)
    monkeypatch.setattr(urllib.request, "urlopen", unexpected)
    monkeypatch.setattr(Path, "read_text", unexpected)
    monkeypatch.setattr(Path, "write_text", unexpected)
    monkeypatch.setattr(Path, "chmod", unexpected)
    script = load_script()
    assert callable(script.main)
    assert script.text_field("heroName", required=True) == {
        "name": "heroName",
        "label": "Hero name",
        "type": "text",
        "required": True,
    }


def test_schema_merge_preserves_custom_fields_options_and_input():
    script = load_script()
    existing = [
        {"name": "custom", "type": "text", "private": True},
        {
            "name": "appearance",
            "type": "object",
            "label": "My colors",
            "fields": [{"name": "background", "type": "text", "required": True}],
        },
        {"name": "kind", "type": "enum", "options": ["custom", "page"], "required": True},
    ]
    original = copy.deepcopy(existing)
    desired = [
        {
            "name": "appearance",
            "type": "object",
            "fields": [script.text_field("background"), script.text_field("foreground")],
        },
        {"name": "kind", "type": "enum", "options": ["page", "blog"]},
        script.text_field("intro", "richText"),
    ]
    merged = script.merge_fields(existing, desired)
    assert existing == original
    assert merged == [
        original[0],
        {**original[1], "fields": original[1]["fields"] + [script.text_field("foreground")]},
        {**original[2], "options": ["custom", "page", "blog"]},
        script.text_field("intro", "richText"),
    ]
    merged[1]["fields"][0]["required"] = False
    assert existing == original


@pytest.mark.parametrize("nested", [False, True])
def test_schema_merge_rejects_incompatible_types_without_changing_input(nested):
    script = load_script()
    existing = [script.text_field("custom", "number")]
    desired = [script.text_field("custom")]
    if nested:
        existing = [{"name": "appearance", "type": "object", "fields": existing}]
        desired = [{"name": "appearance", "type": "object", "fields": desired}]
    original = copy.deepcopy(existing)
    with pytest.raises(SystemExit, match="Cannot upgrade custom field custom: its type differs"):
        script.merge_fields(existing, desired)
    assert existing == original


@pytest.mark.parametrize("status", [{}, {"authSkipped": False}])
def test_main_requires_development_auth_before_accessing_account_or_writing(status, monkeypatch):
    script = load_script()
    calls = []

    def urlopen(request, **kwargs):
        calls.append(request.full_url)
        assert request.full_url == "http://cms.test/auth/status"
        return io.BytesIO(json.dumps(status).encode())

    def unexpected(*args, **kwargs):
        pytest.fail("Rejected setup must not write credentials")

    monkeypatch.setattr(sys, "argv", ["setup_moss", "--cms-url", "http://cms.test/"])
    monkeypatch.setattr(Path, "read_text", lambda self: "{}")
    monkeypatch.setattr(Path, "write_text", unexpected)
    monkeypatch.setattr(Path, "chmod", unexpected)
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(SystemExit, match="MOSS_SKIP_AUTH=true"):
        script.main()
    assert calls == ["http://cms.test/auth/status"]


def test_main_preserves_existing_schema_entry_identity_and_server_credentials(monkeypatch):
    script = load_script()
    defaults = json.loads((SCRIPT.parents[1] / "src/content-defaults.json").read_text())
    profile_data = {
        **defaults,
        "name": "Kept name",
        "headline": "Kept headline",
        "carouselSeconds": 12,
        "carouselAutoplay": True,
    }

    def entry(slug, data, status="draft"):
        return {
            "id": slug + "-id",
            "slug": slug,
            "data": data,
            "status": status,
            "version": 7,
            "scheduledAt": "2030-01-01T00:00:00Z",
        }

    existing_entries = {
        "siteProfile": [entry("profile", profile_data)],
        "sitePage": [
            entry("notes", {"title": "Notes", "kind": "page", "body": "My writing"}, "scheduled"),
            entry(
                "contact",
                {"title": "Contact", "kind": "contact", "body": "Custom biography", "description": "Custom intro"},
            ),
            entry("projects", {"title": "Projects", "kind": "page", "body": "Custom projects"}),
            entry("custom-project", {"title": "Existing project", "parentSlug": "projects", "body": "My content"}),
        ],
        "siteSlide": [],
        "siteProject": [],
        "sitePost": [],
    }
    custom_field = {"name": "custom", "type": "text", "private": True}
    existing_type = {"key": "sitePage", "name": "Custom pages", "version": 4, "fields": [custom_field]}
    calls, mutations, writes, modes = [], [], {}, []
    env = "MOSS_PROJECT_ID=project-id\nMOSS_DELIVERY_TOKEN=kept-token\nPORT=9000\nOTHER=kept\n"

    def urlopen(request, **kwargs):
        calls.append(request)
        path = request.full_url.removeprefix("http://cms.test")
        payload = json.loads(request.data) if request.data else {}
        if path == "/auth/status":
            result = {"authSkipped": True}
        elif path == "/auth/me":
            result = {"csrf": "csrf-token", "projects": [{"name": "Personal website", "id": "project-id"}]}
        elif path == "/delivery/graphql":
            result = {"data": {"contentTypes": [{"key": key} for key in TYPE_KEYS]}}
        else:
            assert path == "/graphql"
            headers = {key.lower(): value for key, value in request.header_items()}
            assert headers["x-moss-csrf"] == "csrf-token"
            assert headers["x-moss-project"] == "project-id"
            query, variables = payload["query"], payload.get("variables")
            if query == "{contentTypes{key name fields version}}":
                result = {"data": {"contentTypes": [existing_type]}}
            elif "entries(typeKey:" in query:
                result = {
                    "data": {
                        "entries": {
                            "nodes": existing_entries[variables["key"]],
                            "hasNextPage": False,
                            "endCursor": None,
                        }
                    }
                }
            else:
                mutations.append((query, variables))
                if "saveContentType(" in query:
                    result = {"data": {"saveContentType": {"key": variables["key"]}}}
                elif "moveEntry(" in query:
                    moved = next(item for item in existing_entries["sitePage"] if item["id"] == variables["id"])
                    result = {"data": {"moveEntry": moved}}
                else:
                    assert "saveEntry(" in query
                    result = {"data": {"saveEntry": {**variables, "id": variables["id"] or "new-id"}}}
        return io.BytesIO(json.dumps(result).encode())

    monkeypatch.setattr(
        sys,
        "argv",
        ["setup_moss", "--cms-url", "http://cms.test/", "--name", "Replacement", "--headline", "Replacement"],
    )
    monkeypatch.setattr(Path, "exists", lambda self: True)
    monkeypatch.setattr(Path, "read_text", lambda self: env if self.name == ".env" else json.dumps(defaults))
    monkeypatch.setattr(Path, "write_text", lambda self, text: writes.update({self: text}))
    monkeypatch.setattr(Path, "chmod", lambda self, mode: modes.append((self, mode)))
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    script.main()

    schema = next(values for query, values in mutations if "saveContentType(" in query and values["key"] == "sitePage")
    assert schema["name"] == "Custom pages"
    assert schema["version"] == 4
    assert schema["fields"][0] == custom_field
    saves = [values for query, values in mutations if "saveEntry(" in query]
    assert not any(values["key"] == "siteProfile" for values in saves)
    for old_slug, new_slug in [("notes", "blog"), ("contact", "about"), ("projects", "projects")]:
        old = next(item for item in existing_entries["sitePage"] if item["slug"] == old_slug)
        saved = next(values for values in saves if values["id"] == old["id"])
        assert saved["slug"] == new_slug
        assert all(saved[key] == old[key] for key in ["id", "version", "status", "scheduledAt"])
        assert saved["data"]["body"] == old["data"]["body"]
    move = next(values for query, values in mutations if "moveEntry(" in query)
    assert move == {"id": "custom-project-id", "key": "siteProject", "version": 7}
    env_file = SCRIPT.parents[1] / ".env"
    assert len(writes) == 1
    saved_env = dict(line.split("=", 1) for line in writes[env_file].splitlines())
    assert saved_env == {
        "MOSS_PROJECT_ID": "project-id",
        "MOSS_DELIVERY_TOKEN": "kept-token",
        "MOSS_API_URL": "http://cms.test",
        "PORT": "9000",
        "OTHER": "kept",
        "SITE_PUBLIC_URL": "https://example.com",
    }
    assert modes == [(env_file, 0o600)]
    delivery = next(request for request in calls if request.full_url.endswith("/delivery/graphql"))
    assert delivery.get_header("Authorization") == "Bearer kept-token"
    assert delivery.get_header("X-moss-csrf") is None
