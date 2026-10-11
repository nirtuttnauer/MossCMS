import argparse
import copy
import importlib.util
import io
import json
import sys
import urllib.request
import urllib.error
from types import SimpleNamespace
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "example-site/scripts/setup_moss.py"
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


@pytest.mark.parametrize("status", [{"authSkipped": True}])
def test_main_rejects_bypass_before_accessing_account_or_writing(status, monkeypatch):
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
    monkeypatch.setattr(urllib.request, "build_opener", lambda *a: SimpleNamespace(open=urlopen))
    with pytest.raises(SystemExit, match="Disable MOSS_SKIP_AUTH"):
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
            result = {"authSkipped": False, "initialized": True}
        elif path == "/auth/login":
            assert payload == {"email": "admin@example.test", "password": "test-password"}
            result = {}
        elif path == "/auth/me":
            result = {
                "csrf": "csrf-token",
                "projects": [
                    {
                        "name": "Example website",
                        "id": "project-id",
                        "role": "admin",
                        "previewOrigin": "https://kept.example",
                    }
                ],
            }
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
    monkeypatch.setattr(urllib.request, "build_opener", lambda *a: SimpleNamespace(open=urlopen))
    monkeypatch.setenv("MOSS_ADMIN_EMAIL", "admin@example.test")
    monkeypatch.setenv("MOSS_ADMIN_PASSWORD", "test-password")
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    script.main()

    schema = next(values for query, values in mutations if "saveContentType(" in query and values["key"] == "sitePage")
    assert schema["name"] == "Custom pages"
    assert schema["version"] == 4
    assert schema["fields"][0] == custom_field
    saves = [values for query, values in mutations if "saveEntry(" in query]
    example = next(values for values in saves if values["slug"] == "example-website")
    assert example["key"] == "siteProject"
    assert example["data"]["title"] == "Moss Example"
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
        "SITE_PUBLIC_URL": "http://localhost:5174",
    }
    assert modes == [(env_file, 0o600)]
    delivery = next(request for request in calls if request.full_url.endswith("/delivery/graphql"))
    assert delivery.get_header("Authorization") == "Bearer kept-token"
    assert delivery.get_header("X-moss-csrf") is None


def test_authenticated_bootstrap_retains_membership_content_and_token(client, admin, tmp_path, monkeypatch):
    script = load_script()
    root = tmp_path / "example-site"
    (root / "scripts").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "src/content-defaults.json").write_text((SCRIPT.parents[1] / "src/content-defaults.json").read_text())
    monkeypatch.setattr(script, "__file__", str(root / "scripts/setup_moss.py"))
    monkeypatch.setattr(sys, "argv", ["setup_moss", "--cms-url", "http://cms.test", "--email", "admin@example.com"])
    monkeypatch.setattr(script.getpass, "getpass", lambda prompt: "secure-test-password")
    monkeypatch.delenv("MOSS_ADMIN_PASSWORD", raising=False)

    def open_request(req, **kwargs):
        path = req.full_url.removeprefix("http://cms.test")
        response = client.request(req.get_method(), path, content=req.data, headers=dict(req.header_items()))
        if response.status_code >= 400:
            raise urllib.error.HTTPError(
                req.full_url, response.status_code, "rejected", {}, io.BytesIO(response.content)
            )
        return io.BytesIO(response.content)

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: SimpleNamespace(open=open_request))
    monkeypatch.setattr(urllib.request, "urlopen", open_request)
    script.main()
    values = dict(line.split("=", 1) for line in (root / ".env").read_text().splitlines())
    project_id = values["MOSS_PROJECT_ID"]
    account = client.get("/auth/me").json()
    assert next(p for p in account["projects"] if p["id"] == project_id)["role"] == "admin"
    assert next(p for p in account["projects"] if p["id"] == project_id)["previewOrigin"] == "http://localhost:5174"
    headers = {"x-moss-project": project_id, "x-moss-csrf": account["csrf"]}
    entries = client.post(
        "/graphql", headers=headers, json={"query": '{entries(typeKey:"siteProfile"){nodes{id slug data version}}}'}
    ).json()["data"]["entries"]["nodes"]
    profile = entries[0]
    profile["data"]["name"] = "My retained website"
    from conftest import gql

    saved = gql(
        client,
        headers,
        'mutation($id:ID!,$version:Int!,$data:JSON!){saveEntry(id:$id,version:$version,typeKey:"siteProfile",slug:"profile",data:$data,status:"draft"){id}}',
        {"id": profile["id"], "version": profile["version"], "data": profile["data"]},
    )
    assert "errors" not in saved
    script.main()
    assert (root / ".env").read_text().split("MOSS_DELIVERY_TOKEN=")[1].splitlines()[0] == values["MOSS_DELIVERY_TOKEN"]
    client.post("/auth/logout", headers={"x-moss-csrf": client.get("/auth/me").json()["csrf"]})
    client.post("/auth/login", json={"email": "admin@example.com", "password": "secure-test-password"})
    assert project_id in [p["id"] for p in client.get("/auth/me").json()["projects"]]
    result = gql(client, {"x-moss-project": project_id}, '{entries(typeKey:"siteProfile"){nodes{data}}}')
    assert result["data"]["entries"]["nodes"][0]["data"]["name"] == "My retained website"
    delivery = gql(
        client,
        {"Authorization": "Bearer " + values["MOSS_DELIVERY_TOKEN"]},
        "{entries(first:1){nodes{id}}}",
        delivery=True,
    )
    assert delivery["data"]["entries"]["nodes"]
