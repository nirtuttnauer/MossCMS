# MOSS-094 local evidence

Label: `local`

| | |
| --- | --- |
| Base SHA | `5ea1d037bb85e47c2efc1d97f72998d130130878` (`main`) |
| Verified SHA | `16c7a250c25d763a2e176c39a09aaa7efd3ce782` |
| Date | 2026-11-12 (UTC) |
| Clean status | `git status --porcelain` was empty when `scripts/verify.sh MOSS-094` started ([summary.txt](16c7a25/summary.txt)) |

`api/app/development.py` is unchanged. `api/app/security.py` and `api/app/accounts.py` are unchanged. The new tests leave `skip_auth` false.

## What was run

`scripts/verify.sh MOSS-094` at 2026-11-12T15:53:09Z. Exit 1. It stopped at `pytest-sqlite`.

That SQLite log failed two tests: `test_dependabot_config_matches_schema_and_covers_manifests`, and `test_variant_a_proxy_and_variant_b_private_listener` (`curl: (28)` to `127.0.0.1:18059` with 0 bytes). The same two failures were reproduced on base `5ea1d03` before any host firewall change ([before-iptables-fix](base-5ea1d03/before-iptables-fix/)).

The proxy timeout and a later `production-up` failure (the app stayed unhealthy while its Postgres SYN was retransmitted) came from this machine: `iptables-legacy` had `FORWARD` policy `DROP`, while Docker 29 installed the matching rules in the nft backend. Bridge traffic between containers was dropped. Host command, not a repo edit:

```
sudo iptables-legacy -P FORWARD ACCEPT
```

The steps `scripts/verify.sh` had not reached were then run with the same commands, labeled `local`, into `reviews/MOSS-094/16c7a25/`. After the firewall change, SQLite, PostgreSQL, pip-audit, and the production Compose steps were run again. Logs from the earlier pass are in [before-iptables-fix](16c7a25/before-iptables-fix/).

## Counts

Compared with base `5ea1d03` after the same firewall change. Both API runs still fail the Dependabot coverage test. Passed counts are two higher on the verified SHA. Those two tests are `tests/test_development_bypass.py`.

| Run | main `5ea1d03` | `16c7a25` |
| --- | --- | --- |
| SQLite passed | 497 | 499 |
| SQLite failed | 1 | 1 |
| SQLite deselected | 4 | 4 |
| PostgreSQL passed | 501 | 503 |
| PostgreSQL failed | 1 | 1 |
| Web (Vitest) | 356 | 356 |
| Example site (node:test) | not run on the base worktree | 50 passed |
| Production (Playwright) | not run on the base worktree | 2 passed |

SQLite deselects the same four PostgreSQL-only tests on both SHAs:

- `tests/test_concurrency.py::test_postgres_workers_skip_locked_rows_and_claim_once`
- `tests/test_indexing.py::test_common_string_count_avoids_per_match_probes_in_generic_postgres_plan`
- `tests/test_postgres_product_migration.py::test_postgres_0009_preserves_localized_live_scheduled_and_revision_data`
- `tests/test_search.py::test_generic_postgres_substring_plan_uses_trigrams_and_rechecks_matches`

Those four pass in the PostgreSQL run (501 vs 497 on main, 503 vs 499 on `16c7a25`). No runtime skip.

The remaining API failure on both SHAs is `tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests`: `starters/nextjs/package.json (npm /starters/nextjs) is not covered by .github/dependabot.yml`. That test is owned by open MOSS-063 #49. `.github/dependabot.yml` was not edited. `tests/verify_required_runs.py` exits 1 because that test did not pass.

Web sources match `main`. The base worktree reported 36 files and 356 tests passed (`npm test`, exit 0), and `npm run check` and `npm run build` exited 0. The verified tree's `npm run check && npm test && npm run build && npm audit --audit-level=high` exited 0 with the same 356 tests.

## Exit codes at `16c7a25` (label local)

| Step | Exit |
| --- | --- |
| `scripts/verify.sh MOSS-094` | 1 (stopped at pytest-sqlite) |
| uv-sync, ruff, ruff-scripts, mypy | 0 |
| pytest-sqlite, before the firewall change | 1 (Dependabot and the proxy timeout) |
| pytest-postgres, otel, web, example-site, gitleaks, npm audits, image build | see [exit-codes.txt](16c7a25/exit-codes.txt) |
| pip-audit, before `python3.12-venv` was installed | 1 (`ensurepip` missing) |
| production-up / production-test, before the firewall change | 1 / 1 |
| pytest-sqlite, rerun | 1 (Dependabot test) |
| pytest-postgres, rerun | 1 (Dependabot test) |
| verify-required-runs, rerun | 1 (Dependabot test) |
| pip-audit, rerun | 0 (`No known vulnerabilities found`) |
| production-up, production-test, production-down, rerun | 0, 0, 0 |

Base commands and exits: [commands.txt](base-5ea1d03/commands.txt).

## Red checks that were reverted

Two temporary edits of `api/app/development.py` were applied on the verified tree and then restored with `git checkout -- api/app/development.py` before the commit. Neither edit is in `16c7a25`.

- Calling `password_hash("development-bypass-disabled-for-password-login")` for the planted user made `test_check_password_rejects_the_stored_development_hash` fail (exit 1). The stored value was an `scrypt$...` string rather than `development-bypass-disabled-for-password-login`.
- Assigning the planted name, email, and hash onto an existing row made `test_second_initialize_development_leaves_existing_user_unchanged` fail (exit 1).

`git diff main -- api/app/development.py` is empty.
