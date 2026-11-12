# MOSS-002 dependency advisories

local

Recorded 29 October 2026 (UTC). `pip-audit` used its default PyPI advisory service. No `--ignore-vuln`, allowlist, or audit exception was added. No package was downgraded.

## Code under test

| | |
| --- | --- |
| SHA tested | `c95824b2e5d60179c4e9ca963d71606cf8247e4c` |
| Branch | `cursor/moss-002-dependency-advisories-2c70` |
| Parent | `8912ec19764ec51b3015d597467e0e59e3569ca3` (main, after MOSS-025) |
| Baseline | `b306d3f0e609347735880be2a3d487b1ac1500a2` (main, MOSS-001 Pillow 13) |
| `git status --porcelain` at the start of this run | empty (clean) |
| Date | 2026-10-29T04:11:50Z through 2026-10-29T04:14:40Z |
| Python / uv / pip-audit | 3.12.3 / 0.12.23 / 2.10.1 |
| PostgreSQL | 16.15 on 127.0.0.1:5432, role `pg` |
| Docker Compose | 2.40.3 (compose config tests ran) |

`api/pyproject.toml` is unchanged. The fixed releases fit the existing caps: `authlib>=1.6,<2`, `opentelemetry-api>=1.44,<2`, and `opentelemetry-sdk>=1.44,<2`. certifi is transitive and has no direct pin.

## Bumps

Compared with `api/uv.lock` at `8912ec1` (same versions as `b306d3f`). Nothing else in the lock changed.

| Package | Before | After |
| --- | --- | --- |
| authlib | 1.8.0 | 1.9.1 |
| certifi | 2026.7.22 | 2026.10.23 |
| opentelemetry-api | 1.45.0 | 1.45.1 |
| opentelemetry-sdk | 1.45.0 | 1.45.1 |
| opentelemetry-semantic-conventions | 0.66b0 | 0.66b1 |

`opentelemetry-sdk` 1.45.0 requires `opentelemetry-api==1.45.0`, and 1.45.1 requires `opentelemetry-api==1.45.1` plus `opentelemetry-semantic-conventions==0.66b1`. Those two moved with the API. The OTLP HTTP exporter stayed at 1.45.0 because `opentelemetry-sdk~=1.45.0` accepts 1.45.1. Application code did not need a change.

## pip-audit

```sh
cd api
uv export --frozen --all-groups --no-emit-project -o /tmp/moss-002-requirements.txt
uv run --with pip-audit pip-audit --progress-spinner off -r /tmp/moss-002-requirements.txt
```

`uv export` exit 0. `pip-audit` printed `No known vulnerabilities found` and exited 0. Full record: [c95824b/pip-audit.txt](c95824b/pip-audit.txt).

## Tests

Same API commands as the README. No tests were added, skipped, or deleted. Counts match the 402 tests collected on `b306d3f`.

| Command | Exit | Result |
| --- | --- | --- |
| `cd api && MOSS_USE_SQLITE=false uv run pytest -rs` | 0 | 402 collected, 398 passed, 4 skipped, 6 warnings in 55.56s |
| `cd api && MOSS_USE_SQLITE=false MOSS_TEST_DATABASE_URL='postgresql+psycopg://pg:pgtestpw@127.0.0.1:5432/postgres' uv run pytest -rs` | 0 | 402 collected, 402 passed, 0 skipped, 6 warnings in 95.56s |

The four SQLite skips are the existing PostgreSQL-only rehearsals, and the same four passed in the PostgreSQL run:

- `tests/test_concurrency.py:13` PostgreSQL row-lock rehearsal
- `tests/test_indexing.py:503` PostgreSQL generic prepared plans
- `tests/test_postgres_product_migration.py:11` PostgreSQL forward-upgrade rehearsal
- `tests/test_search.py:109` PostgreSQL trigram search

Logs: [pytest-sqlite.txt](c95824b/pytest-sqlite.txt), [pytest-postgres.txt](c95824b/pytest-postgres.txt).
