# MOSS-072 local verification

label: local

| | |
| --- | --- |
| Base | `b6c66870b98af990ee91766e5a965e823bf2b03d` |
| Verified product tree | `592607fcbf2e17c490eb870430681828e938dcdc` |
| Clean status | `reviews/MOSS-072/592607f/summary.txt` records an empty `git status --porcelain` when `scripts/verify.sh MOSS-072` started |
| Started | 2026-11-12T14:49:04Z |
| Evidence finished | 2026-11-12T15:21:11Z (base PostgreSQL pytest) |

`scripts/verify.sh MOSS-072` was run on that product tree and exited 1 at `pytest-sqlite`. The failure is `tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests`: `starters/nextjs/package.json` is not covered by `.github/dependabot.yml`. The same assertion fails on main `b6c6687` for both SQLite and PostgreSQL. Those two paths were not edited. No ignore, allowlist, skip, or xfail was added.

The script stops on that SQLite failure. The later steps from `scripts/verify.sh` were run with the same commands and logged under `reviews/MOSS-072/592607f/`. Exit codes are in `exit-codes.txt`. `pytest-sqlite`, `pytest-postgres`, and `verify-required-runs` are exit 1 for the dependabot assertion. Every other recorded step is exit 0.

The commit that adds `reviews/MOSS-072/` sits on top of `592607f`. Product files at that later commit match the verified tree.

## Counts

| Suite | Base `b6c6687` | Product tree `592607f` |
| --- | --- | --- |
| API pytest, SQLite, `-m "not postgres"` | 1 failed, 497 passed, 4 deselected, 0 skipped (collected 502) | 1 failed, 502 passed, 4 deselected, 0 skipped (collected 507) |
| API pytest, PostgreSQL | 1 failed, 501 passed, 0 deselected, 0 skipped (collected 502) | 1 failed, 506 passed, 0 deselected, 0 skipped (collected 507) |
| Admin web vitest | not re-run; `web/` matches the base | 36 files, 356 passed, 0 skipped |
| Example site `node --test` | not re-run; `example-site/` matches the base | 50 pass, 0 fail, 0 skipped |
| Production Playwright | not re-run on the base | 2 passed |

The API delta is the five tests in `api/tests/test_draft_tokens.py`. The failure on both trees is the dependabot manifest check.

The four PostgreSQL-only tests deselected on SQLite are the committed list in `api/tests/required_runs.json`. They were deselected on both SQLite runs and passed in both PostgreSQL runs:

- `tests/test_concurrency.py::test_postgres_workers_skip_locked_rows_and_claim_once`
- `tests/test_indexing.py::test_common_string_count_avoids_per_match_probes_in_generic_postgres_plan`
- `tests/test_postgres_product_migration.py::test_postgres_0009_preserves_localized_live_scheduled_and_revision_data`
- `tests/test_search.py::test_generic_postgres_substring_plan_uses_trigrams_and_rechecks_matches`

`verify_required_runs.py` on the product tree reported empty skipped lists. It exited 1 because the dependabot test did not pass in either required run.

## Base commands

From a worktree of `b6c6687` at `/tmp/moss-base` (label local). Pytest was the product-tree virtualenv binary, with the working directory in the worktree, so collection used the base tests.

- `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite /agent/repos/MossCMS/api/.venv/bin/pytest -m "not postgres" -q --tb=no` in `/tmp/moss-base/api` — exit 1, 2026-11-12T14:53:31Z. Log: `reviews/MOSS-072/b6c6687/pytest-sqlite.txt`.
- PostgreSQL 17 container started the way `scripts/verify.sh` starts it, then `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=postgres /agent/repos/MossCMS/api/.venv/bin/pytest` in `/tmp/moss-base/api` — exit 1, 2026-11-12T15:16:56Z. Logs: `reviews/MOSS-072/b6c6687/postgres-container.txt` and `pytest-postgres.txt`.

## Product-tree commands

`scripts/verify.sh MOSS-072` from a clean tree at `592607f` (exit 1 at pytest-sqlite, 187.49s). Steps that finished inside the script, all exit 0: `uv sync --locked --group dev`, ruff check and format, ruff on scripts, mypy.

Continued with the same commands as the rest of `scripts/verify.sh` (label local):

- PostgreSQL pytest — exit 1, 259.95s, same dependabot assertion, 506 passed. Log: `pytest-postgres.txt`.
- `uv run python tests/verify_required_runs.py` — exit 1. Log: `verify-required-runs.txt`.
- OpenTelemetry collector smoke — exit 0. Log: `otel.txt`.
- `npm ci` in `web/`, then `npm run check && npm test && npm run build && npm audit --audit-level=high` — exit 0. Logs: `web-npm-ci.txt`, `web.txt`.
- Same npm sequence in `example-site/` — exit 0. Logs: `example-site-npm-ci.txt`, `example-site.txt`.
- `uv export --frozen --all-groups --no-emit-project` then `pip-audit` — exit 0, `No known vulnerabilities found`. Logs: `requirements.txt`, `pip-audit.txt`.
- `npm audit` in `web/`, `example-site/`, and `ci/` — exit 0, `found 0 vulnerabilities`.
- `gitleaks detect` on `git archive HEAD` — exit 0, no leaks found. Log: `gitleaks.txt`.
- `npm ci` in `ci/` — exit 0.
- `npx playwright install --with-deps chromium` in `ci/` — exit 0.
- `docker build --tag mosscms:smoke .` — exit 0.
- `docker compose -f ci/compose.yaml -p mosscms-smoke up --no-build -d --wait --wait-timeout 180` — exit 0.
- `npm test` in `ci/` — exit 0, 2 passed. Log: `production-test.txt`.
- `docker compose -f ci/compose.yaml -p mosscms-smoke down --volumes` — exit 0.

## Environment note

Before the recorded SQLite run, `test_private_admin_compose` timed out on the proxy request. The host `iptables-legacy` `FORWARD` policy was `DROP`, so packets from the compose bridge did not reach the app. After `iptables-legacy -P FORWARD ACCEPT`, that test passed. It is included in the 502 SQLite passed tests and the 506 PostgreSQL passed tests. The policy change is on the machine, not in the product diff.

## Acceptance

- Kind `drafts` is issued by `issue_draft_token` and recognized by `identify(..., drafts=True)` and `require()`. `Token.kind` is already `String(16)`. No migration. `models.py` was not edited.
- `read_draft_snapshot` returns the current draft of an entry in the token's project, including Hebrew with niqqud. `test_draft_token_reads_same_project_draft_including_hebrew_niqqud` covers that, and the delivery GraphQL response for the same entry stays on the published public fields.
- An expired token, another project, a missing entry, a session cookie, a delivery token, and `skip_auth` without a drafts token are rejected. Covered by `test_draft_token_fails_closed_for_expiry_other_projects_and_other_kinds` and `test_skip_auth_does_not_turn_into_a_drafts_token`.
- A drafts token cannot authorize a write: `require` with `write=True`, a forged higher role, `save_entry`, issuing another drafts token, `/graphql`, `/delivery/graphql`, and `/api/preview/redeem`. Covered by `test_draft_token_never_authorizes_writes`.
- `audit()` redacts raw-token-shaped strings and password-like detail keys before they are stored. A 64-character lowercase hex digest, including `tokenId`, is kept. Covered by `test_audit_omits_raw_tokens_and_passwords_from_details_and_logs`. Issue and revoke audits in the other tests also keep the raw token out of `Audit.details`.
- Preview grants, delivery REST, GraphQL, MCP, and content save were not edited. The product diff against `b6c6687` is `api/app/draft_tokens.py`, `api/app/security.py`, and `api/tests/test_draft_tokens.py`.

## Left undone

`scripts/verify.sh` does not exit 0 on this tree or on main, because the dependabot manifest test fails. `.github/dependabot.yml` and `starters/nextjs/` were left unchanged.
