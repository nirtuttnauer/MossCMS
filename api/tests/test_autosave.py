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
