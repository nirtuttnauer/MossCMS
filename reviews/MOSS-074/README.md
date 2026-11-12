# MOSS-074 local verification

label: local

Background autosave stores a draft. A Hebrew title is sent on `saveDraft`. A lost response is checked with `draftReceipt`. The requests do not carry `status` `published` or `scheduled`, and they do not call `saveEntry`. `web/src/lib/autosave.ts` needed no edit. The new cases are in `web/src/lib/autosave.test.tsx`.

## SHAs

| | |
| --- | --- |
| SHA named by the ticket | `b6c66870b98af990ee91766e5a965e823bf2b03d` |
| Latest `main` at branch time | `5ea1d037bb85e47c2efc1d97f72998d130130878` |
| Tree `scripts/verify.sh` ran on | `9e5a1ef2e6203be745a97c347537860d9d40d450` |
| `git status --porcelain` at the start of that run | empty |
| Started | 2026-11-12T14:42:47Z |
| Later steps finished | 2026-11-12T14:58:13Z |

`git diff --stat b6c66870b98af990ee91766e5a965e823bf2b03d 5ea1d037bb85e47c2efc1d97f72998d130130878` is `.github/workflows/checks.yml` and `.github/workflows/docker.yml`. `git diff b6c66870b98af990ee91766e5a965e823bf2b03d 9e5a1ef2e6203be745a97c347537860d9d40d450 -- api` is empty (`base-5ea1d03/api-diff-vs-b6c6687.txt`). The review files in this directory were committed after that run, so the pull request head adds this log and does not change the code under test.

## Commands

`scripts/verify.sh MOSS-074` on the clean tree `9e5a1ef`. Exit 1 at `pytest-sqlite`. The failing test is `tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests`. The same assertion fails on main `5ea1d03`:

- `python3 scripts/check_dependabot.py` — exit 1. Output: `starters/nextjs/package.json (npm /starters/nextjs) is not covered by .github/dependabot.yml`. Log: `base-5ea1d03/dependabot-check.txt`.
- In `api/`, `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests -q` — exit 1. Log: `base-5ea1d03/dependabot-pytest.txt`.

Those files are outside this ticket (` .github/dependabot.yml` is MOSS-063, `starters/nextjs/` is MOSS-036). No test was skipped, xfailed, deleted, or weakened, and no audit ignore was added.

`scripts/verify.sh` stops on that failure. The later commands from the script were run locally with the same work directories and the same command text. Exit codes are in `9e5a1ef/exit-codes.txt`.

`pip-audit` exited 1 before any advisory check because this machine had no `python3.12-venv` (`9e5a1ef/pip-audit.txt`). After `apt install python3.12-venv`, the same audit exited 0 with `No known vulnerabilities found` (`9e5a1ef/pip-audit-retry.txt`). The lockfile was not changed.

## Counts

| Suite | main `5ea1d03` (API and prior web sources match `b6c6687`) | `9e5a1ef` |
| --- | --- | --- |
| API pytest, SQLite, `-m "not postgres"` | API tree matches the head run | 497 passed, 1 failed, 4 deselected, 0 skipped |
| API pytest, PostgreSQL | API tree matches the head run | 501 passed, 1 failed, 0 deselected, 0 skipped |
| Admin web vitest | 36 files, 356 passed, 0 skipped (`base-5ea1d03/web-test.txt`, `npm test`, exit 0) | 36 files, 359 passed, 0 skipped |
| Example site `node --test` | sources match the head run | 50 pass, 0 fail, 0 skipped |
| Production Playwright | | 2 passed, 0 skipped |

The web delta is the three new autosave cases. The API failure on the head run is the Dependabot coverage test that also fails on main. The four PostgreSQL-marked tests are deselected on SQLite and executed on PostgreSQL. Neither required run reports a runtime skip or xfail.

Other head steps, all exit 0: `uv sync --locked --group dev`, ruff, ruff on scripts, mypy, OpenTelemetry smoke, web and example-site `npm ci` plus `npm run check && npm test && npm run build && npm audit --audit-level=high`, `npm audit` in `web/`, `example-site/`, and `ci/` (`found 0 vulnerabilities`), `gitleaks detect` on `git archive HEAD`, `npm ci` and `npx playwright install --with-deps chromium` in `ci/`, `docker build --tag mosscms:smoke .`, compose up, `npm test` in `ci/`, compose down.

`tests/verify_required_runs.py` exited 1 because the Dependabot test failed in both required runs. Log: `9e5a1ef/verify-required-runs.txt`.

## What the new tests check

- A background save of `כותרת טיוטה` on an entry whose current status is `published`, and the same save on an entry whose current status is `scheduled`, calls `saveDraftMutation` with that title. The variables have no `status` and no `scheduledAt`. The document is not `saveEntryMutation`.
- A lost background save of `שמירה לא מאושרת` calls `saveDraft` and then `draftReceipt` with that request key. It does not call `saveEntry`.
