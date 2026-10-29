# MOSS-009 client hardening

Two records, kept apart:

- `rehearsal (Linux VM)` — this virtual machine only. Loopback TLS. No public DNS, no registered domain, and no hosted deployment.
- `local` — the repository test suite on the same checkout, after the rehearsal.

The guide is [docs/client-hardening.md](../../docs/client-hardening.md). It is based on the verified MOSS-026 rehearsal ([reviews/MOSS-026/README.md](../MOSS-026/README.md), merged as `28c3dc969c4d5d36a6aa08c4f0103a5b512cd03a`). The MOSS-026 Compose stack was not still running on this machine. This record brings the same proxy shape back up: nginx TLS on `127.0.0.1:8443`, name `cms.moss.test` only in `/etc/hosts`, app on `127.0.0.1:8001`. It adds the Content-Security-Policy header and repeats the Strict-Transport-Security header. No hosting and no DNS registration were changed.

Application source for the check is `28c3dc969c4d5d36a6aa08c4f0103a5b512cd03a`. The admin files served are the production Vite build of this checkout (`web/dist`, which the image copies to `api/static`). The app process was Uvicorn from that checkout with `MOSS_USE_SQLITE=true` and an empty data directory under `/tmp`. Secrets, the TLS private key, and `.env` stayed out of git.

## rehearsal (Linux VM)

Recorded 29 October 2026 (UTC). Linux VM, kernel 6.12.94+. nginx 1.24.0 (Ubuntu). Python 3.12.3, uv 0.12.23, Node v22.23.4.

| | |
| --- | --- |
| Application SHA | `28c3dc969c4d5d36a6aa08c4f0103a5b512cd03a` |
| Date | 2026-10-29T05:34:03Z (first header check) through 2026-10-29T05:36:44Z (saved `curl -I`) |
| Browser pass | 2026-10-29T05:35:26Z through 2026-10-29T05:35:29Z |
| CMS origin | `https://cms.moss.test:8443` |
| App bind | `127.0.0.1:8001` |
| Names | `cms.moss.test` resolves through `/etc/hosts` to `127.0.0.1` |

`.test` is a reserved test name. Nothing was registered in DNS. The certificate is a local leaf for `cms.moss.test` and `site.moss.test`, signed by a CA that exists only on this VM. The private key stayed in `/tmp/moss-009-tls` and is not in this record. `MOSS_SECRET_KEY`, `MOSS_SETUP_TOKEN`, the administrator password, and any `.env` are not in this record.

Non-secret configuration of the process:

| Key | Value |
| --- | --- |
| `MOSS_ENV` | `production` |
| `MOSS_SKIP_AUTH` | `false` |
| `MOSS_USE_SQLITE` | `true` |
| `MOSS_PUBLIC_URL` | `https://cms.moss.test:8443` |
| `MOSS_ORIGINS` | `https://cms.moss.test:8443` |
| `MOSS_OTEL_ENABLED` | `false` |

SQLite was used so the header check did not need a database password in the tree. The single-process limit in the guide applies to PostgreSQL as well. The MOSS-026 rehearsal already ran this proxy shape against PostgreSQL 17.

### Commands

```sh
curl -sS -D - -o /dev/null -I --cacert /tmp/moss-009-tls/ca.crt https://cms.moss.test:8443/
curl -sS -D - -o /dev/null --cacert /tmp/moss-009-tls/ca.crt https://cms.moss.test:8443/ready
curl -sS -D - -o /dev/null -I --cacert /tmp/moss-009-tls/ca.crt https://cms.moss.test:8443/ready
```

The CA file is not a private key. It is omitted from the repository. `nginx -t -c /tmp/moss-009-tls/nginx.conf` succeeded before nginx was started. Config copy: [nginx.conf](rehearsal/nginx.conf).

`curl -I` of `GET`-capable `/` at 2026-10-29T05:36:44Z ([admin.headers](rehearsal/admin.headers)):

| Header | Value |
| --- | --- |
| status | `200` |
| `x-content-type-options` | `nosniff` |
| `referrer-policy` | `same-origin` |
| `x-frame-options` | `DENY` |
| `strict-transport-security` | `max-age=300` |
| `content-security-policy` | `default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'; upgrade-insecure-requests` |

`GET /ready` at the same time ([ready.headers](rehearsal/ready.headers), body [ready.body](rehearsal/ready.body)): `200` `{"status":"ready"}`, with the same two proxy headers.

`curl -I` of `/ready` is `405` with `allow: GET` ([ready-head.headers](rehearsal/ready-head.headers)). The route is registered for GET. Both proxy headers are still present because nginx uses `add_header ... always`.

### Admin console

Chromium loaded `https://cms.moss.test:8443/` with that policy. `securitypolicyviolation` events: 0. Log: [console.txt](rehearsal/console.txt).

| Screen | Result |
| --- | --- |
| Sign-in | heading "Welcome back". [admin-login.png](rehearsal/admin-login.png) |
| Content after sign-in | heading "Content". [admin-content.png](rehearsal/admin-content.png) |
| Overview, Import & export, API explorer, Settings, Assets | each page's heading rendered. Import & export loaded `/assets/Migration-BMW6KVXu.js` with 200 |

The only console error was `GET /auth/me` 401 before sign-in. After sign-in that request was 200. Fonts from `fonts.googleapis.com` and `fonts.gstatic.com` returned 200, which is why those two hosts are in the policy. No CSP message was recorded.

## local

Recorded 29 October 2026 (UTC). Labeled `local`. Application source is `28c3dc969c4d5d36a6aa08c4f0103a5b512cd03a`. The documentation in this change was on disk during the run. No application, test, workflow, or lockfile source was modified. `UV_NO_ENV_FILE=1`. No `.env` was present in the tree. The rehearsal process used its own environment and did not export into these commands.

| | |
| --- | --- |
| SHA at the start of the run | `28c3dc969c4d5d36a6aa08c4f0103a5b512cd03a` |
| Baseline in the ticket | `3a87c73c8e925973608e373863813163b41f04a9` (402 collected) |
| Suite already on this main | 433 collected (MOSS-026 record at `835fbf6`, after MOSS-056) |
| Date | 2026-10-29T05:37:17Z through 2026-10-29T05:41:13Z |
| Python / uv | 3.12.3 / 0.12.23 |
| ruff / mypy | 0.16.10 / 2.4.0 |
| Node / npm | v22.23.4 / 10.9.9 |
| PostgreSQL | 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1), role `ubuntu`, database `ubuntu`, local peer auth |
| Docker / Compose | 29.1.3 / 2.40.3 (compose-marked tests run inside pytest; they fail if Docker is missing) |

433 ≥ 402. The four SQLite deselections are the committed PostgreSQL-only ids in `api/tests/required_runs.json`, and the PostgreSQL run passed them. Both required runs recorded `"skipped": 0`. No new skip or xfail.

### Commands and results

Working directory `api` unless noted. No `-k`, `--ignore`, new skips, or xfails.

```sh
uv run ruff check app tests migrations
uv run ruff format --check app tests migrations
uv run ruff check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py
uv run ruff format --check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py
uv run ruff check --config pyproject.toml ../ci/telemetry_smoke.py
uv run ruff format --check --config pyproject.toml ../ci/telemetry_smoke.py
uv run mypy app
python3 ../scripts/check_dependabot.py
MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest -ra --tb=line -m "not postgres"
MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=postgres \
  MOSS_TEST_DATABASE_URL='postgresql+psycopg://ubuntu@/ubuntu' \
  uv run pytest -ra --tb=line
uv run python tests/verify_required_runs.py
cd ../web && npm run check && npm test && npm run build && npm audit --audit-level=high && npm audit
cd ../example-site && npm ci && npm run check && npm test && npm run build && npm audit --audit-level=high && npm audit
cd ../ci && npm audit && npm audit --audit-level=high
```

| Command | Exit | Result |
| --- | --- | --- |
| `ruff check app tests migrations` | 0 | all checks passed |
| `ruff format --check` | 0 | 85 files already formatted |
| ruff check scripts and example-site setup | 0 | all checks passed |
| ruff format check of those files | 0 | 15 files already formatted |
| ruff check `ci/telemetry_smoke.py` | 0 | all checks passed |
| ruff format check of that file | 0 | 1 file already formatted |
| `mypy app` | 0 | no issues in 28 source files |
| `scripts/check_dependabot.py` | 0 | schema valid; uv, npm, github-actions, and docker manifests covered |
| SQLite required run | 0 | collected 433, **429 passed, 4 deselected, 0 skipped**, 6 warnings in 62.93s |
| PostgreSQL required run | 0 | collected 433, **433 passed, 0 deselected, 0 skipped**, 6 warnings in 96.21s |
| `tests/verify_required_runs.py` | 0 | `"ok": true`; union of passed ids is 433 |
| web `npm run check` | 0 | `tsc -b` |
| web `npm test` | 0 | 35 files, 317 tests passed |
| web `npm run build` | 0 | vite build succeeded |
| web `npm audit` and `--audit-level=high` | 0 | 0 vulnerabilities |
| example-site `npm ci` | 0 | 0 vulnerabilities during install |
| example-site `npm run check` | 0 | `tsc --noEmit` |
| example-site `npm test` | 0 | 46 passed, 0 failed, 0 skipped |
| example-site `npm run build` | 0 | vite build succeeded |
| example-site `npm audit` and `--audit-level=high` | 0 | 0 vulnerabilities |
| ci `npm audit` and `--audit-level=high` | 0 | 0 vulnerabilities |

Logs: [ruff-check.txt](28c3dc9/ruff-check.txt), [ruff-format.txt](28c3dc9/ruff-format.txt), [ruff-scripts.txt](28c3dc9/ruff-scripts.txt), [ruff-scripts-format.txt](28c3dc9/ruff-scripts-format.txt), [ruff-telemetry.txt](28c3dc9/ruff-telemetry.txt), [ruff-telemetry-format.txt](28c3dc9/ruff-telemetry-format.txt), [mypy.txt](28c3dc9/mypy.txt), [dependabot.txt](28c3dc9/dependabot.txt), [pytest-sqlite.txt](28c3dc9/pytest-sqlite.txt), [pytest-postgres.txt](28c3dc9/pytest-postgres.txt), [verify.txt](28c3dc9/verify.txt), [web-check.txt](28c3dc9/web-check.txt), [web-test.txt](28c3dc9/web-test.txt), [web-build.txt](28c3dc9/web-build.txt), [web-audit.txt](28c3dc9/web-audit.txt), [web-audit-high.txt](28c3dc9/web-audit-high.txt), [example-site-ci.txt](28c3dc9/example-site-ci.txt), [example-site-check.txt](28c3dc9/example-site-check.txt), [example-site-test.txt](28c3dc9/example-site-test.txt), [example-site-build.txt](28c3dc9/example-site-build.txt), [example-site-audit.txt](28c3dc9/example-site-audit.txt), [example-site-audit-high.txt](28c3dc9/example-site-audit-high.txt), [ci-audit.txt](28c3dc9/ci-audit.txt), [ci-audit-high.txt](28c3dc9/ci-audit-high.txt).

The ticket does not name an audit. `npm audit` was run because the repository's local check instructions include it. No ignore, allowlist, or override was added. The OTLP collector smoke and the production-image Playwright job were not re-run: this change does not modify the app, the image, or the workflows, and GitHub Actions is not used (no Actions quota). The compose-marked tests inside both pytest runs did execute.

## local, after rebasing onto main

`main` moved to `d9db93d18128033ae326e159b2171b6cee4adc82` (MOSS-032) while this branch was open. Rebased here. `web/` and `example-site/` are unchanged from the run above, so those counts still apply (317 and 46, both with 0 skipped). This section is the API suite on the rebased tree. Labeled `local`.

| | |
| --- | --- |
| SHA tested | `96997ed694f32736e3c278ed0b529d4750283fd7` |
| Parent on main | `d9db93d18128033ae326e159b2171b6cee4adc82` |
| `git status --porcelain` | empty at the start of pytest |
| Date | ruff, mypy, and the Dependabot check at 2026-10-29T05:44:30Z on `7c3914c` (same application files; the following commit only edits `CHANGELOG.md`). Pytest 2026-10-29T05:45:37Z through 2026-10-29T05:48:43Z on `96997ed` |
| PostgreSQL | 16.15, role `ubuntu`, database `ubuntu`, local peer auth |

`MOSS_*` was unset for pytest. `UV_NO_ENV_FILE=1`. An earlier attempt in the same shell inherited `MOSS_ENV=production` from the rehearsal process and failed at import; that attempt is not this result.

| Command | Exit | Result |
| --- | --- | --- |
| ruff check app, tests, migrations | 0 | all checks passed |
| ruff format check | 0 | 86 files already formatted |
| ruff check scripts, setup, telemetry smoke | 0 | all checks passed |
| ruff format check of those files | 0 | 16 files already formatted; telemetry smoke 1 file |
| `mypy app` | 0 | no issues in 28 source files |
| `scripts/check_dependabot.py` | 0 | schema valid |
| SQLite required run | 0 | collected 435, **431 passed, 4 deselected, 0 skipped**, 6 warnings in 64.27s |
| PostgreSQL required run | 0 | collected 435, **435 passed, 0 deselected, 0 skipped**, 6 warnings in 96.17s |
| `tests/verify_required_runs.py` | 0 | `"ok": true` |

435 ≥ 402 at `3a87c73`. The four SQLite deselections are the same committed PostgreSQL-only ids and passed on PostgreSQL. No new skip or xfail. Counts match the MOSS-032 run already on `main` (435 collected).

`python3 scripts/check_changelog.py` exits 1 on this branch and on `main` at `d9db93d` for the same pre-existing reason: `d9db93d18128033ae326e159b2171b6cee4adc82` is not cited. This branch's guide commit `7c3914c37003a94015f13fb0cce3bae5ed9b5d91` is cited from pull request 31. The changelog commit and this evidence commit touch only `CHANGELOG.md` or `reviews/`, which that script does not treat as user-visible. Log: [changelog.txt](96997ed/changelog.txt).

Logs: [pytest-sqlite.txt](96997ed/pytest-sqlite.txt), [pytest-postgres.txt](96997ed/pytest-postgres.txt), [verify.txt](96997ed/verify.txt), [ruff-check.txt](96997ed/ruff-check.txt), [ruff-format.txt](96997ed/ruff-format.txt), [ruff-scripts.txt](96997ed/ruff-scripts.txt), [ruff-scripts-format.txt](96997ed/ruff-scripts-format.txt), [ruff-telemetry.txt](96997ed/ruff-telemetry.txt), [ruff-telemetry-format.txt](96997ed/ruff-telemetry-format.txt), [mypy.txt](96997ed/mypy.txt), [dependabot.txt](96997ed/dependabot.txt).

## local, after merging main through MOSS-058

`main` gained MOSS-033 and MOSS-058 while this branch was open. Those commits were merged in, not rebased, so the published guide commit stays `7c3914c37003a94015f13fb0cce3bae5ed9b5d91`. This run is labeled `local`. `MOSS_*` was unset. `UV_NO_ENV_FILE=1`.

| | |
| --- | --- |
| SHA tested | `18ee0d8da2fc4c063480451e67c0826833a6695f` |
| Date | 2026-10-29T05:54:31Z through 2026-10-29T05:58:07Z |
| PostgreSQL | 16.15, role `ubuntu`, database `ubuntu` |

| Command | Exit | Result |
| --- | --- | --- |
| ruff check | 0 | all checks passed |
| ruff format check | 0 | 89 files already formatted |
| `mypy app` | 0 | no issues in 29 source files |
| SQLite required run | 0 | collected 487, **483 passed, 4 deselected, 0 skipped**, 6 warnings in 68.94s |
| PostgreSQL required run | 0 | collected 487, **487 passed, 0 skipped**, 6 warnings in 103.21s |
| `tests/verify_required_runs.py` | 0 | `"ok": true` |
| web `npm test` | 0 | 36 files, 356 tests passed |
| example-site `npm test` | 0 | 47 passed, 0 failed, 0 skipped |

487 ≥ 402 at `3a87c73`. The four SQLite deselections are the committed PostgreSQL-only ids and passed on PostgreSQL. No new skip or xfail. Counts match the MOSS-058 run on `main`.

`python3 scripts/check_changelog.py` exits 1 because `d9db93d` and `ae66eb0` are not cited. That is the same failure `main` has without this branch. This branch's guide commit is cited. Log: [changelog.txt](18ee0d8/changelog.txt).

Logs: [pytest-sqlite.txt](18ee0d8/pytest-sqlite.txt), [pytest-postgres.txt](18ee0d8/pytest-postgres.txt), [verify.txt](18ee0d8/verify.txt), [ruff-check.txt](18ee0d8/ruff-check.txt), [ruff-format.txt](18ee0d8/ruff-format.txt), [mypy.txt](18ee0d8/mypy.txt), [web-test.txt](18ee0d8/web-test.txt), [example-site-test.txt](18ee0d8/example-site-test.txt).

## local, after the squash onto main

Pull request 31 squash-merged as `43a93fc58007e82f11789d3c255820551bd249b1` at 2026-10-29T05:58:52Z. That commit is the user-visible change. The pre-squash guide SHA `7c3914c37003a94015f13fb0cce3bae5ed9b5d91` is not in `git log 3a87c73..HEAD` on `main`, so the Unreleased bullet now cites `43a93fc58007e82f11789d3c255820551bd249b1` and still links pull request 31. `gh pr view 31` reports that oid as `mergeCommit`. A direct push of that citation was rejected because `main` only accepts pull requests, so the citation lands through pull request 35. That follow-up changes only `CHANGELOG.md` and `reviews/`, which `scripts/check_changelog.py` does not treat as user-visible.

Recorded 2026-10-29T06:01:20Z on `main` at `43a93fc58007e82f11789d3c255820551bd249b1` with the citation already edited in the working tree. Labeled `local`.

```
python3 scripts/check_changelog.py
```

Exit 1. The only missing commits are the same two that `main` already failed to cite before this ticket: `d9db93d18128033ae326e159b2171b6cee4adc82` and `ae66eb0a9218cce4d24a45fa887126ea974013b8`. Log: [changelog.txt](43a93fc/changelog.txt).
