# MOSS-058 Hebrew (Unicode) slugs

local

Recorded 29 October 2026 (UTC). The runs below executed against `f18197ee03616891b8860474d9ef4bae247faaf9` with a clean working tree. This evidence commit only adds the run record.

## Code under test

| | |
| --- | --- |
| SHA tested | `f18197ee03616891b8860474d9ef4bae247faaf9` |
| Branch | `cursor/hebrew-unicode-slugs-6792` |
| What that SHA is | MOSS-058 rebased onto main `d9db93d18128033ae326e159b2171b6cee4adc82` |
| Ticket read SHA | `2d4c6082d308c638c981a3ed6a26f02142ac2532` |
| Main at this run | `d9db93d18128033ae326e159b2171b6cee4adc82` (MOSS-032) |
| Previous required-run record | MOSS-032 `79f3cbdf0458058f1b12bba7c3b79cbfc2fe47ae`: collected 435, SQLite 431 passed / 4 deselected / 0 skipped, PostgreSQL 435 passed / 0 skipped |
| `git status --porcelain` at the start of this run | empty (clean). The log header records `STATUS 0` |
| API run | 2026-10-29T05:40:05Z through 2026-10-29T05:43:40Z |
| Web and example site | 2026-10-29T05:40:09Z through 2026-10-29T05:40:53Z |
| Python / uv | 3.12.3 / 0.12.23 |
| ruff / mypy / pip-audit | 0.16.10 / 2.4.0 / 2.10.1 |
| Node / npm | v22.23.4 / 10.9.9 |
| PostgreSQL required run | 16.15 (Ubuntu), `127.0.0.1:5432`, role `pg`, database `postgres` |
| Docker / Compose | 29.1.3 / 2.40.3 |

`f18197e` keeps Unicode letters and combining marks in slugs. Bidi and zero-width characters (U+200B–U+200F, U+202A–U+202E, U+2066–U+2069, U+FEFF) are stripped before NFC and casefold. Characters outside categories L*, M*, and N* become `-`. The script rule is the one Architecture stated for this ticket: Latin plus at most one other script, plus digits and hyphen. `nextjs-מדריך` is accepted. Latin mixed with Cyrillic or Greek is rejected. Hebrew mixed with Arabic is rejected. A single Cyrillic or Greek script is accepted.

The character limit stays 220. The byte limit is 600, measured as `len(slug.encode("utf-8"))` on the NFC casefolded slug before percent-encoding. Website paths stay raw in `website_paths.path` (`String(300)` still fits a 220-character slug plus the section prefix). GraphQL and REST delivery percent-encode those paths with `urllib.parse.quote(path, safe="/")`, which is uppercase hex, the same form as MOSS-031. Existing stored slugs are left unchanged: there is no migration and no rewrite on read. The client slugifier uses the same script table, casefold table, and `shared/slug-vectors.json`. The server remains the authority.

## Commands

No `-k`, `--ignore`, new skips, or xfails. A runtime skip or xfail fails the API required runs. PostgreSQL-only tests use the `postgres` marker and are excluded from the SQLite required run with `-m "not postgres"`. Compose tests ran in both required runs. GitHub Actions was not used. `pip-audit` had no ignore, allowlist, or override.

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
uv export --frozen --all-groups --no-emit-project -o /tmp/moss-058-rebased/requirements.txt
uv run --with pip-audit pip-audit --progress-spinner off -r /tmp/moss-058-rebased/requirements.txt

cd web
npm run check && npm test && npm run build && npm audit --audit-level=high
npm audit

cd example-site
npm run check && npm test && npm run build && npm audit --audit-level=high
npm audit
```

## Results

| Command | Exit | Result |
| --- | --- | --- |
| ruff check app, tests, migrations | 0 | all checks passed |
| ruff format check of those files | 0 | 88 files already formatted |
| ruff check scripts and example-site setup | 0 | all checks passed |
| ruff format check of those files | 0 | 16 files already formatted |
| ruff check `ci/telemetry_smoke.py` | 0 | all checks passed |
| ruff format check of that file | 0 | 1 file already formatted |
| `uv run mypy app` | 0 | no issues in 29 source files |
| SQLite required run | 0 | collected 483, **479 passed, 4 deselected, 0 skipped**, 6 warnings in 73.16s |
| PostgreSQL 16.15 required run | 0 | collected 483, **483 passed, 0 deselected, 0 skipped**, 6 warnings in 109.04s |
| `tests/verify_required_runs.py` | 0 | `ok: true`; union of passed ids is 483 |
| `pip-audit` 2.10.1 | 0 | No known vulnerabilities found |
| `cd web && npm run check` | 0 | `tsc -b` |
| `cd web && npm test` | 0 | 36 files, 356 tests passed |
| `cd web && npm run build` | 0 | vite build succeeded in 6.89s |
| `cd web && npm audit` and `--audit-level=high` | 0 | found 0 vulnerabilities |
| `cd example-site && npm run check` | 0 | `tsc --noEmit` |
| `cd example-site && npm test` | 0 | 47 passed, 0 failed, 0 skipped |
| `cd example-site && npm run build` | 0 | vite build succeeded in 8.40s |
| `cd example-site && npm audit` and `--audit-level=high` | 0 | found 0 vulnerabilities |

The four ids deselected on SQLite are the committed list in `api/tests/required_runs.json`. No xfail. `tests/test_compose.py` executed in both required runs.

Against the MOSS-032 required-run counts (collected 435, SQLite 431 passed / 4 deselected, PostgreSQL 435 passed) this run adds 48 tests: 47 in `api/tests/test_slugs.py` and `test_import_accepts_normalized_hebrew_and_rejects_unnormalized_slugs`. Web went from 317 to 356 (38 shared-vector tests plus the Hebrew editor suggestion). The example site went from 46 to 47 (the Hebrew Next.js route). No new skips or failures.

Logs: [lint.txt](f18197e/lint.txt), [pytest-sqlite.txt](f18197e/pytest-sqlite.txt), [pytest-postgres.txt](f18197e/pytest-postgres.txt), [verify.txt](f18197e/verify.txt), [pip-audit.txt](f18197e/pip-audit.txt), [web.txt](f18197e/web.txt), [example-site.txt](f18197e/example-site.txt).

## Mutation checks

Each guard was switched on `f18197e`, the focused test was run, and the source was restored before this evidence commit. `git diff` was empty afterward. All three mutated runs exited 1. The restored lines are `if len(others) > 1` in `api/app/slugs.py`, `if (others.length > 1) return false` in `web/src/lib/slugify.ts`, and `len(slug.encode("utf-8")) > SLUG_MAX_BYTES`.

1. Allowing two non-Latin scripts. `len(others) > 1` was changed to `len(others) > 2`. `test_allowing_two_scripts_is_rejected` failed with `assert not True` for `allows_scripts({'Arabic', 'Hebrew'})`, and `test_shared_slug_vectors[hebrew-arabic]` did not raise `CmsError`. 2 failed, 33 deselected. Log: [two-scripts.txt](f18197e/mutations/two-scripts.txt).

2. The same relaxation in the client, `others.length > 1` changed to `others.length > 2`. Vitest failed `hebrew-arabic` (`expected [Function] to throw an error`) and `allowsScripts(new Set(['Hebrew', 'Arabic']))` (expected false, received true). 2 failed, 36 passed. Log: [two-scripts-vitest.txt](f18197e/mutations/two-scripts-vitest.txt).

3. Raw versus percent-encoded length. The byte check was switched to `len(encode_website_path(slug).encode("utf-8"))`. The 200-character Han slug is 600 UTF-8 bytes and longer once percent-encoded, so `slugify(exact)` raised `CmsError` at `api/app/slugs.py`. `test_byte_limit_is_nfc_utf8_before_percent_encoding` failed at `tests/test_slugs.py:76`. Log: [byte-limit.txt](f18197e/mutations/byte-limit.txt).
