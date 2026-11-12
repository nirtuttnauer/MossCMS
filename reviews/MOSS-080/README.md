# MOSS-080 workspace archive routes

local

Recorded 12 November 2026 (UTC). `scripts/verify.sh MOSS-080` ran on a clean tree at `599803c210e3e4e177bf4b9987bbd2f035fd3fc5`. The script refuses a dirty tree. It exited 1 at the SQLite pytest step. The same dependabot test fails on main `b6c6687`. The remaining script commands were then run locally and their logs are in this folder. There is no audit ignore and no allowed-skip list.

## Code under test

| | |
| --- | --- |
| Base | `b6c66870b98af990ee91766e5a965e823bf2b03d` (main) |
| SHA tested | `599803c210e3e4e177bf4b9987bbd2f035fd3fc5` |
| Branch | `cursor/workspace-archive-auth-54c1` |
| `git status --porcelain` at the start of `scripts/verify.sh` | empty (clean) |
| Date | 2026-11-12T14:50:53Z through 2026-11-12T15:01:47Z |
| Command | `scripts/verify.sh MOSS-080` |
| `scripts/verify.sh` exit | 1 |
| Logs | [599803c](599803c/) |

The evidence files were committed after the run, so the pull request head is the evidence commit. The counts below are for `599803c`.

## What the tests lock

`api/tests/test_workspace_migration.py` extends the browser archive routes:

- Limits, download, and upload return 401 `Sign in required.` when the session cookie is absent, including when a project header is present.
- A delivery token sent as `Authorization: Bearer`, or placed in the session cookie, is rejected with that same 401. The signed-in operator can still read limits.
- Zip members and upload filenames using `..`, an absolute path, `%2e%2e`, `..%2f`, double-encoded `%252e%252e`, or a backslash do not write or return a planted file outside the temp directory. Member traversal returns 422. A traversal upload filename on a valid archive still previews into an empty workspace.
- Export returns 422 and does not return planted bytes when an asset key is `..` or absolute.
- Hebrew project, entry, asset, and upload names, and Hebrew entry content, export and import with status 200. A Hebrew zip member name returns 422.

`api/app/workspace_migration.py` and `api/app/portability.py` are unchanged. The new tests pass against the routes as they stand on main.

## Counts against main `b6c6687`

Main commands, from a detached worktree at `b6c66870b98af990ee91766e5a965e823bf2b03d`:

| Command | When (UTC) | Exit | Result |
| --- | --- | --- | --- |
| `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest -m "not postgres"` | 2026-11-12T14:41:58Z–14:45:46Z | 1 | 497 passed, 1 failed, 4 deselected, 0 skipped |
| `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=postgres MOSS_TEST_DATABASE_URL=postgresql+psycopg://pg:***@localhost:5432/postgres uv run pytest` | 2026-11-12T14:46:14Z–14:50:28Z | 1 | 501 passed, 1 failed, 0 deselected, 0 skipped |
| `npm ci && npm test` in `web` | 2026-11-12T14:50:50Z | 0 | 356 passed (36 files), 0 skipped |
| `npm ci && npm test` in `example-site` | same window, ended 14:51:12Z | 0 | 50 passed, 0 failed, 0 skipped |

The failed id on both main runs is `tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests`. The assertion is `starters/nextjs/package.json (npm /starters/nextjs) is not covered by .github/dependabot.yml`. Those two paths are outside this ticket. The four SQLite deselected ids match main and the head:

- `tests/test_concurrency.py::test_postgres_workers_skip_locked_rows_and_claim_once`
- `tests/test_indexing.py::test_common_string_count_avoids_per_match_probes_in_generic_postgres_plan`
- `tests/test_postgres_product_migration.py::test_postgres_0009_preserves_localized_live_scheduled_and_revision_data`
- `tests/test_search.py::test_generic_postgres_substring_plan_uses_trigrams_and_rechecks_matches`

| Run | Main collected / passed / failed | This run collected / passed / failed | Deselected | Skipped |
| --- | --- | --- | --- | --- |
| SQLite `-m "not postgres"` | 502 / 497 / 1 | 518 / 513 / 1 | 4 | 0 |
| PostgreSQL, no marker filter | 502 / 501 / 1 | 518 / 517 / 1 | 0 | 0 |
| web | 356 (36 files) | 356 (36 files) |  | 0 |
| example-site | 50 | 50 |  | 0 |
| production Playwright | not run on the base worktree | 2 |  | 0 |

The sixteen additional passed tests are in `tests/test_workspace_migration.py`. Web, example-site, and production sources are the same as main. The head production run passed 2 and skipped 0. [counts.txt](599803c/counts.txt).

## Commands and results

`scripts/verify.sh MOSS-080` exited 1 at `pytest-sqlite`. Later rows are the same commands from that script, continued in this shell and labeled `local`. `pip-audit` and `gitleaks` were run again once the evidence variable and gitleaks directory were available; those reruns are the recorded exits.

| Command | Exit |
| --- | --- |
| `uv sync --locked --group dev` | 0 |
| `ruff check` and `ruff format --check` for `app tests migrations` | 0 |
| ruff check/format of scripts, example-site setup, telemetry smoke | 0 |
| `mypy app` | 0 |
| SQLite required run | 1 |
| PostgreSQL required run in the throwaway container | 1 |
| `tests/verify_required_runs.py` | 1 |
| OTLP Collector smoke | 0 |
| web `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 |
| example-site `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 |
| `pip-audit` against the frozen lock | 0 |
| `npm audit` web, example-site, and ci | 0 |
| `gitleaks` on `git archive HEAD` | 0 |
| production image, compose, Playwright, teardown | 0 |

SQLite and PostgreSQL each fail on the dependabot test named above and pass the new archive tests. `verify_required_runs.py` reports that same id. Skip scans of the SQLite, PostgreSQL, web, example-site, and production logs exited 0. No `--ignore-vuln`, npm override, or gitleaks allowlist was added.
