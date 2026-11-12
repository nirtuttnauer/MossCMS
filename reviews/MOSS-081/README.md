# MOSS-081 local verification

label: local

Content transform steps stay on the documented operations `rename`, `default`, `drop`, and `convert`. Default values have to be plain JSON. A step shaped like `eval`, `exec`, `import`, `__import__`, a dotted module call, or a callable payload is rejected before the input is copied or changed.

Before that validation change, the new tests reported 12 failures. Callable defaults, modules, code objects, objects with a copy hook, and list or dict subclasses were accepted. After the change, those tests pass, and a rejected step leaves the caller's data and change log untouched.

`api/app/portability.py` was not edited.

## SHAs

| | |
| --- | --- |
| Named base | `b6c66870b98af990ee91766e5a965e823bf2b03d` |
| `origin/main` when this branch was created | `5ea1d037bb85e47c2efc1d97f72998d130130878` |
| Code tested | `63fe58dabba377c142847f5fbc435400ed24ec46` |
| Clean status at `scripts/verify.sh` start | empty `git status --porcelain` (`reviews/MOSS-081/63fe58d/summary.txt`) |
| Started | 2026-11-12T14:44:07Z |

`5ea1d03` is `b6c6687` plus `.github/workflows` pin updates. The API, web, and example-site trees match between those two commits. Baseline commands below were run on `b6c6687`.

## Commands

`scripts/verify.sh MOSS-081` from a clean tree at `63fe58d`. Exit 1 at `pytest-sqlite`.

The failure is `tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests`: `starters/nextjs/package.json` is not covered by `.github/dependabot.yml`. The same assertion fails on `b6c6687` (`reviews/MOSS-081/b6c6687/pytest-sqlite.txt`). Those files are outside this ticket. No skip, xfail, allowlist, or audit ignore was added.

The remaining `scripts/verify.sh` commands were run afterward and logged under `reviews/MOSS-081/63fe58d/`. Exit codes are in `exit-codes.txt`.

An overlapping baseline run used the same Compose project name, so the head PostgreSQL run also failed `test_variant_a_proxy_and_variant_b_private_listener`. That log was replaced by an isolated rerun. The isolated rerun's only failure is the Dependabot test above: 1 failed, 532 passed, 0 skipped.

`pip-audit` exited 1 in the continuation because `EVIDENCE` was unset in that shell. A second attempt exited 1 because `python3.12-venv` was not installed. After that package was installed on the machine, the same audit command exited 0: `No known vulnerabilities found`. `api/uv.lock` is unchanged from `b6c6687`.

## Counts

| Suite | `b6c6687` | `63fe58d` |
| --- | --- | --- |
| API pytest, SQLite, `-m "not postgres"` | 497 passed, 1 failed, 4 deselected, 0 skipped | 528 passed, 1 failed, 4 deselected, 0 skipped |
| API pytest, PostgreSQL | 501 passed, 1 failed, 0 skipped | 532 passed, 1 failed, 0 skipped |
| Admin web vitest | tree matches `b6c6687` | 36 files, 356 passed, 0 skipped |
| Example site `node --test` | tree matches `b6c6687` | 50 pass, 0 fail, 0 skipped |
| Production Playwright | not re-run on the base | 2 passed, 0 skipped |

The API delta is 31 passing tests in `api/tests/test_transforms.py`. The failed id on both SHAs is the Dependabot coverage test. Web and example-site files are unchanged from `b6c6687`.

The four ids deselected on SQLite are the committed list in `api/tests/required_runs.json`: `test_postgres_workers_skip_locked_rows_and_claim_once`, `test_common_string_count_avoids_per_match_probes_in_generic_postgres_plan`, `test_postgres_0009_preserves_localized_live_scheduled_and_revision_data`, and `test_generic_postgres_substring_plan_uses_trigrams_and_rechecks_matches`. They passed in the PostgreSQL runs on both SHAs. No xfail.

`tests/verify_required_runs.py` exits 1 on `63fe58d` because the Dependabot test did not pass. The deselected ids match the committed list.

## Other local results at `63fe58d`

| Command | Exit |
| --- | --- |
| `uv sync --locked --group dev` | 0 |
| ruff check and format | 0 |
| ruff on scripts | 0 |
| `uv run mypy app` | 0 |
| OpenTelemetry smoke | 0 |
| web `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 |
| example-site `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 |
| `npm audit` in `web/`, `example-site/`, and `ci/` | 0, `found 0 vulnerabilities` |
| `gitleaks detect` on `git archive HEAD` | 0, no leaks found |
| `ci/` `npm ci` and Playwright install | 0 |
| `docker build --tag mosscms:smoke .` | 0 |
| Compose up, `npm test` in `ci/`, Compose down | 0, 2 passed |
| `pip-audit` rerun | 0 |

Tools: Python 3.12.3, uv 0.13.7, ruff 0.16.10, mypy 2.4.0, Node v22.23.4, npm 10.9.9, Docker 29.1.3, Compose 2.40.3, gitleaks 8.30.1, pip-audit 2.10.1, PostgreSQL 17 Alpine. Host `iptables-legacy` FORWARD policy was set to ACCEPT before the run so the Compose bridge was reachable. That change is not in the repository.
