# MOSS-087 local verification

label: local

| | |
| --- | --- |
| Base | `b6c66870b98af990ee91766e5a965e823bf2b03d` |
| Verified tree | `04d5ca90af4a4acc32f10f5e343c7b1d9a1ee4d2` |
| Clean status | [04d5ca9/summary.txt](04d5ca9/summary.txt) records an empty `git status --porcelain` when `scripts/verify.sh MOSS-087` started |
| Started | 2026-11-12T14:54:42Z |
| Continuation finished | 2026-11-12T15:06:46Z |

`api/app/main.py` is unchanged. `GET /health` and `GET /ready` already return a bounded status, and a failed ready check already returns 503. `GET /metrics` already requires an admin session. `api/tests/test_health.py` locks that behavior.

## Locked behavior

- `GET /health` is 200 and `{"status":"ok"}`.
- `GET /ready` is 200 and `{"status":"ready"}`.
- When the ready check raises, the response is 503 and `{"status":"unavailable"}`. The exception text is not copied into the body.
- Those bodies do not contain the configured database URL, origins, secret, setup token, or storage path, and they do not echo a query or header marker.
- `GET /metrics` with an admin session and project header is the four counter lines.
- A call with no session, a delivery token, a reader session, an editor session, or an admin session without a project is 401 or 403. The body does not contain the counter names or those configured values.

## Commands

`scripts/verify.sh MOSS-087` from a clean tree at `04d5ca9` (2026-11-12T14:54:42Z). Exit 1 at `pytest-sqlite`.

The failure is `tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests`: `starters/nextjs/package.json (npm /starters/nextjs) is not covered by .github/dependabot.yml`. The same assertion fails on main `b6c6687`. Logs: [b6c6687/pytest-sqlite.txt](b6c6687/pytest-sqlite.txt) and [b6c6687/pytest-postgres.txt](b6c6687/pytest-postgres.txt). `.github/dependabot.yml` and `starters/nextjs/` were not edited.

An earlier SQLite run on main, before `iptables-legacy` policy FORWARD was set to ACCEPT, also failed `test_variant_a_proxy_and_variant_b_private_listener` with `curl: (28) Operation timed out`. After that policy change, the compose test passed on main and on this tree. The main logs in this folder are the rerun.

`scripts/verify.sh` stops when `pytest-sqlite` exits 1. The remaining commands from that script were run with the same arguments and logged under [04d5ca9/](04d5ca9/). Exit codes are in [04d5ca9/exit-codes.txt](04d5ca9/exit-codes.txt).

Two continuation steps were repeated after a local setup fix:

- `gitleaks` exited 127 because the continuation shell did not include the binary `verify.sh` had installed. The repeat, with `~/.cache/moss-verify/gitleaks-8.30.1` on `PATH`, exited 0. No leaks found. Log: [04d5ca9/gitleaks.txt](04d5ca9/gitleaks.txt).
- `pip-audit` failed once because `EVIDENCE` was unset in that shell, and once because `python3.12-venv` was missing, so `uv run --with pip-audit` could not create a virtual environment. After `apt install python3.12-venv`, the same audit exited 0 on this tree and on main. No known vulnerabilities found. Logs: [04d5ca9/pip-audit.txt](04d5ca9/pip-audit.txt), [b6c6687/pip-audit.txt](b6c6687/pip-audit.txt). `api/uv.lock` is unchanged from the base.

`scripts/verify_report.py scan` on both pytest logs exited 0. The four PostgreSQL-marked tests deselected by `-m "not postgres"` are the same four ids on main. There is no runtime skip or xfail in those logs.

Base commands (2026-11-12, label local), from a checkout of `b6c6687` in `/tmp/moss-base`:

- `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest -m "not postgres"` in `api/` — exit 1
- `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=postgres MOSS_TEST_DATABASE_URL=postgresql+psycopg://pg:pgtestpw@127.0.0.1:5432/postgres uv run pytest` in `api/` — exit 1
- `npm ci && npm test` in `web/` — exit 0

## Counts

| Suite | Base `b6c6687` | Verified tree `04d5ca9` |
| --- | --- | --- |
| API pytest, SQLite, `-m "not postgres"` | 497 passed, 1 failed, 4 deselected, 0 skipped | 502 passed, 1 failed, 4 deselected, 0 skipped |
| API pytest, PostgreSQL | 501 passed, 1 failed, 0 skipped | 506 passed, 1 failed, 0 skipped |
| Admin web vitest | 36 files, 356 passed, 0 skipped | 36 files, 356 passed, 0 skipped |
| Example site `node --test` | not re-run; `example-site/` matches the base | 50 pass, 0 fail, 0 skipped |
| Production Playwright | not re-run on the base | 2 passed, 0 skipped |

The API difference is the five tests in `api/tests/test_health.py`. Both trees fail the same Dependabot coverage test. Web sources match the base (`git diff b6c6687 04d5ca9 -- web example-site` is empty). Head counts are also in [04d5ca9/counts.json](04d5ca9/counts.json).

## Other results at `04d5ca9`

| Command | Exit |
| --- | --- |
| `uv sync --locked --group dev` | 0 |
| ruff check and format, app/tests/migrations | 0 |
| ruff check and format, scripts and telemetry smoke | 0 |
| `uv run mypy app` | 0 |
| SQLite pytest | 1 |
| PostgreSQL pytest | 1 |
| `tests/verify_required_runs.py` | 1 |
| OpenTelemetry smoke | 0 |
| web `npm ci`, `npm run check`, `npm test`, `npm run build`, `npm audit --audit-level=high` | 0 |
| example-site `npm ci`, `npm run check`, `npm test`, `npm run build`, `npm audit --audit-level=high` | 0 |
| `pip-audit` after `python3.12-venv` was installed | 0 |
| `npm audit` in `web/`, `example-site/`, and `ci/` | 0 |
| `gitleaks detect` on `git archive HEAD` | 0 |
| `ci/` `npm ci` and `npx playwright install --with-deps chromium` | 0 |
| `docker build --tag mosscms:smoke .` | 0 |
| compose up, `npm test` in `ci/`, compose down | 0 |

`npm audit` reported `found 0 vulnerabilities` in each of those three directories. The required-run check fails because the Dependabot test did not pass; no other collected id is missing.
