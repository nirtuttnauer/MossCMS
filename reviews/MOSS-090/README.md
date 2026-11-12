# MOSS-090 sign-in errors

local

Recorded 12 November 2026 (UTC). The sign-in form shows the API sentence for an unknown email and for a wrong password, and a Hebrew email can be submitted.

## Code under test

| | |
| --- | --- |
| SHA tested | `09b7dc9b995ad5f40461aa455b2fe28e60a6ff2d` |
| Branch | `cursor/moss-090-signin-errors-9580` |
| Comparison base | `b6c6687` |
| Branch parent | `5ea1d03` (main; workflow files differ from `b6c6687`) |
| `git status --porcelain` at the start of `scripts/verify.sh` | empty |
| Date | 2026-11-12T14:56:46Z through 2026-11-12T15:08:55Z |
| Label | local |

`git diff b6c6687 -- web` is `web/src/pages/Auth.tsx` and `web/src/pages/Auth.test.tsx`. No API test file differs from `b6c6687`.

## Sign-in behavior

On the sign-in form, a 401 whose API message is `Invalid email or password.` is rendered as that sentence. The code and request id are not appended. An unknown email and a wrong password therefore show the same alert when the API returns that sentence.

The sign-in email field uses `type="text"` and `inputMode="email"`, so a Hebrew address is submitted. Setup, invitation, and recovery keep `type="email"`. A Hebrew value the API rejects is shown as that API error. `api/app/accounts.py`, `api/app/oauth.py`, and `api/app/cli.py` were not edited.

Browser check on the local Vite dev server proxied to the API: a known email with a wrong password, an unregistered email, and `משתמש@דוגמה.קום` each showed the alert `Invalid email or password.` Submitting `משתמש@דוגמה` showed `Enter a valid email address.` with the validation code and request id, and the form stayed on the sign-in page. The console recorded the HTTP status for those responses and no uncaught exception.

## Commands

`scripts/verify.sh MOSS-090` started on a clean tree at `09b7dc9` and exited 1 at `pytest-sqlite`.

The failing id is `tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests`. The assertion text is `starters/nextjs/package.json (npm /starters/nextjs) is not covered by .github/dependabot.yml`. `git diff b6c6687 HEAD` for `.github/dependabot.yml`, `starters/nextjs/package.json`, and `api/tests/test_dependabot.py` is empty, so the same assertion fails at `b6c6687`. Those files were not edited.

Before the recorded SQLite run, `iptables-legacy` FORWARD policy was DROP, which blocked container-to-container traffic. It was set to ACCEPT on this host. The SQLite log in this folder is from `scripts/verify.sh` after that host change. The private-admin Compose test passed in that run.

The script stops on the SQLite failure, so the later commands from `scripts/verify.sh` were run with the same environment and written into [09b7dc9](09b7dc9/). `pip-audit` was run again after `python3.12-venv` was installed; the saved log is that rerun and its exit code is 0.

| Command | Exit | Result |
| --- | --- | --- |
| `uv sync --locked --group dev` | 0 | locked dependencies installed |
| ruff check and format | 0 | passed |
| ruff scripts | 0 | passed |
| `mypy app` | 0 | passed |
| SQLite `pytest -m "not postgres"` | 1 | 497 passed, 4 deselected, 1 failed, 0 skipped |
| PostgreSQL `pytest` | 1 | 501 passed, 1 failed, 0 skipped |
| `tests/verify_required_runs.py` | 1 | the dependabot id did not pass in either run |
| OTLP collector smoke | 0 | passed |
| web `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 | 36 files, 358 passed, 0 skipped |
| example-site check, test, build, high audit | 0 | 50 passed, 0 failed, 0 skipped |
| `pip-audit` 2.10.1 | 0 | No known vulnerabilities found |
| `npm audit` web, example-site, ci | 0 | passed |
| gitleaks on `git archive HEAD` | 0 | no leaks found |
| production image, compose, Playwright, teardown | 0 | 2 passed |

The SQLite and PostgreSQL failure is the same dependabot id. The four SQLite deselections also pass on PostgreSQL:

- `tests/test_concurrency.py::test_postgres_workers_skip_locked_rows_and_claim_once`
- `tests/test_indexing.py::test_common_string_count_avoids_per_match_probes_in_generic_postgres_plan`
- `tests/test_postgres_product_migration.py::test_postgres_0009_preserves_localized_live_scheduled_and_revision_data`
- `tests/test_search.py::test_generic_postgres_substring_plan_uses_trigrams_and_rechecks_matches`

No new skip, xfail, or audit ignore was added.

Web at `b6c6687` is 356 tests. This branch adds 2 sign-in tests, and the run here is 358. API collection is 502 here and at `b6c6687`, because no API test file changed. Example-site remains 50 passed.

Counts: [counts.json](09b7dc9/counts.json). Exit codes: [exit-codes.txt](09b7dc9/exit-codes.txt).
