"""Seed only the disposable editor acceptance API on loopback port 18111.

Initialize the fresh temporary app first as described in docs/editor-acceptance-2026-10-11.md.
This fixture adds synthetic references, validation fields and five bulk-trash entries.
"""

import json
import os
from pathlib import Path

import httpx


def main():
    with httpx.Client(base_url="http://127.0.0.1:18111", timeout=30) as client:
        login = client.post(
            "/auth/login",
            json={
                "email": "acceptance@example.test",
                "password": "synthetic-acceptance-password",
            },
        )
        login.raise_for_status()
        account = client.get("/auth/me").json()
        assert account["user"]["name"] == "Acceptance tester", "Refusing a non-fixture account"
        project = account["projects"][0]
        headers = {"x-moss-project": project["id"], "x-moss-csrf": account["csrf"]}

        def gql(query, variables=None):
            response = client.post(
                "/graphql",
                headers=headers,
                json={"query": query, "variables": variables},
            )
            response.raise_for_status()
            result = response.json()
            assert "errors" not in result, result.get("errors")
            return result["data"]

        types = gql("{contentTypes{key name fields version}}")["contentTypes"]
        assert not any(t["key"] in {"acceptancePerson", "acceptanceBatch"} for t in types), (
            "Use a fresh disposable fixture; do not seed twice"
        )
        save_type = "mutation($key:String!,$fields:JSON!,$version:Int){saveContentType(key:$key,name:$key,fields:$fields,version:$version){key}}"
        gql(
            save_type,
            {
                "key": "acceptancePerson",
                "fields": [{"name": "title", "type": "text", "required": True}],
            },
        )
        save = 'mutation($key:String!,$slug:String!,$data:JSON!){saveEntry(typeKey:$key,slug:$slug,data:$data,status:"draft"){id version}}'
        references = []
        for i in range(160):
            references.append(
                gql(
                    save,
                    {
                        "key": "acceptancePerson",
                        "slug": f"person-{i:03}",
                        "data": {"title": f"Acceptance person {i:03}"},
                    },
                )["saveEntry"]
            )
        article = next(t for t in types if t["key"] == "article")
        fields = article["fields"] + [
            {
                "name": "related",
                "label": "Related person",
                "type": "reference",
                "target": "acceptancePerson",
            },
            {
                "name": "details",
                "type": "object",
                "fields": [{"name": "score", "type": "number", "required": True}],
            },
            {
                "name": "localizedHeading",
                "label": "Localized heading",
                "type": "text",
                "localized": True,
            },
        ]
        gql(
            save_type,
            {"key": "article", "fields": fields, "version": article["version"]},
        )
        gql(
            save_type,
            {
                "key": "acceptanceBatch",
                "fields": [{"name": "title", "type": "text", "required": True}],
            },
        )
        batch = [
            gql(
                save,
                {
                    "key": "acceptanceBatch",
                    "slug": f"batch-{i}",
                    "data": {"title": f"Batch {i}"},
                },
            )["saveEntry"]
            for i in range(1, 6)
        ]
        token = client.post(
            "/api/tokens",
            headers=headers,
            json={
                "name": "HTTP acceptance assertions",
                "scopes": ["article"],
                "days": 1,
            },
        )
        token.raise_for_status()
        state = {
            "project": project["id"],
            "references": references,
            "batch": batch,
            "token": token.json()["token"],
        }
        target = Path("/tmp/moss-acceptance-20261011/fixture.json")
        with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as output:
            json.dump(state, output)
        print("Seeded 160 references and five bulk-trash entries in the disposable fixture.")


if __name__ == "__main__":
    main()
