# MOSS-057 changelog

local

Recorded 29 October 2026 (UTC). `CHANGELOG.md` is a Keep a Changelog file with one Unreleased section. Each entry links its pull request and cites the user-visible commits in `git log 3a87c73..HEAD`. `scripts/check_changelog.py` checks that list. Ticket ids stay in the commit message.

## Code under test

| | |
| --- | --- |
| Suite SHA | `27ccf24ebf5dab51a8cc40ac675374fdbd5a20d2` |
| Rebased changelog SHA | `bcf8ff5d17a4bc6da4b42a00ac952200209757f8` |
| Parent at suite time | `9a4c81c68416f08b369a601b1ed3b20313ccc9b1` |
| Parent after rebase | `28c3dc9` (`Merge pull request #22`) |
| Baseline in the ticket | `d50e2788485e4ef0c65598c4c2f2bd7536e1ed96` (403 collected) |
| `git status --porcelain` at the start of the suite | empty (clean) |
| Date | 2026-10-29T05:24:30Z through 2026-10-29T05:29:18Z |
| Python / uv | 3.12.3 / 0.12.23 |
| Node / npm | v22.23.4 / 10.9.9 |
| PostgreSQL | 17.11, `postgres:17-alpine`, `127.0.0.1:5432`, role `pg`, database `postgres` |
| Docker / Compose | 29.1.3 / 2.40.3 |
| pip-audit / gitleaks | 2.10.1 / 8.30.1 |

`git diff 27ccf24 bcf8ff5 -- . ':(exclude)reviews/MOSS-026'` is empty. The rebase only added review notes that were already on main. Application code, tests, lockfiles, workflows, `CHANGELOG.md`, and `scripts/check_changelog.py` are the same bytes the suite ran.

## Changelog check

```sh
python3 scripts/check_changelog.py
```

| Command | Exit | Result |
| --- | --- | --- |
| `python3 scripts/check_changelog.py` at `27ccf24` | 0 | `changelog ok: 10 entries, 13 user-visible commits` |
| same command at `bcf8ff5` | 0 | `changelog ok: 10 entries, 13 user-visible commits, head bcf8ff5d17a4bc6da4b42a00ac952200209757f8` |

Log: [changelog.txt](27ccf24/changelog.txt).

## Private names, employer domain, and gitleaks

Raw `rg` exits 1 when it finds nothing. The check below exits 0 only in that case. The search was `CHANGELOG.md` and `scripts/check_changelog.py`.

```sh
rg -n -i \
  -e '\bNir\b' \
  -e '\bTuttnauer\b' \
  -e 'chefi\.biz' \
  -e '\bAftur\b' \
  -e 'ProjectMemory' \
  -e 'gmail\.com' \
  CHANGELOG.md scripts/check_changelog.py
test $? -eq 1
```

```sh
gitleaks detect --no-banner --redact \
  --log-opts="bcf8ff5d17a4bc6da4b42a00ac952200209757f8^..bcf8ff5d17a4bc6da4b42a00ac952200209757f8" \
  --source .
```

| Command | Exit | Result |
| --- | --- | --- |
| `rg` on the changelog and the check script | 1 | 0 matches |
| wrapper `test $? -eq 1` | 0 | 0 matches |
| `gitleaks` on the changelog commit | 0 | no leaks found |

Logs: [rg.txt](27ccf24/rg.txt), [rg-final.txt](27ccf24/rg-final.txt), [gitleaks.txt](27ccf24/gitleaks.txt), [gitleaks-final.txt](27ccf24/gitleaks-final.txt).

## API required runs

No `-k`, `--ignore`, new skips, or xfails. A runtime skip fails the run. There is no allowed-skip list. PostgreSQL-only tests use the `postgres` marker and are excluded from the SQLite run with `-m "not postgres"` before they execute. Compose tests ran in both required runs.

```sh
cd api
uv run ruff check app tests migrations
uv run ruff format --check app tests migrations
uv run ruff check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py
uv run ruff format --check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py
uv run ruff check --config pyproject.toml ../ci/telemetry_smoke.py
uv run ruff format --check --config pyproject.toml ../ci/telemetry_smoke.py
uv run mypy app
MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest -m "not postgres" -ra --tb=line
MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=postgres \
  MOSS_TEST_DATABASE_URL='postgresql+psycopg://pg:pgtestpw@127.0.0.1:5432/postgres' \
  uv run pytest -ra --tb=line
uv run python tests/verify_required_runs.py
```

| Command | Exit | Result |
| --- | --- | --- |
| `ruff check app tests migrations` | 0 | all checks passed |
| `ruff format --check app tests migrations` | 0 | 85 files already formatted |
| ruff check/format of scripts, example-site setup, telemetry smoke | 0 | all checks passed |
| `mypy app` | 0 | no issues in 28 source files |
| SQLite required run | 0 | collected 433, **429 passed, 4 deselected, 0 skipped**, 6 warnings in 61.40s |
| PostgreSQL required run | 0 | collected 433, **433 passed, 0 deselected, 0 skipped**, 6 warnings in 123.62s |
| `tests/verify_required_runs.py` | 0 | `"ok": true` |

433 collected is above the 403 collected at `d50e278`. The four deselected ids are the committed PostgreSQL-only tests, and the PostgreSQL run passed them:

- `tests/test_concurrency.py::test_postgres_workers_skip_locked_rows_and_claim_once`
- `tests/test_indexing.py::test_common_string_count_avoids_per_match_probes_in_generic_postgres_plan`
- `tests/test_postgres_product_migration.py::test_postgres_0009_preserves_localized_live_scheduled_and_revision_data`
- `tests/test_search.py::test_generic_postgres_substring_plan_uses_trigrams_and_rechecks_matches`

Logs: [pytest-sqlite.txt](27ccf24/pytest-sqlite.txt), [pytest-postgres.txt](27ccf24/pytest-postgres.txt), [verify.txt](27ccf24/verify.txt), [ruff-check.txt](27ccf24/ruff-check.txt), [ruff-format.txt](27ccf24/ruff-format.txt), [mypy.txt](27ccf24/mypy.txt).

## OTLP smoke, pip-audit, web, example site, production image

```sh
cd api
uv export --frozen --all-groups --no-emit-project -o /tmp/moss-057-requirements.txt
uv run --with pip-audit pip-audit --progress-spinner off -r /tmp/moss-057-requirements.txt
cd web && npm ci && npm run check && npm test && npm run build && npm audit --audit-level=high && npm audit
cd example-site && npm ci && npm run check && npm test && npm run build && npm audit --audit-level=high && npm audit
cd ci && npm ci && npm audit
docker build --tag mosscms:smoke .
docker compose -f ci/compose.yaml -p mosscms-smoke up --no-build -d --wait --wait-timeout 180
cd ci && npm test
```

| Command | Exit | Result |
| --- | --- | --- |
| Collector smoke | 0 | metrics ready |
| `pip-audit` 2.10.1 | 0 | No known vulnerabilities found |
| web check, test, build, `npm audit` | 0 | 35 files, 317 tests passed; 0 vulnerabilities |
| example-site check, test, build, `npm audit` | 0 | 46 passed, 0 failed, 0 skipped; 0 vulnerabilities |
| `npm audit` ci | 0 | 0 vulnerabilities |
| `docker build --tag mosscms:smoke .` | 0 | image built |
| `compose up --wait` | 0 | app healthy |
| `npm test` in `ci` | 0 | 2 passed |

Logs: [otel.txt](27ccf24/otel.txt), [pip-audit.txt](27ccf24/pip-audit.txt), [web.txt](27ccf24/web.txt), [example.txt](27ccf24/example.txt), [ci-audit.txt](27ccf24/ci-audit.txt), [docker-build.txt](27ccf24/docker-build.txt), [compose-up.txt](27ccf24/compose-up.txt), [playwright-test.txt](27ccf24/playwright-test.txt), [summary.txt](27ccf24/summary.txt).
