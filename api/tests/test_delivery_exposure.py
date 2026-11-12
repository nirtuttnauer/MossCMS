"""Delivery GraphQL rejects mutations and introspection of admin types."""

from app.graphql import generated_schema
from conftest import define, entry, gql


def _names(schema):
    return set(schema._schema.type_map)


def test_delivery_token_rejects_every_mutation_and_admin_type_introspection(client, admin):
    editorial = generated_schema([], delivery=False)
    delivery = generated_schema([], delivery=True)
    admin_types = sorted(_names(editorial) - _names(delivery))
    assert admin_types == ["Mutation"]
    issued = client.post("/api/tokens", headers=admin, json={"name": "site", "scopes": [], "days": 1})
    assert issued.status_code == 200, issued.text
    headers = {"Authorization": "Bearer " + issued.json()["token"]}
    define(client, admin)
    saved = entry(client, admin, "moss059-live", status="draft")
    assert "errors" not in saved, saved
    record = saved["data"]["saveEntry"]

    mutation_names = list(editorial._schema.get_type("Mutation").fields)
    assert "deleteEntry" in mutation_names
    for name in mutation_names:
        response = client.post("/delivery/graphql", json={"query": f"mutation {{ {name} }}"}, headers=headers)
        body = response.json()
        assert response.status_code in {200, 400}, (name, response.status_code, response.text)
        assert not body.get("data"), (name, body)
        assert body.get("errors"), (name, body)

    targeted = client.post(
        "/delivery/graphql",
        json={
            "query": "mutation($id:ID!,$version:Int!){deleteEntry(id:$id,version:$version)}",
            "variables": {"id": record["id"], "version": record["version"]},
        },
        headers=headers,
    )
    assert targeted.status_code == 200, targeted.text
    assert targeted.json().get("errors")
    assert targeted.json().get("data") is None
    kept = gql(client, admin, "query($id:ID!){entry(id:$id){status}}", {"id": record["id"]})
    assert kept["data"]["entry"]["status"] == "draft"

    intro = client.post(
        "/delivery/graphql",
        json={
            "query": "{ schemaInfo: __schema { mutationType { name fields { name } } types { name } } "
            'found: __type(name: "Mutation") { name fields { name } } }'
        },
        headers=headers,
    )
    assert intro.status_code == 200, intro.text
    payload = intro.json()["data"]
    assert payload["schemaInfo"]["mutationType"] is None
    assert payload["found"] is None
    assert "Mutation" not in {item["name"] for item in payload["schemaInfo"]["types"]}
    for name in admin_types:
        found = client.post(
            "/delivery/graphql",
            json={
                "query": "query($name:String!){ found: __type(name: $name) { name fields { name } } }",
                "variables": {"name": name},
            },
            headers=headers,
        )
        assert found.status_code == 200, found.text
        assert found.json()["data"]["found"] is None
