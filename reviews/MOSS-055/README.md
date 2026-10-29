# MOSS-055 CI audits

local

Recorded 29 October 2026 (UTC). CI now runs the same audits as the QA gate: `npm audit` with dev dependencies included and no `--audit-level`, `pip-audit` 2.10.1 on the frozen `api/uv.lock` with no ignore list, and gitleaks 8.30.1 with no allowlist. No audit exception, override, or skip was added.

## Code under test

| | |
| --- | --- |
| Rebased SHA | `75e7889ae0e611bdc8ae9b59d763575aefa5fc1c` |
| Suite SHA | `dfe7eda8d9269b056b3420300d58aabc6dd2501e` |
| Branch | `cursor/moss-055-ci-audits-2b1f` |
| Parent after rebase | `2d4c6082d308c638c981a3ed6a26f02142ac2532` (main, includes MOSS-045) |
| Ticket baseline | `d50e2788485e4ef0c65598c4c2f2bd7536e1ed96` |
| `git status --porcelain` at the start of the suite | empty (clean) |
| Date | 2026-10-29T04:58:47Z through 2026-10-29T05:05:22Z |
| Python / uv / pip-audit | 3.12.3 / 0.12.23 / 2.10.1 |
| Node / npm | v22.23.4 / 10.9.9 |
| gitleaks / actionlint | 8.30.1 / 1.7.12 |
| PostgreSQL | 17.11, `postgres:17-alpine`, `127.0.0.1:5432`, role `pg`, database `postgres` |
| Docker / Compose | 29.1.3 / 2.40.3 |

The suite ran on `dfe7eda`, then the branch was rebased onto main `2d4c608`. `git diff dfe7eda 75e7889 -- .github/workflows docs/docker.md` is empty. The only tree difference is the MOSS-045 documentation already on that main commit (`README.md` status paragraph, `TODO.md`, `reviews/MOSS-045/`). Application code, lockfiles, and workflows are unchanged, so the suite counts still apply. `npm audit`, `pip-audit`, and gitleaks were run again on `75e7889` with a clean tree.

MOSS-045's README and TODO edits are still present. This branch does not change `checks.yml` relative to that rebase except for the audit steps in this ticket.

## What CI runs

`.github/workflows/checks.yml`:

- `web` and `example-site`: `npm audit` (the `--audit-level=high` flag is gone). Dev dependencies stay included. There is no `--omit=dev`.
- `api`: `uv export --frozen --all-groups --no-emit-project` from `api/uv.lock`, then `uv run --with pip-audit==2.10.1 pip-audit --progress-spinner off -r /tmp/moss-requirements.txt`. No `--ignore-vuln`.
- `gitleaks`: checkout is `actions/checkout@11d5960a326750d5838078e36cf38b85af677262` (`# v4.4.0`), full history. The job installs gitleaks 8.30.1 after checking sha256 `551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb`, then runs `gitleaks detect --source . --redact --verbose`.

No new third-party Action was added. Every external `uses:` remains a full commit SHA with a version comment. The local reusable workflow `./.github/workflows/checks.yml` is unchanged. actionlint 1.7.12 with shellcheck exited 0. Log: [75e7889/actionlint.txt](75e7889/actionlint.txt).

These jobs fail the workflow when they find an advisory or a leak. They are not a GitHub branch-protection gate. The merge decision is this local run.

## Positive control

A throwaway clone, branch `cursor/moss-055-positive-control`, commit `721b00a2a54d836278ed156343dfad9db65ba003`, based on `dfe7eda`. It was never pushed. The clone was deleted before the clean gitleaks scan.

Plants, both removed with that clone:

- `web` `vitest` and `@vitest/mocker` set to 4.1.11 in `package.json` and `package-lock.json`.
- `planted-test-secret.txt`, a synthetic Slack bot token. The value is not stored here. gitleaks was run with `--redact`.

| Command | Exit | Result |
| --- | --- | --- |
| `gitleaks detect --source . --redact --verbose` | 1 | 1 leak, rule `slack-bot-token`, file `planted-test-secret.txt` |
| `cd web && npm audit` | 1 | 2 moderate: [GHSA-qxg6-89mg-rqv8](https://github.com/advisories/GHSA-qxg6-89mg-rqv8), [GHSA-xp26-3454-mjgp](https://github.com/advisories/GHSA-xp26-3454-mjgp) |
| `cd web && npm audit --audit-level=high` | 0 | same moderate report, exit 0. The old CI flag would have passed this plant |

Logs: [positive-control/gitleaks.txt](positive-control/gitleaks.txt), [npm-audit.txt](positive-control/npm-audit.txt), [npm-audit-high.txt](positive-control/npm-audit-high.txt), and the matching `.exit` files. Meta: [positive-control/meta.txt](positive-control/meta.txt).

## Audits at `75e7889`

```sh
cd web && npm audit
cd example-site && npm audit
cd api && uv export --frozen --all-groups --no-emit-project -o /tmp/moss-requirements.txt
cd api && uv run --with pip-audit==2.10.1 pip-audit --progress-spinner off -r /tmp/moss-requirements.txt
gitleaks detect --source . --redact --verbose
```

| Command | Exit | Result |
| --- | --- | --- |
| `npm audit` web | 0 | found 0 vulnerabilities |
| `npm audit` example-site | 0 | found 0 vulnerabilities |
| `uv export --frozen` | 0 | requirements written |
| `pip-audit` 2.10.1 | 0 | No known vulnerabilities found |
| gitleaks 8.30.1 | 0 | no leaks found, 92 commits scanned |

Logs: [npm-audit-web-75e7889.txt](75e7889/npm-audit-web-75e7889.txt), [npm-audit-example-75e7889.txt](75e7889/npm-audit-example-75e7889.txt), [pip-audit-75e7889.txt](75e7889/pip-audit-75e7889.txt), [gitleaks-75e7889.txt](75e7889/gitleaks-75e7889.txt).

## Full local suite at `dfe7eda`

Same commands as `.github/workflows/checks.yml` and the README, plus `tests/verify_required_runs.py` and `npm audit` in `ci`. No `-k`, `--ignore`, new skip, or xfail was added. Counts match the MOSS-024 record at the ticket baseline `d50e278`: 403 collected. 403 is above the earlier 402-test tree.

| Command | Exit | Result |
| --- | --- | --- |
| ruff check `app tests migrations` | 0 | all checks passed |
| ruff format --check `app tests migrations` | 0 | 82 files already formatted |
| ruff check/format scripts, example-site setup, telemetry smoke | 0 | all checks passed; 14 files and 1 file already formatted |
| mypy app | 0 | no issues in 27 source files |
| SQLite `-m "not postgres"`, `MOSS_REQUIRED_RUN=sqlite` | 0 | 399 passed, 4 deselected, 0 skipped, 6 warnings in 65.10s |
| PostgreSQL `MOSS_REQUIRED_RUN=postgres` | 0 | 403 passed, 0 deselected, 0 skipped, 6 warnings in 119.16s |
| `tests/verify_required_runs.py` | 0 | `"ok": true`, union of passed ids is 403 |
| web check, test, build, `npm audit` | 0 | 35 files, 317 passed; build succeeded; 0 vulnerabilities |
| example-site check, test, build, `npm audit` | 0 | 46 passed, 0 failed, 0 skipped; build succeeded; 0 vulnerabilities |
| `npm audit` ci | 0 | found 0 vulnerabilities |
| pip-audit 2.10.1 | 0 | No known vulnerabilities found |
| gitleaks 8.30.1 | 0 | no leaks found |
| OTLP Collector smoke | 0 | pinned collector `0.156.0` |
| production image build | 0 | `mosscms:smoke` |
| production Compose `--wait` | 0 | app healthy |
| production Playwright | 0 | 2 passed |
| Compose down | 0 | stack removed |

The four SQLite deselections are the existing PostgreSQL-only tests, and the same four passed in the PostgreSQL run. No xfail.

Logs: [lint.txt](75e7889/lint.txt), [pytest-sqlite.txt](75e7889/pytest-sqlite.txt), [pytest-postgres.txt](75e7889/pytest-postgres.txt), [verify.txt](75e7889/verify.txt), [web.txt](75e7889/web.txt), [example-site.txt](75e7889/example-site.txt), [npm-audit-ci.txt](75e7889/npm-audit-ci.txt), [pip-audit.txt](75e7889/pip-audit.txt), [gitleaks.txt](75e7889/gitleaks.txt), [otel.txt](75e7889/otel.txt), [docker-build.txt](75e7889/docker-build.txt), [compose-up.txt](75e7889/compose-up.txt), [playwright.txt](75e7889/playwright.txt), [compose-down.txt](75e7889/compose-down.txt).
