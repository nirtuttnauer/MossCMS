# MOSS-078 local verification

label: local

| | |
| --- | --- |
| Comparison base | `b6c66870b98af990ee91766e5a965e823bf2b03d` |
| `origin/main` when the branch was updated | `5ea1d037bb85e47c2efc1d97f72998d130130878` (github-actions bump #26; no API, web, or example-site test changes) |
| Code under test | `38f230dc0be4fe0d22e76a1acf535365df9f4fc9` |
| Earlier code commit | `f7bead783772ed388c09ff0a1d65dddfab54d577` (same test, before a placeholder rename) |
| Clean status | `reviews/MOSS-078/f7bead7/summary.txt` and `reviews/MOSS-078/38f230d/meta.txt` record an empty `git status --porcelain` at the start of each run |
| Head run window | 2026-11-12T14:51:54Z through 2026-11-12T15:03:30Z |

`api/app/portability.py` is unchanged. `_redact` was left as it is: the new test plants a password hash, a session row, an invitation row, and the raw bearer strings, then reads the zip, including an export with private fields included. Those values are absent, and the localized private field next to the Hebrew body is absent from the default archive.

`api/uv.lock` is unchanged from `b6c6687`.

The separate ticket file `MOSS-078.md` was not in the upload and is not in the repo or in GitHub issues. The checks below follow the prompt.

## What the new test locks

`test_hebrew_niqqud_round_trip_stays_draft_and_omits_auth_secrets` in `api/tests/test_portability.py`:

- Hebrew titles and bodies that include niqqud survive export and import as written, or as NFC.
- The destination row stays `draft`. Published and scheduled columns stay empty, and the destination has no published row. The source row stays published. Source publication text remains on the import revision.
- The archive does not contain the planted password hash, session row, invitation row, or raw bearer strings.

Slugify and content save were not edited.

## Counts

| Suite | Base `b6c6687` | Head `38f230d` |
| --- | --- | --- |
| API pytest, SQLite, `-m "not postgres"` | 496 passed, 2 failed, 4 deselected | 498 passed, 1 failed, 4 deselected |
| API pytest, PostgreSQL | 500 passed, 2 failed | 502 passed, 1 failed |
| Admin web vitest | 36 files, 356 passed | 36 files, 356 passed |
| Example site `node --test` | not re-run; `example-site/` matches `b6c6687` | 50 pass, 0 fail |
| Production Playwright | not re-run on the base in this session | 2 passed |

The API delta is the new portability test. Web counts match. The 4 PostgreSQL-marked tests are deselected on SQLite on both trees and are part of the PostgreSQL passed totals.

### Failures that also happen on `b6c6687`

`tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests` fails on `b6c6687` and on `38f230d`. The message says `starters/nextjs/package.json` is not covered by `.github/dependabot.yml`. Those files are outside this ticket, so they were not edited. `tests/verify_required_runs.py` then exits 1 because that test did not pass. Log: [verify-required-runs.txt](38f230d/verify-required-runs.txt).

`tests/test_private_admin_compose.py` failed in the overlapping `b6c6687` runs. SQLite hit a container-name clash because two suites used project `moss059` at the same time. PostgreSQL later reached the proxy and `curl` timed out while `iptables-legacy` policy `FORWARD` was `DROP`. After `iptables-legacy -P FORWARD ACCEPT`, the same test on `b6c6687` passed (1 passed). Log: [compose-rerun.txt](b6c6687/compose-rerun.txt). The head SQLite and PostgreSQL runs after that change do not fail this test.

## Commands

Base `b6c6687`, label local, 2026-11-12T14:43:06Z, empty `git status --porcelain` in the worktree. Logs: `reviews/MOSS-078/b6c6687/`.

- `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest -m "not postgres"` in `api/` — exit 1 (496 passed, 2 failed, 4 deselected)
- `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=postgres MOSS_TEST_DATABASE_URL=postgresql+psycopg://pg:pgtestpw@localhost:5433/postgres uv run pytest` in `api/` — exit 1 (500 passed, 2 failed)
- `npm ci && npm test` in `web/` — exit 0 (36 files, 356 passed)
- `uv run pytest tests/test_private_admin_compose.py` in `api/` — exit 0 on the rerun after the firewall change

`scripts/verify.sh MOSS-078` on `f7bead7`, label local, started 2026-11-12T14:43:06Z from a clean tree. It exited 1 at `pytest-sqlite` for the dependabot failure and the overlapping compose project. Ruff, ruff on scripts, and mypy exited 0. The steps after that were run with the same commands and logged under [f7bead7](f7bead7/):

- `npm ci`, then `npm run check && npm test && npm run build && npm audit --audit-level=high` in `web/` — exit 0
- the same in `example-site/` — exit 0 (50 pass, 0 fail)
- `npm audit` in `web/`, `example-site/`, and `ci/` — exit 0, `found 0 vulnerabilities`
- `npm ci` in `ci/` — exit 0

That `f7bead7` gitleaks run found a generic key pattern on the invitation placeholder. `38f230d` renames the placeholder. `gitleaks detect` on `git archive HEAD` at `38f230d` exited 0. Log: [gitleaks.txt](38f230d/gitleaks.txt).

Head `38f230d`, label local, 2026-11-12T14:51:54Z, empty `git status --porcelain`. Logs: `reviews/MOSS-078/38f230d/`.

- `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest -m "not postgres"` — exit 1 (498 passed, 1 failed, 4 deselected)
- `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=postgres MOSS_TEST_DATABASE_URL=postgresql+psycopg://pg:pgtestpw@localhost:5432/postgres uv run pytest` — exit 1 (502 passed, 1 failed)
- `uv run python tests/verify_required_runs.py` — exit 1, same dependabot id
- OpenTelemetry smoke — exit 0
- `uv run --with pip-audit pip-audit --progress-spinner off -r requirements.txt` — the earlier attempt exited 1 before the audit because `python3-venv` / ensurepip was missing. After `python3.12-venv` was installed, the same audit exited 0, `No known vulnerabilities found`. Log: [pip-audit.txt](38f230d/pip-audit.txt). `exit-codes.txt` keeps `pip-audit 1` for the earlier attempt and `pip-audit-rerun 0` for this result.
- `npx playwright install --with-deps chromium` in `ci/` — exit 0
- `docker build --tag mosscms:smoke .` — exit 0
- `docker compose -f ci/compose.yaml -p mosscms-smoke up --no-build -d --wait --wait-timeout 180` — exit 0
- `npm test` in `ci/` — exit 0 (2 passed)
- `docker compose -f ci/compose.yaml -p mosscms-smoke down --volumes` — exit 0

`f7bead7` and `38f230d` differ by the placeholder rename. Web, example-site, ruff, and mypy were not re-run on `38f230d` because those trees are the same.
