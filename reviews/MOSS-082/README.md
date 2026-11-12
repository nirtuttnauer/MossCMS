# MOSS-082 local verification

label: local

| | |
| --- | --- |
| Base | `b6c66870b98af990ee91766e5a965e823bf2b03d` (`origin/main`) |
| Code tested | `c641c10b02dbdd316bb61b10c50ac0e142fef041` |
| Clean status | `reviews/MOSS-082/c641c10/summary.txt` records an empty `git status --porcelain` when `scripts/verify.sh MOSS-082` started |
| Started | 2026-11-12T14:48:23Z |
| `scripts/verify.sh MOSS-082` | exit 1 at `pytest-sqlite` |

The evidence files were committed after that run, so the pull request head is the evidence commit. The counts below are for `c641c10`. Product files at that commit are `api/app/query_limits.py` and `api/tests/test_query_limits.py`.

`scripts/verify.sh MOSS-082` stopped at SQLite pytest. The failing test is also failing on the base. The prompt leaves `.github/dependabot.yml` untouched, so that failure was left as it is. The later commands from the same script were run on this commit and logged beside the script output. Exit codes are in `reviews/MOSS-082/c641c10/exit-codes.txt`.

## Counts

| Suite | Base `b6c6687` | Code `c641c10` |
| --- | --- | --- |
| API pytest, SQLite, `-m "not postgres"` | 1 failed, 497 passed, 4 deselected, 0 skipped | 1 failed, 504 passed, 4 deselected, 0 skipped |
| API pytest, PostgreSQL | 1 failed, 501 passed, 0 skipped | 1 failed, 508 passed, 0 skipped |
| Admin web vitest | unchanged tree | 36 files, 356 passed, 0 skipped |
| Example site `node --test` | unchanged tree | 50 pass, 0 fail, 0 skipped |
| Production Playwright | unchanged tree | 2 passed, 0 skipped |

The API difference is seven new tests in `api/tests/test_query_limits.py`. `web/`, `example-site/`, and `ci/` match the base.

Base commands (2026-11-12, label local), from a checkout of `b6c6687`:

- `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest -m "not postgres"` in `api/` — exit 1, log `reviews/MOSS-082/b6c6687/pytest-sqlite.txt` (written 2026-11-12T14:48:20Z)
- `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=postgres` and `MOSS_TEST_DATABASE_URL` set to the PostgreSQL URL from `scripts/verify.sh`, then `uv run pytest` in `api/` — exit 1, log `reviews/MOSS-082/b6c6687/pytest-postgres.txt`

Both base runs fail `tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests`. The assertion text on the base and on `c641c10` is `starters/nextjs/package.json (npm /starters/nextjs) is not covered by .github/dependabot.yml`.

The four ids deselected on SQLite are the same on both trees:

- `tests/test_concurrency.py::test_postgres_workers_skip_locked_rows_and_claim_once`
- `tests/test_indexing.py::test_common_string_count_avoids_per_match_probes_in_generic_postgres_plan`
- `tests/test_postgres_product_migration.py::test_postgres_0009_preserves_localized_live_scheduled_and_revision_data`
- `tests/test_search.py::test_generic_postgres_substring_plan_uses_trigrams_and_rechecks_matches`

They are deselected by `-m "not postgres"`. The pytest summaries do not report a runtime skip or an xfail.

## Head commands

`scripts/verify.sh MOSS-082` from a clean tree at `c641c10` (exit 1 at `pytest-sqlite`). Steps that finished inside that process, all exit 0: `uv sync --locked --group dev`, ruff, ruff on scripts, mypy. SQLite pytest then exited 1 with the Dependabot failure above: 1 failed, 504 passed, 4 deselected.

Remaining script commands, logged with `label: local` on the same commit:

| Command | Exit |
| --- | --- |
| PostgreSQL pytest | 1, same Dependabot test; 508 passed, 0 skipped |
| `tests/verify_required_runs.py` | 1, because that test failed in the saved runs |
| OpenTelemetry smoke | 0 |
| web `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 |
| example-site `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 |
| `pip-audit` during the continuation | 1, `python3.12-venv` was missing, so the tool stopped before reading advisories |
| `pip-audit` retry after that package was installed | 0, `No known vulnerabilities found` (`pip-audit-retry.txt`). `api/uv.lock` matches the base |
| `npm audit` in `web/`, `example-site/`, and `ci/` | 0 |
| `gitleaks` during the continuation | 127, the binary was not on that shell's `PATH` |
| `gitleaks` retry on `git archive HEAD` | 0, no leaks found (`gitleaks-retry.txt`) |
| `npm ci` and Playwright Chromium install in `ci/` | 0 |
| `docker build --tag mosscms:smoke .` | 0 |
| compose up, `npm test` in `ci/`, compose down | 0, 2 passed |

No ignore, allowlist, or override was added.

## Query limits

`bounded_query` still caps depth at 12 and expanded selections at 200. A string longer than 30,000 characters raises `Query length limit exceeded.` with code `QUERY_LIMIT` and is not parsed. A Hebrew document of 30,000 characters that selects one field still parses. Nested fragment copies are counted, and a wide fragment tree over the selection cap is rejected. A short Hebrew query is accepted. `api/app/graphql.py` was not edited.
