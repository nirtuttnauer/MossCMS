# MOSS-092 origin schemes

local

Recorded 12 November 2026 (UTC). GitHub Actions was not used.

## Code under test

| | |
| --- | --- |
| Base | `5ea1d037bb85e47c2efc1d97f72998d130130878` (`main`) |
| SHA tested | `32156f3e515bfd7ce1b82bb57950af5fb3a0a684` |
| `git status --porcelain` before `scripts/verify.sh MOSS-092` | empty |
| Verify start | 2026-11-12T15:51:12Z |
| Record finished | 2026-11-12T16:08:30Z |

`32156f3` rejects `file:`, `data:`, and `javascript:` origins, other non-http schemes, scheme-less values, and host-less values in `Settings.validate`. This later commit adds the run record. It does not change `api/app/config.py` or the tests.

`///` still normalizes to an empty entry. `test_slash_only_origin_keeps_existing_validation_behavior` in `api/tests/test_config.py` locks that result, and that file was not edited.

## What was run

`scripts/verify.sh MOSS-092` exited 1 at `pytest-sqlite`. The failure is `tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests`:

```
starters/nextjs/package.json (npm /starters/nextjs) is not covered by .github/dependabot.yml
```

The same assertion fails on `5ea1d03`. `.github/dependabot.yml` was not edited. The script stops at that step, so the later steps were run with the same commands and written into [32156f3](32156f3/).

Two environment retries are in `exit-codes.txt`: `pip-audit` exited 1 until `python3.12-venv` was installed (the same gap recorded for MOSS-026), then exited 0. `gitleaks` exited 127 when it was not on `PATH`, then exited 0 with the binary `scripts/verify.sh` had already cached.

No runtime skip or xfail. The skip scanner exited 0 for the SQLite, PostgreSQL, web, and example-site logs.

## Counts

Label: `local`.

| Run | `5ea1d03` | `32156f3` |
| --- | --- | --- |
| SQLite `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest -m "not postgres"` | 1 failed, 497 passed, 4 deselected, 0 skipped | 1 failed, 530 passed, 4 deselected, 0 skipped |
| PostgreSQL `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=postgres uv run pytest` | 1 failed, 501 passed, 0 skipped | 1 failed, 534 passed, 0 skipped |
| web `npm run check && npm test && npm run build && npm audit --audit-level=high` | same tree as the head | 36 files passed, 356 tests passed, 0 skipped |
| example-site | same tree as the head | 50 passed, 0 failed, 0 skipped |
| production `npm test` in `ci/` | same tree as the head | 2 passed, 0 skipped |

The SQLite deselection is the same four PostgreSQL-only ids on both SHAs:

- `tests/test_concurrency.py::test_postgres_workers_skip_locked_rows_and_claim_once`
- `tests/test_indexing.py::test_common_string_count_avoids_per_match_probes_in_generic_postgres_plan`
- `tests/test_postgres_product_migration.py::test_postgres_0009_preserves_localized_live_scheduled_and_revision_data`
- `tests/test_search.py::test_generic_postgres_substring_plan_uses_trigrams_and_rechecks_matches`

Collected API tests: 502 on `5ea1d03`, 535 on `32156f3`. The difference is the 33 tests in `api/tests/test_origin_schemes.py`. Those 33 passed on SQLite and on PostgreSQL. The single failure on both SHAs and both database runs is the dependabot manifest check. `web/`, `example-site/`, and `ci/` match `5ea1d03`, so those counts describe both trees.

`uv run python tests/verify_required_runs.py` exited 1 because that same dependabot id is the collected test that did not pass. No other id is missing.

## Exit codes

| Step | Exit |
| --- | --- |
| `uv sync --locked --group dev` | 0 |
| ruff check and format | 0 |
| ruff on scripts, example-site setup, telemetry smoke | 0 |
| `mypy app` | 0 |
| SQLite pytest | 1 (dependabot) |
| PostgreSQL container | 0 |
| PostgreSQL pytest | 1 (dependabot) |
| `verify_required_runs.py` | 1 (dependabot) |
| web `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 |
| example-site `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 |
| `pip-audit` | 0 |
| `npm audit` for web, example-site, and ci | 0 |
| gitleaks | 0 |
| OpenTelemetry smoke | 0 |
| `docker build --tag mosscms:smoke .` | 0 |
| production Compose up, Playwright, down | 0 |

Before the config change, `uv run pytest tests/test_origin_schemes.py` reported 25 failed and 8 passed. Each failure was `Failed: DID NOT RAISE RuntimeError`. After the change, `tests/test_origin_schemes.py` and `tests/test_config.py` together reported 63 passed.
