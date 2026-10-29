# MOSS-023 required-run markers

local

Recorded 29 October 2026 (UTC). A runtime skip or xfail fails the run. There is no allowed-skip list. PostgreSQL-only tests use the `postgres` marker and are excluded from the SQLite required run with `-m "not postgres"` before they execute. Compose tests use the `compose` marker and ran in both required runs. Deselected ids are committed in `api/tests/required_runs.json` and checked against each run.

## Code under test

| | |
| --- | --- |
| SHA tested | `1b55a1be7a91d79c6c1d73a28979c2c1ced40f43` |
| Rebased code commit | `3f94ac3b232af62a7831181d1a17b622deddc758` on `fd1f0b0c953f1bf77bdca4903c660af72f33342e` |
| Branch | `cursor/moss-023-skip-policy-5f0c` |
| Parent at test time | `24431f82d35824e18a184c6e6d9f9c8342a76a62` (main, after MOSS-002) |
| Baseline | `3a87c73c8e925973608e373863813163b41f04a9` |
| `git status --porcelain` at the start of this run | empty (clean) |
| Date | 2026-10-29T04:17:30Z through 2026-10-29T04:21:04Z |
| Python / uv | 3.12.3 / 0.12.23 |
| PostgreSQL | 16.15, role `ubuntu`, local socket |
| Docker Compose | 2.40.3 (compose tests ran) |
| Node / npm | v22.23.4 / 10.9.9 |

Markers are registered in `api/tests/conftest.py`. `api/pyproject.toml`, `api/uv.lock`, and `.github/workflows` are unchanged by this ticket.

`3f94ac3` is this change replayed onto `fd1f0b0`. `git diff 1b55a1b 3f94ac3` is only `docs/rest-delivery-design.md` and `reviews/MOSS-030` from main. API, web, example-site, and tests are the same bytes, so the results below still apply.

## API required runs

```sh
cd api
MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest -m "not postgres" -q --tb=line
MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=postgres \
  MOSS_TEST_DATABASE_URL='postgresql+psycopg://ubuntu@/ubuntu' \
  uv run pytest -q --tb=line
uv run python tests/verify_required_runs.py
```

| Command | Exit | Result |
| --- | --- | --- |
| SQLite required run | 0 | 403 collected, **399 passed, 4 deselected, 0 skipped**, 6 warnings in 62.38s |
| PostgreSQL required run | 0 | 403 collected, **403 passed, 0 deselected, 0 skipped**, 6 warnings in 99.83s |
| `tests/verify_required_runs.py` | 0 | union of passed ids is 403, equal to the collected list |

Baseline on this suite before the marker change, measured on main at `b306d3f` (test files identical to `3a87c73`): 402 collected, SQLite 398 passed and 4 skipped. MOSS-002 on `c95824b` recorded the same 402 / 398 / 4. This run collects 403 because it adds `tests/test_required_runs.py`. 403 >= 402.

The four ids deselected on SQLite and passed on PostgreSQL:

- `tests/test_concurrency.py::test_postgres_workers_skip_locked_rows_and_claim_once`
- `tests/test_indexing.py::test_common_string_count_avoids_per_match_probes_in_generic_postgres_plan`
- `tests/test_postgres_product_migration.py::test_postgres_0009_preserves_localized_live_scheduled_and_revision_data`
- `tests/test_search.py::test_generic_postgres_substring_plan_uses_trigrams_and_rechecks_matches`

Logs: [pytest-sqlite.txt](1b55a1b/pytest-sqlite.txt), [pytest-postgres.txt](1b55a1b/pytest-postgres.txt), [verify.txt](1b55a1b/verify.txt).

## Other local checks on this tree

| Command | Exit | Result |
| --- | --- | --- |
| `uv run ruff check` and `ruff format --check` for `app`, `tests`, `migrations` | 0 | clean |
| `uv run mypy app` | 0 | 27 source files |
| `cd web && npm ci && npm run check && npm test && npm run build && npm audit --audit-level=high` | 0 | 35 files, 317 tests passed, build succeeded, 0 vulnerabilities |
| `cd example-site && npm test && npm run check && npm audit --audit-level=high` | 0 | 46 passed, 0 failed, 0 skipped, 0 vulnerabilities |

## Workflow

MOSS-003 is on main (`8f4c76e` and later). The SQLite job in `.github/workflows/checks.yml` runs `uv run pytest -m "not postgres"` with `MOSS_REQUIRED_RUN=sqlite`. The PostgreSQL job keeps `uv run pytest` and sets `MOSS_REQUIRED_RUN=postgres`. Action SHA pins, permissions, and job and step names are unchanged. The two jobs do not share result files, so `tests/verify_required_runs.py` stays the local union check. Each CI job still checks its own committed deselection list, and `tests/test_required_runs.py` checks that the two marker expressions cover every collected id.

## Rerun after the workflow edit

local

2026-10-29T04:24:55Z through 2026-10-29T04:28:07Z, on the same API tree as `3f94ac3` plus the workflow edit. `actionlint` 1.7.7 on `checks.yml` and `docker.yml` exited 0.

| Command | Exit | Result |
| --- | --- | --- |
| ruff check/format (api, scripts, example-site setup, telemetry smoke) and `mypy app` | 0 | clean; 27 source files |
| SQLite required run | 0 | 399 passed, 4 deselected, 0 skipped, 61.11s |
| PostgreSQL required run | 0 | 403 passed, 0 deselected, 0 skipped, 89.03s |
| `tests/verify_required_runs.py` | 0 | union 403 |
| web check, test, build, `npm audit --audit-level=high` | 0 | 317 passed, 0 vulnerabilities |
| example-site test, check, `npm audit --audit-level=high` | 0 | 46 passed, 0 failed, 0 skipped, 0 vulnerabilities |

Logs: [pytest-sqlite.txt](workflow-rerun/pytest-sqlite.txt), [pytest-postgres.txt](workflow-rerun/pytest-postgres.txt), [verify.txt](workflow-rerun/verify.txt).

## Review after merge

Nir authorized merging without a separate written QA and CTO sign-off. QA and the CTO should review this rule after the fact.
