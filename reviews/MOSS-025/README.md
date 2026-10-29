# MOSS-025 npm audit

local

Recorded 29 October 2026 (UTC). Dev dependencies are included. `npm audit` is the default audit (no `--omit=dev`, no `--audit-level`). No `overrides`, allowlists, or audit exceptions were added.

## Code under test

| | |
| --- | --- |
| SHA | `ffbdc3685d684c676af9846d20b25954902b8fab` |
| Branch | `cursor/moss-025-npm-audit-d37d` |
| Parent | `b306d3f0e609347735880be2a3d487b1ac1500a2` (main, MOSS-001 Pillow 13) |
| Baseline | `3a87c73c8e925973608e373863813163b41f04a9` |
| `git status --porcelain` at the start of this run | empty (clean) |
| Date | 2026-10-29T04:03:56Z through 2026-10-29T04:06Z |
| Node / npm | v22.23.4 / 10.9.9 |
| Python / uv | 3.12.3 / 0.12.23 |
| PostgreSQL | 16.15 on 127.0.0.1:5432, role `pg` |

`ffbdc36` is the vitest lockfile fix rebased onto `b306d3f`. This directory is the run record for that SHA. The evidence commit that adds this directory does not change lockfiles or tests.

## Baseline audit at `3a87c73`

Working tree clean, before the vitest bump. Command in each package directory: `npm audit` (human) and `npm audit --json`.

| Lockfile | Findings | Exit |
| --- | --- | --- |
| `web/package-lock.json` | 2 moderate (`vitest` 4.1.11 and `@vitest/mocker` 4.1.11): [GHSA-qxg6-89mg-rqv8](https://github.com/advisories/GHSA-qxg6-89mg-rqv8), [GHSA-xp26-3454-mjgp](https://github.com/advisories/GHSA-xp26-3454-mjgp). Fix available inside 4.x (`>=4.1.12`). | 1 |
| `example-site/package-lock.json` | 0 | 0 |
| `ci/package-lock.json` | 0 | 0 |

Full output: [baseline-3a87c73/web.txt](baseline-3a87c73/web.txt), [web.json](baseline-3a87c73/web.json), [example-site.txt](baseline-3a87c73/example-site.txt), [example-site.json](baseline-3a87c73/example-site.json), [ci.txt](baseline-3a87c73/ci.txt), [ci.json](baseline-3a87c73/ci.json).

## Fix

`web` devDependency `vitest` moved from `^4.0.0` to `^4.1.12`. The lockfile pins `vitest` and the installed `@vitest/*` packages (including `@vitest/mocker`) at 4.1.12. That is the patched release inside the existing major. `example-site` and `ci` needed no change. `npm ci` in `web` with npm 10.9.9 installs 4.1.12.

## Audit after the fix at `ffbdc36`

```sh
cd web && npm audit; echo $?
cd example-site && npm audit; echo $?
cd ci && npm audit; echo $?
npm audit --json   # same directories, saved beside the text
```

| Lockfile | Findings | Exit |
| --- | --- | --- |
| web | 0 (info 0, low 0, moderate 0, high 0, critical 0) | 0 |
| example-site | 0 | 0 |
| ci | 0 | 0 |

Full output: [ffbdc36/web.txt](ffbdc36/web.txt), [web.json](ffbdc36/web.json), [example-site.txt](ffbdc36/example-site.txt), [example-site.json](ffbdc36/example-site.json), [ci.txt](ffbdc36/ci.txt), [ci.json](ffbdc36/ci.json).

## Tests at `ffbdc36`

Same commands as the README, with no `-k`, `--ignore`, skips, or xfails added. Counts match the run of this same suite on `3a87c73` (test files are unchanged from that SHA through `b306d3f`).

| Command | Exit | Result |
| --- | --- | --- |
| `cd api && uv sync --locked --group dev` | 0 | Pillow 13.0.0 from the rebased lock |
| `cd api && uv run ruff check app tests migrations` | 0 | all checks passed |
| `cd api && uv run ruff format --check app tests migrations` | 0 | 79 files already formatted |
| `cd api && uv run mypy app` | 0 | no issues in 27 files |
| `cd api && MOSS_USE_SQLITE=false uv run pytest -ra --tb=line` | 0 | 398 passed, 4 skipped, 6 warnings in 67.38s |
| `cd api && MOSS_USE_SQLITE=false MOSS_TEST_DATABASE_URL='postgresql+psycopg://pg:pgtestpw@127.0.0.1:5432/postgres' uv run pytest -ra --tb=line` | 0 | 402 passed, 6 warnings in 107.78s |
| `cd web && npm run check` | 0 | `tsc -b` |
| `cd web && npm test` | 0 | 35 files, 317 tests passed (vitest 4.1.12) |
| `cd web && npm run build` | 0 | vite build succeeded |
| `cd example-site && npm run check` | 0 | `tsc --noEmit` |
| `cd example-site && npm test` | 0 | 46 passed, 0 failed, 0 skipped |
| `cd example-site && npm run build` | 0 | vite build succeeded |

SQLite skipped four tests that already skip on main and pass on PostgreSQL: `test_postgres_workers_skip_locked_rows_and_claim_once`, `test_common_string_count_avoids_per_match_probes_in_generic_postgres_plan`, `test_postgres_0009_preserves_localized_live_scheduled_and_revision_data`, and `test_generic_postgres_substring_plan_uses_trigrams_and_rechecks_matches`. The PostgreSQL run executed the whole suite: 402 passed, 0 skipped. No xfail.

Logs: [pytest-sqlite.txt](ffbdc36/pytest-sqlite.txt), [pytest-postgres.txt](ffbdc36/pytest-postgres.txt), [web-check.txt](ffbdc36/web-check.txt), [web-test.txt](ffbdc36/web-test.txt), [web-build.txt](ffbdc36/web-build.txt), [example-site-check.txt](ffbdc36/example-site-check.txt), [example-site-test.txt](ffbdc36/example-site-test.txt), [example-site-build.txt](ffbdc36/example-site-build.txt).
