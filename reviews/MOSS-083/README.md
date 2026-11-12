# MOSS-083 local verification

label: local

| | |
| --- | --- |
| Named main | `b6c66870b98af990ee91766e5a965e823bf2b03d` |
| PR base | `5ea1d037bb85e47c2efc1d97f72998d130130878` |
| Verified tree | `4ae0c83b1ef41c911701518adaa82d6de219eee5` |
| Clean status | `reviews/MOSS-083/4ae0c83/summary.txt` records an empty `git status --porcelain` when `scripts/verify.sh MOSS-083` started |
| Started | 2026-11-12T15:01:08Z |

`b6c6687..5ea1d03` changes `.github/workflows/checks.yml` and `.github/workflows/docker.yml` action pins. API, web, and example-site files are the same in those two commits. Counts below were measured on `5ea1d03`.

`scripts/verify.sh MOSS-083` was run on `4ae0c83` from a clean tree and exited 1 at `pytest-sqlite`. The failed test is `tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests`: `starters/nextjs/package.json` is not covered by `.github/dependabot.yml`. The same assertion fails on `5ea1d03` (`reviews/MOSS-083/5ea1d03/pytest-sqlite.txt`). Those files were not edited.

The commands after `pytest-sqlite` were run with the same logging and are in `reviews/MOSS-083/4ae0c83/`. `pytest-postgres` in that directory is the rerun with `MOSS_USE_SQLITE=false`, which is what `scripts/verify.sh` exports. `pip-audit` in that directory is the rerun after `python3.12-venv` was installed; the earlier attempt exited because `ensurepip` was missing, not because an advisory was reported.

## Counts

| Suite | Main `5ea1d03` | Verified tree `4ae0c83` |
| --- | --- | --- |
| API pytest, SQLite, `-m "not postgres"` | 1 failed, 497 passed, 4 deselected, 0 skipped | 1 failed, 504 passed, 4 deselected, 0 skipped |
| API pytest, PostgreSQL | 1 failed, 501 passed, 0 skipped | 1 failed, 508 passed, 0 skipped |
| Admin web vitest | 36 files, 356 passed, 0 skipped | 36 files, 356 passed, 0 skipped |
| Example site `node --test` | 50 pass, 0 fail, 0 skipped | 50 pass, 0 fail, 0 skipped |
| Production Playwright | not run on the base in this session | 2 passed |

The API delta is the seven tests in `api/tests/test_development.py`. The failed test is the dependabot coverage check on both trees. The 4 deselected ids are the PostgreSQL-marked tests excluded by `-m "not postgres"`, on both trees. Web and example-site counts match; those trees are unchanged.

`uv.lock` is unchanged from `5ea1d03`. `pip-audit` exit 0, `No known vulnerabilities found`. `npm audit` in `web/`, `example-site/`, and `ci/` exited 0 with `found 0 vulnerabilities`. `gitleaks detect` on `git archive HEAD` exited 0.

## Commands

Base (`5ea1d03`, label local, 2026-11-12):

- `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest -m "not postgres"` in `api/` — exit 1
- `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=postgres MOSS_TEST_DATABASE_URL=postgresql+psycopg://pg:pgtestpw@127.0.0.1:5432/postgres uv run pytest` in `api/` — exit 1
- `npm test` in `web/` — exit 0
- `npm test` in `example-site/` — exit 0

Logs: `reviews/MOSS-083/5ea1d03/`.

Head (`4ae0c83`): `scripts/verify.sh MOSS-083` from a clean tree, then the remaining script commands. Exit codes: `reviews/MOSS-083/4ae0c83/exit-codes.txt`. Counts: `reviews/MOSS-083/4ae0c83/counts.txt`.

Host note: `iptables-legacy` policy for `FORWARD` was `DROP`. It was set to `ACCEPT` before the recorded API reruns and the production compose test. That is a VM firewall adjustment, not a repository change.
