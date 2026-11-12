# MOSS-071 read-only MCP

Local evidence for a stdio MCP server that lists and gets published entries with a delivery token. Label: `local`.

The separate ticket file named in the prompt was not in the upload. The checks below are the outcome in that prompt.

| | |
| --- | --- |
| Base SHA | `b6c66870b98af990ee91766e5a965e823bf2b03d` |
| Verified SHA | `8bb8f896c34d0baae901309f62f4f2d560442b03` |
| Date | 2026-11-12 (UTC), `scripts/verify.sh` started `2026-11-12T14:56:30Z` |
| `git status --porcelain` at the start of `scripts/verify.sh` | empty |
| Evidence directory | [8bb8f89](8bb8f89/) |

`scripts/verify.sh MOSS-071` exited 1 at `pytest-sqlite`. The failing test is `tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests`. The same test fails on the base SHA. `starters/nextjs/package.json` is not covered by `.github/dependabot.yml`. Those two paths were left unchanged. The later checks use the same commands as `scripts/verify.sh` and are recorded in the evidence directory. `pip-audit` was run again after `python3.12-venv` was installed; that rerun exited 0 with `No known vulnerabilities found`.

On this VM, `iptables-legacy` had `FORWARD` policy `DROP`, so containers on a Compose bridge could not reach each other. An accept rule for interfaces named `br-*` was added in the VM. It is not a repository change. After that rule, `tests/test_private_admin_compose.py::test_variant_a_proxy_and_variant_b_private_listener` passes on the base SHA and on the verified SHA.

## Counts

SQLite on the base SHA, full `pytest -m "not postgres"`, before the bridge rule: 496 passed, 2 failed, 4 deselected. The failures were the dependabot test and the Compose proxy test (curl timed out). After the bridge rule the proxy test passes on the base SHA, which leaves 497 passed, 1 failed, 4 deselected.

PostgreSQL on the base SHA, full `pytest`, while the SQLite run was also using Compose project `moss059`: 500 passed, 2 failed. The proxy failure in that run was a container collision. Run by itself on the base SHA after the bridge rule, the proxy test passes.

| Suite | Base `b6c6687` | Verified `8bb8f89` |
| --- | --- | --- |
| SQLite | 497 passed, 1 failed, 4 deselected, 0 skipped | 504 passed, 1 failed, 4 deselected, 0 skipped |
| PostgreSQL | 501 passed, 1 failed, 0 deselected, 0 skipped | 508 passed, 1 failed, 0 deselected, 0 skipped |
| Web | unchanged tree | 356 passed, 0 skipped, 36 files |
| Example site | unchanged tree | 50 passed, 0 failed, 0 skipped |
| Production smoke | unchanged tree | 2 passed, 0 skipped |

The seven additional passes are `tests/test_mcp.py`. The one failure in both API runs is the dependabot test. The four deselected ids are the PostgreSQL-only tests already listed in `api/tests/required_runs.json`. No runtime skip or xfail was reported. `pip-audit`, `npm audit`, and `gitleaks` exited 0 (`gitleaks`: no leaks found).

## What the server does

From the `api` directory:

```sh
MOSS_DELIVERY_TOKEN=... python -m app.mcp
```

The token is read from the environment. A command-line argument is rejected and is not written to stderr. `MOSS_PROJECT`, when set, must be the token's workspace. `MOSS_SKIP_AUTH` does not authenticate this process.

The tools are `list_published_entries` and `get_published_entry`. Drafts are left out. A scheduled entry that has not gone live is left out. A live entry that also has a pending schedule returns the live snapshot, and the scheduled title and body are absent. Titles and bodies are returned as stored, including Hebrew letters and niqqud. A missing, expired, wrong-workspace, or non-delivery token gets `A valid delivery token is required.` and no entries. The raw token is redacted from log lines. The database session is read-only. No drafts token kind was added.

## Criteria

| Criterion | Result |
| --- | --- |
| Stdio entry `python -m app.mcp` | Met. `test_module_entry_and_rejected_argv` starts that module. |
| Delivery token authentication | Met. Missing, blank, expired, session, revoked, and non-delivery rows are refused. |
| List and get published entries | Met. Payloads match `GET /delivery/entries` and `GET /delivery/entries/{id}`. |
| Hebrew and niqqud titles and bodies stay intact | Met, including a newline inside a body so each MCP message stays on one line. |
| Drafts are not returned | Met. |
| Scheduled entries are not returned | Met for an entry that has not gone live. A live entry with a pending schedule returns the live snapshot. |
| Wrong-project tokens fail closed | Met. `MOSS_PROJECT` and a `projectId` argument must match the token workspace. An id from another workspace is not returned. |
| Raw token is not logged | Met. Log lines and stdio were checked, and a command-line value is not echoed. |
| No drafts-only token and no mutating tools | Met. Kind `draft` is refused. `save_entry` does not change the published document. |
| Delivery REST, GraphQL, and the SEO audit stay as they are | Met. Product diff is `api/app/mcp.py` and `api/tests/test_mcp.py`. |
