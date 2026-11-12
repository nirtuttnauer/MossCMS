# MOSS-093 OpenAPI secret-shaped samples

label: local

Recorded 2026-11-12 (UTC). GitHub Actions was not used.

## SHAs

| | |
| --- | --- |
| Base | `5ea1d037bb85e47c2efc1d97f72998d130130878` (`main`) |
| Verified tree | `dab65dd27ba4680e93b966e801856d9a10a41418` |
| `git status --porcelain` at the start of `scripts/verify.sh MOSS-093` | empty |
| Verify start | 2026-11-12T15:57:01Z |
| Continued steps finished | 2026-11-12T16:09:20Z |
| Python / uv | 3.12.3 / 0.13.7 |
| ruff / mypy | 0.16.10 / 2.4.0 |
| Node / npm | v22.23.4 / 10.9.9 |
| Docker / Compose | 29.1.3 / 2.40.3 |
| gitleaks | 8.30.1 |
| PostgreSQL | 17.11 (`postgres:17-alpine`) |

`dab65dd` adds `api/tests/test_openapi_secret_scan.py`. The committed OpenAPI document and the schema `build_openapi` returns had no secret-shaped example, default, or description sample, so `api/openapi.json` and `api/app/openapi_schema.py` were not edited. `api/tests/test_openapi.py` and `api/app/delivery_rest.py` were not edited.

The scan walks example, examples, and default values, and description text. It rejects common API-key prefixes (`sk_live_` / `sk_test_` / `rk_` / `pk_` and `sk-`), GitHub token prefixes (`ghp_` / `gho_` / `ghu_` / `ghs_` / `ghr_` / `github_pat_`), cloud token prefixes (AWS access-key ids, `AIza`, `ya29.`), chat-bot token prefixes (`xoxb-` and the other `xox*-` forms, plus a numeric bot-token shape), password assignments, and PEM private-key armor. Planted fixture documents use split, clearly fake markers. The same assertion that the committed document must satisfy raises `AssertionError` on those fixtures, and the test expects that raise. The failure text names the pattern and the JSON pointer, not the sample text.

## Commands

`scripts/verify.sh MOSS-093` on `dab65dd` from a clean tree. Exit 1. It stopped at the SQLite required run because `test_dependabot_config_matches_schema_and_covers_manifests` failed. That test also fails on `5ea1d03` with `starters/nextjs/package.json (npm /starters/nextjs) is not covered by .github/dependabot.yml`. `.github/dependabot.yml` was not edited.

The steps after that used the same commands as `scripts/verify.sh` and were logged in [dab65dd](dab65dd/). Exit codes are in [exit-codes.txt](dab65dd/exit-codes.txt).

On this machine, `iptables-legacy` `FORWARD` was `DROP` before the recorded run, and `test_variant_a_proxy_and_variant_b_private_listener` then timed out contacting the proxy. The policy was set to `ACCEPT` before `scripts/verify.sh MOSS-093`. In the recorded SQLite and PostgreSQL logs that test passed. `pip-audit` needed `python3.12-venv` so its isolated environment could be created. The recorded audit says `No known vulnerabilities found`.

## Counts

| Suite | Base `5ea1d03` | Verified `dab65dd` |
| --- | --- | --- |
| API pytest, SQLite, `-m "not postgres"` | 502 collected, 497 passed, 1 failed, 4 deselected, 0 skipped | 518 collected, 513 passed, 1 failed, 4 deselected, 0 skipped |
| API pytest, PostgreSQL | 502 collected, 501 passed, 1 failed, 0 skipped | 518 collected, 517 passed, 1 failed, 0 skipped |
| Admin web vitest | not re-run | 36 files, 356 passed, 0 skipped |
| Example site `node --test` | not re-run | 50 passed, 0 failed, 0 skipped |
| Production Playwright | not re-run | 2 passed, 0 skipped |

The API delta is the 16 tests in `api/tests/test_openapi_secret_scan.py`. They passed on SQLite and on PostgreSQL. The failed id on the base and on the verified tree is `tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests`. No skip and no xfail. The four SQLite deselections are the committed PostgreSQL-only ids in `api/tests/required_runs.json`, and they passed in the PostgreSQL run.

Base logs: [pytest-sqlite.txt](5ea1d03/pytest-sqlite.txt), [pytest-postgres.txt](5ea1d03/pytest-postgres.txt). Base commands ran from a detached checkout of `5ea1d03` with the branch virtualenv, dated 2026-11-12T16:13:37Z (SQLite) and 2026-11-12T16:17:31Z (PostgreSQL).

`tests/verify_required_runs.py` exited 1 because that dependabot id is in the failed set for both required runs. Web, example-site, npm audit, gitleaks, the OpenTelemetry smoke, and the production Playwright test exited 0.

## Head steps on `dab65dd`

| Step | Exit |
| --- | --- |
| `uv sync --locked --group dev` | 0 |
| ruff check and format | 0 |
| ruff on scripts, example-site setup, telemetry smoke | 0 |
| `mypy app` | 0 |
| SQLite `uv run pytest -m "not postgres"` | 1 |
| PostgreSQL `uv run pytest` | 1 |
| `tests/verify_required_runs.py` | 1 |
| OpenTelemetry smoke | 0 |
| web `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 |
| example-site `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 |
| `pip-audit` on the locked export | 0 |
| `npm audit` in web, example-site, and ci | 0 |
| gitleaks on `git archive HEAD` | 0 |
| production image, compose, Playwright | 0 |
