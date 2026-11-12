# MOSS-076 delivery secret, invitations, and logout

local

Recorded 12 November 2026 (UTC). `scripts/verify.sh MOSS-076` started from a clean `git status` at `b431a037659057c31b3cf8890f25849cafb8e381`. The script refuses a dirty tree. It exited 1 in the SQLite pytest. The failed id is `tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests`. That test fails with the same assertion on main `b6c66870b98af990ee91766e5a965e823bf2b03d`. This ticket does not edit `.github/dependabot.yml` or `starters/nextjs/`.

The remaining commands from `scripts/verify.sh` were run afterward and recorded in [b431a03](b431a03/). PostgreSQL pytest and `tests/verify_required_runs.py` exit 1 for that same test id. Every other step exits 0. There is no runtime skip or xfail. No audit ignore, allowlist, or baseline was added to hide a finding.

The pull request head is the commit that adds this directory. The tested tree is the parent, `b431a03`.

## Code under test

| | |
| --- | --- |
| Base | `b6c66870b98af990ee91766e5a965e823bf2b03d` (main) |
| SHA tested | `b431a037659057c31b3cf8890f25849cafb8e381` |
| Branch | `cursor/moss-076-token-invites-7c73` |
| `git status --porcelain` at the start of `scripts/verify.sh` | empty (clean) |
| Date | 2026-11-12T14:49:59Z through 2026-11-12T15:09:19Z |
| Command | `scripts/verify.sh MOSS-076`, then the remaining commands from that script |
| `scripts/verify.sh` exit | 1 |
| Logs | [b431a03](b431a03/) |

`api/app/accounts.py` was not modified. The new tests passed against the handlers already on main, so there was no defect in that module to change. CLI password reset and OAuth were not changed.

`git diff b6c6687` for this tested commit is `api/tests/test_accounts_tokens.py` only.

## Counts against main `b6c6687`

Main collection is [baseline-b6c6687/collect.txt](baseline-b6c6687/collect.txt): 502 API tests. The dependabot failure on that commit is [baseline-b6c6687/dependabot.txt](baseline-b6c6687/dependabot.txt). Web, example-site, and the production smoke sources are unchanged from that commit, so the counts below are the counts for both trees. The full API suite was not re-executed on main.

| Run | Main `b6c6687` | This run `b431a03` | Skipped |
| --- | --- | --- | --- |
| API collected, no marker filter | 502 | 507 | |
| SQLite `-m "not postgres"` | dependabot test fails; full suite not re-run | 502 passed, 1 failed, 4 deselected | 0 |
| PostgreSQL, no marker filter | same dependabot assertion on the single test | 506 passed, 1 failed, 0 deselected | 0 |
| web | unchanged sources | 356 passed (36 files) | 0 |
| example-site | unchanged sources | 50 passed | 0 |
| production Playwright | unchanged sources | 2 passed | 0 |

The five added tests are in `tests/test_accounts_tokens.py`. The dot line for that file is five passes in both [pytest-sqlite.txt](b431a03/pytest-sqlite.txt) and [pytest-postgres.txt](b431a03/pytest-postgres.txt).

The failed id in both API runs is the dependabot manifest check. `tests/verify_required_runs.py` reports that same id and does not report a deselected-id mismatch. The four SQLite deselections are the PostgreSQL-marked tests already listed in `api/tests/required_runs.json`. Counts: [counts.txt](b431a03/counts.txt).

## Commands and results

`scripts/verify.sh MOSS-076` completed uv sync, ruff, ruff on scripts, and mypy with exit 0, then SQLite pytest with exit 1. [exit-codes.txt](b431a03/exit-codes.txt).

| Command | Exit |
| --- | --- |
| `uv sync --locked --group dev` | 0 |
| `ruff check` and `ruff format --check` for `app tests migrations` | 0 |
| ruff check/format of scripts, example-site setup, telemetry smoke | 0 |
| `mypy app` | 0 |
| SQLite required run | 1 |
| throwaway Postgres container | 0 |
| PostgreSQL required run, `MOSS_USE_SQLITE=false` | 1 |
| `tests/verify_required_runs.py` | 1 |
| OTLP Collector smoke | 0 |
| web `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 |
| example-site `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 |
| `pip-audit` against the frozen lock | 0 |
| `npm audit` web, example-site, and ci | 0 |
| `gitleaks` on `git archive HEAD` | 0 |
| production image, compose, Playwright, teardown | 0 |

No `--ignore-vuln`, npm override, or gitleaks allowlist was added.

The PostgreSQL command is the one in `scripts/verify.sh`, with `MOSS_USE_SQLITE=false` set the way that script sets it before the SQLite run. A collected import calls `setdefault` on that variable; leaving it unset let a later test in the same process see SQLite. That attempt was discarded and replaced by the log in this directory.

On this VM, `iptables-legacy` FORWARD policy was set to ACCEPT so Compose bridge traffic could pass. That change is outside the repository.

## What the new tests check

- Delivery create returns a body whose field is the secret, with `Cache-Control: no-store`. Later list and read responses do not contain that secret. The list id does not authorize `GET /delivery/types`. Revoking that id makes the secret stop working.
- An invitation can be accepted, and a later accept of the same link is rejected. The pending-list id is rejected as an invitation secret. An expired invitation is rejected and does not create an account. Revoking an unused invitation makes the link fail.
- A session cookie that works before logout is rejected afterward, including after a new sign-in. The new cookie value differs from the logged-out one.
- Request logs, the audit log, and the checked responses do not contain the delivery secret, the invitation secret, or the passwords used by the tests. The evidence logs do not contain those fixture passwords.
