"""Repeatable assertions and synthetic bulk fixtures for the disposable acceptance API.

Only http://127.0.0.1:18111 and /tmp/moss-acceptance-20261011/cms.db are allowed.
Run with api/.venv/bin/python; use --help for browser-coordinated commands.
The original fixture, delivery token, and prior batch evidence are retained.
"""

import argparse
import json
import os
import sqlite3
import stat
import tempfile
import uuid
from pathlib import Path

import httpx

ROOT = Path("/tmp/moss-acceptance-20261011")
STATE = ROOT / "fixture.json"
API = "http://127.0.0.1:18111"
EMAIL = "acceptance@example.test"
PASSWORD = "synthetic-acceptance-password"
NAME = "Acceptance tester"
ENTRY_FIELDS = "id typeKey slug title data status version isLive publishedSnapshot"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def read_state(path=STATE):
    info = path.lstat()
    require(
        stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600,
        "Fixture state must be a regular mode-0600 file, never a symlink.",
    )
    with path.open() as source:
        return json.load(source)


def write_state(state, path=STATE):
    # Replace atomically with a private temporary file; never follow a state symlink.
    if path.exists() or path.is_symlink():
        read_state(path)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=".acceptance-", delete=False) as output:
        temporary = Path(output.name)
        try:
            os.fchmod(output.fileno(), 0o600)
            json.dump(state, output)
            output.flush()
            os.fsync(output.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    os.replace(temporary, path)


def fixture_project(state):
    require(ROOT.is_dir() and not ROOT.is_symlink(), "Refusing a redirected disposable fixture directory.")
    database = ROOT / "cms.db"
    require(database.is_file() and not database.is_symlink(), "Disposable fixture database is missing.")
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        rows = connection.execute(
            "SELECT m.project_id, u.id FROM memberships m JOIN users u ON u.id=m.user_id "
            "WHERE u.email=? AND u.name=? AND m.role=?",
            (EMAIL, NAME, "admin"),
        ).fetchall()
    require(
        len(rows) == 1 and rows[0][0] == state["project"],
        "Refusing a database without the exact synthetic fixture account/workspace.",
    )
    return rows[0]


class Fixture:
    def __init__(self, client, state):
        self.client, self.state = client, state
        project, user = fixture_project(state)
        require(str(client.base_url).rstrip("/") == API, "Only the fixed disposable loopback API is allowed.")
        response = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
        response.raise_for_status()
        response = client.get("/auth/me")
        response.raise_for_status()
        account = response.json()
        require(
            account["user"]["id"] == user and account["user"]["name"] == NAME and account["user"]["email"] == EMAIL,
            "Refusing a non-fixture server account.",
        )
        require(
            any(item["id"] == project and item["role"] == "admin" for item in account["projects"]),
            "Refusing a non-fixture server workspace.",
        )
        self.headers = {"x-moss-project": project, "x-moss-csrf": account["csrf"]}

    def gql(self, query, variables=None, delivery=False):
        headers = {"Authorization": f"Bearer {self.state['token']}"} if delivery else self.headers
        response = self.client.post(
            "/delivery/graphql" if delivery else "/graphql",
            headers=headers,
            json={"query": query, "variables": variables},
        )
        response.raise_for_status()
        result = response.json()
        require(not result.get("errors"), "Fixture GraphQL request failed; inspect the disposable API.")
        return result["data"]

    def batch(self, name):
        if name == "original":
            return {"type": "acceptanceBatch", "entries": self.state["batch"]}
        batch = self.state.get("batches", {}).get(name)
        require(batch is not None, "Batch is not seeded; run seed-batch first.")
        return batch

    def entries(self, name):
        batch = self.batch(name)
        records = [
            self.gql("query($id:ID!){entry(id:$id){" + ENTRY_FIELDS + "}}", {"id": item["id"]})["entry"]
            for item in batch["entries"]
        ]
        require(
            len(records) == 5 and all(item and item["typeKey"] == batch["type"] for item in records),
            "Expected exactly five entries from the selected synthetic batch type.",
        )
        return records

    def seed_batch(self, name):
        require(name != "original", "The original evidence batch is retained; use a separate browser batch.")
        require(name not in self.state.get("batches", {}), "Batch already seeded; use reset-batch explicitly.")
        key = f"acceptance{name.title()}Batch"
        types = self.gql("{contentTypes{key}}")["contentTypes"]
        require(not any(item["key"] == key for item in types), "Batch type already exists; refusing to overwrite it.")
        self.gql(
            "mutation($key:String!,$fields:JSON!){saveContentType(key:$key,name:$key,fields:$fields){key}}",
            {"key": key, "fields": [{"name": "title", "type": "text", "required": True}]},
        )
        entries = []
        for index in range(1, 6):
            entries.append(
                self.gql(
                    'mutation($key:String!,$slug:String!,$data:JSON!,$requestKey:String){saveEntry(typeKey:$key,slug:$slug,data:$data,status:"draft",requestKey:$requestKey){id version}}',
                    {
                        "key": key,
                        "slug": f"{name}-batch-{index}",
                        "data": {"title": f"{name.title()} Batch {index}"},
                        "requestKey": str(uuid.uuid4()),
                    },
                )["saveEntry"]
            )
        self.state.setdefault("batches", {})[name] = {"type": key, "entries": entries}
        write_state(self.state)
        print(f"Seeded five draft entries in {key}; prior fixture evidence retained.")

    def reset_batch(self, name):
        batch = self.batch(name)
        records = self.entries(name)
        restored = []
        for item in records:
            restored.append(
                self.gql(
                    "mutation($id:ID!,$version:Int!){restoreEntry(id:$id,number:1,version:$version){id version}}",
                    {"id": item["id"], "version": item["version"]},
                )["restoreEntry"]
            )
        batch["entries"] = restored
        if name == "original":
            self.state["batch"] = restored
        write_state(self.state)
        print(
            "Restored the five original synthetic revisions as drafts; versions: "
            + ",".join(str(item["version"]) for item in restored)
        )

    def bump(self, name, index):
        item = self.entries(name)[index - 1]
        require(item["status"] != "deleted", "Choose an active synthetic entry to force a version conflict.")
        data = {**item["data"], "title": item["title"] + " (concurrent fixture edit)"}
        result = self.gql(
            "mutation($id:ID!,$version:Int!,$type:String!,$slug:String!,$data:JSON!,$requestKey:String!){saveDraft(id:$id,version:$version,typeKey:$type,slug:$slug,data:$data,requestKey:$requestKey){version}}",
            {
                "id": item["id"],
                "version": item["version"],
                "type": item["typeKey"],
                "slug": item["slug"],
                "data": data,
                "requestKey": str(uuid.uuid4()),
            },
        )["saveDraft"]
        print(f"Synthetic batch item {index} version changed {item['version']}→{result['version']}.")

    def assert_batch(self, name, statuses, versions):
        records = self.entries(name)
        actual_statuses = [item["status"] for item in records]
        actual_versions = [item["version"] for item in records]
        require(actual_statuses == statuses, f"Batch statuses differ: actual {actual_statuses}, expected {statuses}.")
        require(actual_versions == versions, f"Batch versions differ: actual {actual_versions}, expected {versions}.")
        print(f"Exact batch assertions passed: statuses={actual_statuses}, versions={actual_versions}.")

    def assert_delivery(self, slug, expected_body, expected_draft_body):
        query = 'query($slug:String!){entries(typeKey:"article",search:$slug,first:100){nodes{id slug data}}}'
        delivered = self.gql(query, {"slug": slug}, delivery=True)["entries"]["nodes"]
        delivered = [item for item in delivered if item["slug"] == slug]
        require(len(delivered) == 1, "Expected exactly one matching published article.")
        require(
            delivered[0]["data"].get("body") == expected_body,
            "Delivered article body differs from the exact expected value.",
        )
        draft = self.gql("query($id:ID!){entry(id:$id){" + ENTRY_FIELDS + "}}", {"id": delivered[0]["id"]})["entry"]
        require(
            draft["data"].get("body") == expected_draft_body,
            "Saved working article body differs from the exact expected value.",
        )
        require(
            draft["isLive"] and draft["publishedSnapshot"]["data"].get("body") == expected_body,
            "Published snapshot disagrees with live delivery.",
        )
        print("Exact draft/live/delivery assertions passed; no publication outcome inferred from UI text.")


def self_check():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "state.json"
        write_state({"token": "synthetic-only"}, path)
        require(stat.S_IMODE(path.stat().st_mode) == 0o600, "State permissions self-check failed.")
        require(read_state(path) == {"token": "synthetic-only"}, "State roundtrip self-check failed.")
        link = Path(directory) / "link.json"
        link.symlink_to(path)
        try:
            write_state({}, link)
        except RuntimeError:
            pass
        else:
            raise RuntimeError("State symlink guard self-check failed.")
    print("Private atomic state writes and symlink guard self-check passed; no API contacted.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("self-check")
    for name in ("seed-batch", "reset-batch", "bump-batch-version", "assert-batch"):
        command = commands.add_parser(name)
        command.add_argument("--name", choices=["original", "safari", "chromium"], required=True)
        if name == "bump-batch-version":
            command.add_argument("--item", type=int, choices=range(1, 6), required=True)
        elif name == "assert-batch":
            command.add_argument(
                "--statuses", required=True, help="Five comma-separated statuses, in original batch order."
            )
            command.add_argument(
                "--versions", required=True, help="Five comma-separated exact versions, in original batch order."
            )
    delivery = commands.add_parser("assert-delivery")
    delivery.add_argument("--slug", default="browser-acceptance-article")
    delivery.add_argument("--expected-body", required=True)
    delivery.add_argument("--expected-draft-body", required=True)
    args = parser.parse_args()
    if args.command == "self-check":
        self_check()
        return
    state = read_state()
    with httpx.Client(base_url=API, timeout=30, trust_env=False, follow_redirects=False) as client:
        fixture = Fixture(client, state)
        if args.command == "seed-batch":
            fixture.seed_batch(args.name)
        elif args.command == "reset-batch":
            fixture.reset_batch(args.name)
        elif args.command == "bump-batch-version":
            fixture.bump(args.name, args.item)
        elif args.command == "assert-batch":
            statuses, versions = args.statuses.split(","), [int(value) for value in args.versions.split(",")]
            require(len(statuses) == 5 and len(versions) == 5, "Provide exactly five statuses and versions.")
            fixture.assert_batch(args.name, statuses, versions)
        else:
            fixture.assert_delivery(args.slug, args.expected_body, args.expected_draft_body)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
    except (httpx.HTTPError, OSError, KeyError, ValueError, sqlite3.Error):
        # Do not print response bodies, state or authorization headers on failure.
        raise SystemExit(
            "Fixture command failed. Check arguments, private fixture state, and the disposable API."
        ) from None
