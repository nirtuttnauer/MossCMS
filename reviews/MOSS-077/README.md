# MOSS-077 local verification

label: local

| | |
| --- | --- |
| Ticket base named in the prompt | `b6c66870b98af990ee91766e5a965e823bf2b03d` |
| Branch base (`origin/main`) | `5ea1d037bb85e47c2efc1d97f72998d130130878` |
| Code verified | `1dbd4655384657d2b89d2c84676d557857157f3b` |
| Clean status | `reviews/MOSS-077/1dbd465/summary.txt` records an empty `git status --porcelain` when `scripts/verify.sh MOSS-077` started |
| Started | 2026-11-12T14:53:10Z |

`origin/main` is `b6c6687` plus `5ea1d03` (GitHub Actions pin bump). That commit changes `.github/workflows/checks.yml` and `.github/workflows/docker.yml`. It does not change the API, web, or example-site test trees, so the counts measured on `5ea1d03` are the `b6c6687` counts.

## What changed

`GET /auth/oauth/{provider}/callback` resolves the provider before the failure handler, so an unknown provider returns 404. `api/tests/test_oauth.py` drives the real Authlib client against a local HTTP double. A missing state, a mismatched state, a missing code, or a rejected code creates or links no user. The mocked success path links the existing admin account. Service logs and the provider-client logs do not contain the client secret marker or the authorization-code marker. The test client records the callback URL it was given; that line is the request under test.

`api/tests/test_cms.py` was not edited.

## Commands

`scripts/verify.sh MOSS-077` from a clean tree at `1dbd465` (2026-11-12T14:53:10Z). It exited 1 at `pytest-sqlite`. The same dependabot assertion fails on `origin/main` (`reviews/MOSS-077/1dbd465/dependabot-on-main.txt`, exit 1): `starters/nextjs/package.json` is not covered by `.github/dependabot.yml`. Those files are unchanged from `origin/main` and are outside this ticket's file list. No ignore, allowlist, or override was added.

An earlier sqlite run on the same commit, before `iptables-legacy -P FORWARD ACCEPT`, also failed `tests/test_private_admin_compose.py::test_variant_a_proxy_and_variant_b_private_listener` with `curl: (28)` to the published proxy. After the host FORWARD policy accepted packets, that test passed. The sqlite log in this directory is the rerun.

The steps after `pytest-sqlite` used the same commands as `scripts/verify.sh` and are logged beside that run. Exit codes are in `reviews/MOSS-077/1dbd465/exit-codes.txt`.

The `pip-audit` step exited 1 because this machine had no `python3.12-venv` (`ensurepip` missing). After `python3.12-venv` was installed, the same command exited 0: `No known vulnerabilities found` (`pip-audit-retry.txt`). `api/uv.lock` matches `origin/main`.

## Counts

| Suite | Base `5ea1d03` / `b6c6687` | Code `1dbd465` |
| --- | --- | --- |
| API pytest, SQLite, `-m "not postgres"` | 497 passed, 1 failed, 4 deselected, 0 skipped | 503 passed, 1 failed, 4 deselected, 0 skipped |
| API pytest, PostgreSQL | 501 passed, 1 failed, 0 skipped | 507 passed, 1 failed, 0 skipped |
| Admin web vitest | same tree as the head | 36 files, 356 passed, 0 skipped |
| Example site `node --test` | same tree as the head | 50 pass, 0 fail, 0 skipped |
| Production Playwright | same tree as the head | 2 passed, 0 skipped |

The API delta is the six tests in `api/tests/test_oauth.py`. They run on SQLite and on PostgreSQL. The one failure on both SHAs is `tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests`. The four PostgreSQL-only tests deselected on SQLite are the same four deselected on the base. `web/`, `example-site/`, and `ci/` are unchanged from `origin/main`, so those counts are the base counts.

Base API logs: `reviews/MOSS-077/5ea1d03/`. Head logs: `reviews/MOSS-077/1dbd465/`.

`tests/verify_required_runs.py` exited 1 because that same dependabot test is recorded as failed in both required-run result files. There were no runtime skips or xfails.

## Head commands that exited 0

`uv sync --locked --group dev`, ruff, ruff on scripts, mypy, OpenTelemetry smoke, web and example-site `npm ci` plus `npm run check && npm test && npm run build && npm audit --audit-level=high`, `npm audit` in `web/`, `example-site/`, and `ci/`, `gitleaks detect` on `git archive HEAD` (no leaks found), `npm ci` and `npx playwright install --with-deps chromium` in `ci/`, `docker build --tag mosscms:smoke .`, `docker compose -f ci/compose.yaml -p mosscms-smoke up --no-build -d --wait --wait-timeout 180`, `npm test` in `ci/` (2 passed), and `docker compose ... down --volumes`.
