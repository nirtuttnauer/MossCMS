# MOSS-084 backup archives and env files

label: local

Operator backup archives from a monkeypatched fixture workspace do not contain `.env` or `.env.*` paths, and they do not contain the planted database password stored in those files. Media restore still requires `--confirm-empty-volume` and does not write those paths into the volume.

## SHAs

| | |
| --- | --- |
| Ticket comparison base | `b6c66870b98af990ee91766e5a965e823bf2b03d` |
| Branch point (`origin/main`) | `5ea1d03` (GitHub Actions pin bump on top of `b6c6687`; product files match that base) |
| Verified tree | `59e34ac27bf842f2bc8a67c4923aa3284dbaa354` |
| Clean status | `reviews/MOSS-084/59e34ac/summary.txt` records an empty `git status --porcelain` when `scripts/verify.sh MOSS-084` started |
| Started | 2026-11-12T15:02:07Z |
| Date | 2026-11-12 (UTC) |

`git diff b6c6687..5ea1d03` is `.github/workflows/checks.yml` and `.github/workflows/docker.yml` only.

## What changed

`scripts/backup.py` passes `--exclude=.env` and `--exclude=.env.*` to the media `tar`. `scripts/restore_media.py` skips archive members whose path contains `.env` or a `.env.*` component. `scripts/restore.py` is unchanged. Database restore still requires the target name twice and still refuses a database that is not empty.

`api/tests/test_backup_redaction.py` builds a fixture workspace, monkeypatches `subprocess.run`, and runs the backup script's tar arguments against that workspace. No Docker daemon is started by that test. The media archive keeps the upload, the SQLite file, and a file named `.environment`. It has no `.env` / `.env.*` member, and the planted password bytes are absent from the archive and the dump. A backup with `--database-only` writes the dump and does not write a media archive. Media restore without `--confirm-empty-volume` exits before `docker` is called. With the flag, an archive that also contains env members restores `image.webp` and `note.txt` and does not write those env paths.

## Commands

`scripts/verify.sh MOSS-084` on the clean tree at `59e34ac`. Exit 1 at `pytest-sqlite`. The same Dependabot failure is on `b6c6687` (`reviews/MOSS-084/b6c6687/pytest-sqlite.txt`): `starters/nextjs/package.json` is not covered by `.github/dependabot.yml`. Those files are outside this ticket. No ignore, allowlist, or override was added.

The script stops at that step. The later commands from `scripts/verify.sh` were run on the same checkout and written into `reviews/MOSS-084/59e34ac/`. Exit codes are in [exit-codes.txt](59e34ac/exit-codes.txt).

Before the recorded API runs, `iptables-legacy` `FORWARD` was `DROP`, and a container-to-container connection timed out. `iptables-legacy -P FORWARD ACCEPT` was set in this VM. That is not a repository change. The baseline logs below are the runs after that change.

## Counts

| Suite | `b6c6687` | `59e34ac` |
| --- | --- | --- |
| API pytest, SQLite, `-m "not postgres"` | 497 passed, 1 failed, 4 deselected, 0 skipped | 500 passed, 1 failed, 4 deselected, 0 skipped |
| API pytest, PostgreSQL | 501 passed, 1 failed, 0 skipped | 504 passed, 1 failed, 0 skipped |
| Admin web vitest | 36 files, 356 passed, 0 skipped | 36 files, 356 passed, 0 skipped |
| Example site `node --test` | 50 pass, 0 fail, 0 skipped | 50 pass, 0 fail, 0 skipped |
| Production Playwright | not run on the base in this session | 2 passed, 0 skipped |

The API difference is the three tests in `api/tests/test_backup_redaction.py`. Web and example-site counts match. The four deselected SQLite ids are the PostgreSQL-marked tests committed in `api/tests/required_runs.json`. `tests/verify_required_runs.py` exits 1 because the Dependabot test failed in both required runs. It does not report a deselected-id mismatch, a runtime skip, or a different failing test.

Baseline commands (2026-11-12, label local), from a checkout of `b6c6687`:

- `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest -m "not postgres"` in `api/` — exit 1
- `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=postgres MOSS_TEST_DATABASE_URL=postgresql+psycopg://pg:pgtestpw@localhost:5432/postgres uv run pytest` in `api/` — exit 1
- `npm test` in `web/` — exit 0
- `npm test` in `example-site/` — exit 0

Logs: [b6c6687](b6c6687/).

Head commands, label local, SHA `59e34ac`:

| Command | Exit |
| --- | --- |
| `uv sync --locked --group dev` | 0 |
| ruff check and format for `app tests migrations` | 0 |
| ruff check and format for scripts, example-site setup, telemetry smoke | 0 |
| `mypy app` | 0 |
| SQLite `uv run pytest -m "not postgres"` | 1 |
| PostgreSQL `uv run pytest` | 1 |
| `tests/verify_required_runs.py` | 1 |
| OpenTelemetry smoke | 0 |
| web `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 |
| example-site `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 |
| `pip-audit` against the frozen lock | 0 |
| `npm audit` in `web/`, `example-site/`, and `ci/` | 0 |
| `gitleaks detect` on `git archive HEAD` | 0 |
| `npm ci` and Playwright Chromium install in `ci/` | 0 |
| `docker build --tag mosscms:smoke .` | 0 |
| production Compose up, `npm test`, down | 0 |

No runtime skip and no xfail. Counts: [counts.txt](59e34ac/counts.txt).
