from datetime import timedelta
from app.models import now
from conftest import define, entry, gql
from test_cms import delivery, invited

DRAFT = 'mutation($key:String!,$slug:String!,$data:JSON!,$id:ID,$version:Int){saveDraft(requestKey:$key,typeKey:"article",slug:$slug,data:$data,id:$id,version:$version){id version data scheduledRevision isLive}}'


def test_draft_replay_creation_and_receipt_are_scoped(app, client, admin):
    define(client, admin)
    args = dict(key="draft_request_00001", slug="hello", data={"title": "Hello"})
    first = gql(client, admin, DRAFT, args)
    assert "errors" not in first, first
    assert gql(client, admin, DRAFT, args) == first
    assert gql(client, admin, "{entries{total}}")["data"]["entries"]["total"] == 1
    assert (
        gql(client, admin, DRAFT, {**args, "data": {"title": "Different"}})["errors"][0]["extensions"]["code"]
        == "CONFLICT"
    )
    query = "query($key:String!){draftReceipt(key:$key){id version}}"
    assert gql(client, admin, query, {"key": args["key"]})["data"]["draftReceipt"]["version"] == 1
    other, headers, _ = invited(app, client, admin)
    assert gql(other, headers, query, {"key": args["key"]})["data"]["draftReceipt"] is None
    token = delivery(client, admin)
    assert "errors" in gql(client, token, query, {"key": args["key"]}, delivery=True)


def test_draft_update_preserves_live_schedule_and_rejects_stale_version(client, admin):
    define(client, admin)
    live = entry(client, admin, status="published")["data"]["saveEntry"]
    scheduled = entry(
        client,
        admin,
        status="scheduled",
        id=live["id"],
        version=live["version"],
        scheduledAt=(now() + timedelta(hours=1)).isoformat(),
    )["data"]["saveEntry"]
    args = dict(
        key="draft_request_00002", slug="new-url", data={"title": "New"}, id=live["id"], version=scheduled["version"]
    )
    saved = gql(client, admin, DRAFT, args)["data"]["saveDraft"]
    assert saved["isLive"] and saved["scheduledRevision"] == scheduled["version"]
    assert (
        gql(client, admin, DRAFT, {**args, "key": "draft_request_00003"})["errors"][0]["extensions"]["code"]
        == "CONFLICT"
    )


def test_publication_receipt_prevents_duplicate_events_and_preserves_request_id(app, client, admin):
    from sqlalchemy import select
    from app.models import PublicationEvent

    define(client, admin)
    query = 'mutation($key:String!){saveEntry(typeKey:"article",slug:"post",data:{title:"Hello"},status:"published",requestKey:$key){id version publishedRevision}}'
    args = {"key": "publish_request_00001"}
    first = gql(client, admin, query, args)
    assert gql(client, admin, query, args) == first
    assert (
        gql(client, admin, '{draftReceipt(key:"publish_request_00001"){id}}')["data"]["draftReceipt"]["id"]
        == first["data"]["saveEntry"]["id"]
    )
    with app.state.db() as session:
        assert len(session.scalars(select(PublicationEvent)).all()) == 1
    failed = client.post(
        "/graphql", headers=admin, json={"query": query.replace("Hello", "Changed"), "variables": args}
    )
    assert failed.json()["errors"][0]["extensions"]["requestId"] == failed.headers["x-request-id"]
    assert failed.json()["errors"][0]["extensions"]["code"] == "CONFLICT"
    assert failed.headers["server-timing"].startswith("app;dur=")


def test_graphql_error_logs_do_not_include_inline_body_secrets(client, admin, caplog):
    import logging

    with caplog.at_level(logging.WARNING):
        gql(
            client, admin, 'mutation{saveEntry(typeKey:"missing",slug:"x",data:{title:"DO_NOT_LOG_INLINE_SECRET"}){id}}'
        )
    assert "DO_NOT_LOG_INLINE_SECRET" not in caplog.text
    assert "graphqlErrorCodes" in caplog.text
