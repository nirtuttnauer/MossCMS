# MOSS-079 Hebrew preview grant

local

Recorded 12 November 2026 (UTC). `scripts/verify.sh MOSS-079` started at `d6aaae74a118426cd93f33434791c414a1e2099d` with an empty `git status --porcelain`. It exited 1 at `pytest-sqlite`. The same Dependabot test fails on base `b6c6687`. The remaining commands from `scripts/verify.sh` were run afterward and are logged under [d6aaae7](d6aaae7/).

## Code under test

| | |
| --- | --- |
| Ticket base | `b6c66870b98af990ee91766e5a965e823bf2b03d` |
| Branch parent | `5ea1d037bb85e47c2efc1d97f72998d130130878` |
| SHA tested | `d6aaae74a118426cd93f33434791c414a1e2099d` |
| `git status --porcelain` at the start of `scripts/verify.sh` | empty |
| Started | 2026-11-12T14:51:03Z |
| Python / uv | 3.12.3 / 0.13.7 |
| ruff / mypy / pip-audit | 0.16.10 / 2.4.0 / 2.10.1 |
| Node / npm | v22.23.4 / 10.9.9 |
| Docker / Compose | 29.1.3 / 2.40.3 |
| gitleaks | 8.30.1 |

`git diff b6c6687 5ea1d03 -- api web example-site scripts ci starters .github/dependabot.yml` is empty. The parent commit updates GitHub Actions pins. This branch adds `api/tests/test_preview.py` and these review logs. `api/app/preview.py` is unchanged: redemption already returned the saved public title and body.

## What the new test checks

`test_hebrew_niqqud_draft_round_trips_on_redemption_and_stays_off_delivery` saves a draft whose title and body contain Hebrew niqqud in an order NFC would reorder. After a later save, `POST /api/preview/redeem` returns that frozen title and body, the same code points, with the private field removed. A delivery token does not receive that draft from delivery GraphQL (entry, search, list, revisions) or from delivery REST (entry, list search, resolved assets). Request logs for `mosscms` include `/api/preview/redeem` and do not include the grant token or the delivery secret.

## Commands

`scripts/verify.sh MOSS-079` ran the steps through `pytest-sqlite` and stopped. The continuation used the same commands as `scripts/verify.sh` from the PostgreSQL container onward. No new skips, xfails, audit ignores, or allowlists. The four PostgreSQL-only tests are deselected on SQLite by `-m "not postgres"`, the same marker exclusion as on `b6c6687`. Runtime skips: 0.

Base comparison, detached `b6c6687`:

```sh
MOSS_USE_SQLITE=false uv run pytest tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests -q --tb=short
uv run pytest --collect-only -q
```

## Results

| Command | Exit | Result |
| --- | --- | --- |
| `uv sync --locked --group dev` | 0 | locked install |
| ruff check and format | 0 | app, tests, migrations, scripts |
| `uv run mypy app` | 0 | no issues |
| SQLite `uv run pytest -m "not postgres"` | 1 | 498 passed, 1 failed, 4 deselected, 0 skipped. Failure: `test_dependabot_config_matches_schema_and_covers_manifests` |
| PostgreSQL `uv run pytest` | 1 | 502 passed, 1 failed, 0 deselected, 0 skipped. Same Dependabot failure |
| `tests/verify_required_runs.py` | 1 | the Dependabot test is the collected id that did not pass |
| OpenTelemetry smoke | 0 | collector smoke completed |
| `web` check, test, build, `npm audit --audit-level=high` | 0 | 36 files, 356 tests passed, 0 skipped |
| `example-site` check, test, build, `npm audit --audit-level=high` | 0 | 50 passed, 0 failed, 0 skipped |
| `pip-audit` 2.10.1 | 0 | No known vulnerabilities found |
| `npm audit` for web, example-site, and ci | 0 | found 0 vulnerabilities |
| gitleaks 8.30.1 on `git archive HEAD` | 0 | no leaks found |
| production image, compose, `ci` `npm test` | 0 | 2 passed, 0 skipped |

### Counts against `b6c6687`

| | `b6c6687` | `d6aaae7` |
| --- | --- | --- |
| API collected | 502 (`--collect-only`) | 503 |
| SQLite passed / failed / deselected / skipped | 502 collected. The Dependabot test failed when run on this checkout. A full SQLite pass count was not re-recorded after an overlapping Compose run. | 498 passed, 1 failed, 4 deselected, 0 skipped |
| PostgreSQL passed / failed / deselected / skipped | same Dependabot failure on this tree. Product tests are unchanged aside from the added preview test. | 502 passed, 1 failed, 0 deselected, 0 skipped |
| Web | sources unchanged from `b6c6687` | 356 passed, 0 skipped |
| Example site | sources unchanged from `b6c6687` | 50 passed, 0 skipped |

The added test is `test_hebrew_niqqud_draft_round_trips_on_redemption_and_stays_off_delivery`. It passed on SQLite and PostgreSQL. The Dependabot failure is `starters/nextjs/package.json (npm /starters/nextjs) is not covered by .github/dependabot.yml`. Log on the base checkout: [base-b6c6687/dependabot.txt](base-b6c6687/dependabot.txt). This ticket does not edit `.github/dependabot.yml` or `starters/nextjs/`.

`pip-audit` was rerun after `python3.12-venv` was installed on the machine. The successful log is [d6aaae7/pip-audit.txt](d6aaae7/pip-audit.txt). Two earlier exit lines in `exit-codes.txt` are that missing package, not a vulnerability finding.
