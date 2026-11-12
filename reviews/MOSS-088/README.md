# MOSS-088 image user and Compose Postgres port

local

Recorded 12 November 2026 (UTC). `scripts/verify.sh MOSS-088` ran on a clean tree at `3a572638d84836291d1396da0d6428d4ff89592e` and exited 1 at the SQLite required run. The same Dependabot manifest check fails on main `b6c6687` and on main `5ea1d03`. The commands that follow `pytest-sqlite` in `scripts/verify.sh` were then run on this checkout and written into [3a57263](3a57263/). No skip, xfail, audit ignore, or allowlist was added.

## Code under test

| | |
| --- | --- |
| Comparison SHA named by the ticket | `b6c66870b98af990ee91766e5a965e823bf2b03d` |
| Branch base, current main | `5ea1d037bb85e47c2efc1d97f72998d130130878` |
| SHA `scripts/verify.sh` started on | `3a572638d84836291d1396da0d6428d4ff89592e` |
| Branch | `cursor/moss-088-image-user-compose-lock-81ad` |
| `git status --porcelain` at the start of `scripts/verify.sh` | empty |
| Started | 2026-11-12T14:51:24Z |
| Evidence directory finished | 2026-11-12T15:05:31Z |
| Command | `scripts/verify.sh MOSS-088`, then the remaining commands from that script |
| Python / uv | 3.12.3 / 0.12.23 |
| ruff / mypy / pip-audit | 0.16.10 / 2.4.0 / 2.10.1 |
| Node / npm | v22.23.4 / 10.9.9 |
| Docker / Compose | 29.1.3 / 2.40.3 |
| gitleaks | 8.30.1 |

`git diff b6c6687 5ea1d03` is the workflow pin update already on main. `Dockerfile`, `compose.yaml`, `compose.database.false.yaml`, `compose.benchmark.yaml`, `compose.observability.yaml`, `web`, and `example-site` match `b6c6687`. This branch adds `api/tests/test_compose_hardening.py`.

The evidence files were committed after the run, so the pull request head is that later commit. The counts below are for `3a57263`.

This VM needed `iptables` pointed at `iptables-legacy` before Docker started, so a Compose bridge is accepted by the forward rules. `python3.12-venv` was installed so `pip-audit` can create its temporary environment. Neither change is in the repository.

## What the new tests lock

`api/tests/test_compose_hardening.py` reads the checked-in `Dockerfile` and renders the default Compose project. `docker compose up` and `scripts/start.py` both use `compose.yaml`. With `MOSS_USE_SQLITE` unset, that file extends `compose.database.false.yaml`, whose `db` service is `postgres:17-alpine`.

`compose.benchmark.yaml` says it is independent of the normal Compose file. `compose.observability.yaml` is an optional overlay (`docker compose -f compose.yaml -f compose.observability.yaml`). Neither file is the documented start path, so both were left unchanged. The benchmark file publishes no host port. The observability overlay publishes `127.0.0.1:9464`, not `5432`. `ci/compose.yaml` is the smoke file, not the documented start path, and its `db` service has no `ports` entry. It was left unchanged.

The checked-in runtime stage is `USER appuser`, created with `--uid 10001`. The default render has no published port whose host or container number is 5432, and the `db` image is `postgres:17-alpine`. Those files already matched the lock, so `Dockerfile` and `compose.yaml` were not edited.

The suite fails when the runtime `USER` is `root`, `0`, `0:0`, or `root:root`, when that instruction is removed, when it sits in an earlier stage, and when the runtime account is created with `--uid 0`. It also fails when `5432:5432`, `127.0.0.1:5432:5432`, or `127.0.0.1:15432:5432` is added on the Postgres service, and when `5432:5432` is added on `db` in `compose.yaml`. Those cases use copies. The checked-in files stay as they are.

## Counts against main `b6c6687`

`pytest --collect-only -q` on the branch point, before `test_compose_hardening.py` existed, collected 502 tests. The API test sources other than that new file match `b6c6687` and `5ea1d03`, so that collected count is the count at both SHAs. This run collected 515. The difference is the 13 tests in `tests/test_compose_hardening.py`, and those 13 passed in both required runs.

| Run | Main `b6c6687` | This run | Deselected | Skipped |
| --- | --- | --- | --- | --- |
| SQLite `-m "not postgres"` | 502 collected | 515 collected, 510 passed, 1 failed | 4 | 0 |
| PostgreSQL, no marker filter | 502 collected | 515 collected, 514 passed, 1 failed | 0 | 0 |
| web | same tree as this run | 356 passed (36 files) |  | 0 |
| example-site | same tree as this run | 50 passed |  | 0 |
| production Playwright | same tree as this run | 2 passed |  | 0 |

The failed id in both required runs is `tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests`. The message is `starters/nextjs/package.json (npm /starters/nextjs) is not covered by .github/dependabot.yml`. The same command on detached `b6c6687` and detached `5ea1d03` exited 1 with that message: [dependabot-b6c6687.txt](main/dependabot-b6c6687.txt), [dependabot-5ea1d03.txt](main/dependabot-5ea1d03.txt). `.github/dependabot.yml` and `starters/nextjs/` were not edited.

The four ids deselected on SQLite are the committed list in `api/tests/required_runs.json`. No xfail. `tests/verify_required_runs.py` exited 1 because that Dependabot id did not pass. It names no other id. [verify-required-runs.txt](3a57263/verify-required-runs.txt). [counts.json](3a57263/counts.json).

## Commands and results

| Command | Exit |
| --- | --- |
| `scripts/verify.sh MOSS-088` | 1 at `pytest-sqlite` |
| `uv sync --locked --group dev` | 0 |
| `ruff check` and `ruff format --check` for `app tests migrations` | 0 |
| ruff check/format of scripts, example-site setup, telemetry smoke | 0 |
| `mypy app` | 0 |
| SQLite required run | 1, Dependabot manifest check |
| PostgreSQL required run in the throwaway container | 1, same Dependabot check |
| `tests/verify_required_runs.py` | 1, same id |
| OTLP Collector smoke | 0 |
| web `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 |
| example-site `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 |
| `pip-audit` against the frozen lock | 0, no known vulnerabilities found |
| `npm audit` web, example-site, and ci | 0, found 0 vulnerabilities |
| `gitleaks` on `git archive HEAD` | 127, then 0 |
| production image, compose, Playwright, teardown | 0 |

`gitleaks` exited 127 when the continuation shell could not see the binary `scripts/verify.sh` had installed under `~/.cache/moss-verify/gitleaks-8.30.1`. The retry with that directory on `PATH` scanned the archive and reported no leaks. Log of the 127 run: [gitleaks-path.txt](3a57263/gitleaks-path.txt). Successful scan: [gitleaks.txt](3a57263/gitleaks.txt).

No `--ignore-vuln`, npm override, or gitleaks allowlist was added. No image was pushed and nothing was deployed.
