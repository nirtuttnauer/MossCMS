# MOSS-091 local verification

label: local

| | |
| --- | --- |
| Base | `5ea1d037bb85e47c2efc1d97f72998d130130878` (`main`) |
| Verified tree | `673cdb1e3a18206de39e9b1ce468247c57528661` |
| Clean status | [673cdb1/summary.txt](673cdb1/summary.txt) records an empty `git status --porcelain` when `scripts/verify.sh MOSS-091` started |
| Started | 2026-11-12T15:59:46Z |
| Finished | 2026-11-12T16:16:00Z |

`scripts/verify.sh MOSS-091` was run on that verified tree and exited 1 at `pytest-sqlite`. The failed test is `test_dependabot_config_matches_schema_and_covers_manifests`: `starters/nextjs/package.json` is not covered by `.github/dependabot.yml`. The same test fails on main `5ea1d03` ([5ea1d03/pytest-sqlite.txt](5ea1d03/pytest-sqlite.txt), [5ea1d03/pytest-postgres.txt](5ea1d03/pytest-postgres.txt)). `.github/dependabot.yml` was not edited. That failure belongs to open MOSS-063 #49.

The script stops at the failed step, so the later commands were run with the same arguments and logged in [673cdb1](673cdb1/). Exit codes are in [673cdb1/exit-codes.txt](673cdb1/exit-codes.txt). Skip scans reported no runtime skip or xfail.

`tests/verify_required_runs.py` exits 1 on this tree and on main because that dependabot test is the id missing from both required runs ([673cdb1/verify-required-runs.txt](673cdb1/verify-required-runs.txt), [5ea1d03/verify-required-runs.txt](5ea1d03/verify-required-runs.txt)).

The evidence files were committed after the run, so the pull request head is the evidence commit. Counts below are for `673cdb1`.

## Counts

| Suite | Base `5ea1d03` | Verified tree `673cdb1` |
| --- | --- | --- |
| API pytest, SQLite, `-m "not postgres"` | 497 passed, 1 failed, 4 deselected, 0 skipped | 533 passed, 1 failed, 4 deselected, 0 skipped |
| API pytest, PostgreSQL | 501 passed, 1 failed, 0 skipped | 537 passed, 1 failed, 0 skipped |
| Admin web vitest | 36 files, 356 passed, 0 skipped | 36 files, 356 passed, 0 skipped |
| Example site `node --test` | 50 pass, 0 fail, 0 skipped | 50 pass, 0 fail, 0 skipped |
| Production Playwright | not re-run on the base in this session | 2 passed, 0 skipped |

The API delta is the 36 tests in `api/tests/test_security_validators.py`. Web and example-site counts match; those trees are unchanged from the base. The failed test on both API runs is the dependabot manifest check. The four ids deselected on SQLite are the PostgreSQL-marked tests in `api/tests/required_runs.json`, the same four deselected on main.

## What the tests lock

`password_hash` accepts strings of length 12, 64, and 128, and an 80-character Unicode password whose UTF-8 form is longer than 128 bytes. It rejects length 11, empty, length 129, and non-strings (`None`, `int`, `bytes`, `list`).

`check_password` accepts a matching `scrypt$salt$hash`, including a second encoding of the same password. It rejects a truncated digest, a stored value with the salt and digest exchanged, another password's hash, a `bcrypt$` label in front of a real scrypt salt and digest, and a non-scrypt literal.

`valid_email` accepts `editor@example.com`, a stripped and lowercased address, `שלום@example.com` (including a mixed-case domain), and a 254-character address. It rejects empty and whitespace-only values, a 255-character address, a missing `@`, a domain without a dot, a newline or carriage return, and more than one `@`.

Before the `security.py` edit, an embedded newline, a trailing newline, a carriage return, and a second `@` were accepted, and `check_password` returned true for a non-scrypt label copied onto a real scrypt salt and digest. Those cases were red, then `api/app/security.py` was updated. `api/app/accounts.py` and `web/src/pages/Auth.tsx` were not edited.

A later temporary edit that changes the password lower bound from 12 to 11 fails `test_password_hash_rejects_short_long_and_non_strings[11-chars]`. Removing the line-break rejection fails the newline, CRLF, and carriage-return cases. The file was restored afterward ([673cdb1/mutations.txt](673cdb1/mutations.txt)).

## Commands

Base commands (2026-11-12, label local), from a checkout of `5ea1d03` at `/tmp/moss-base`:

- `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest -m "not postgres"` in `api/` — exit 1, 497 passed, 1 failed, 4 deselected
- `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=postgres` with the PostgreSQL URL from `scripts/verify.sh`, `uv run pytest` in `api/` — exit 1, 501 passed, 1 failed
- `npm test` in `web/` — exit 0
- `npm test` in `example-site/` — exit 0
- `uv run python tests/verify_required_runs.py` in `api/` — exit 1, same dependabot id

An earlier SQLite run on that checkout also failed `test_variant_a_proxy_and_variant_b_private_listener` with `curl: (28)` while `iptables-legacy` FORWARD policy was DROP. After `iptables-legacy -P FORWARD ACCEPT`, the SQLite retry, the PostgreSQL run, and the head production stack did not show that timeout. That policy change is not in the repository.

Head commands, label local, tree `673cdb1`:

- `scripts/verify.sh MOSS-091` — exit 1 at `pytest-sqlite` (533 passed, 1 failed, 4 deselected). Earlier steps `uv sync --locked --group dev`, ruff, ruff on scripts, and `mypy app` exited 0.
- Remaining script commands, logged beside that output: PostgreSQL pytest (537 passed, 1 failed, skip scan exit 0), `tests/verify_required_runs.py` (exit 1, dependabot id), OpenTelemetry smoke (exit 0), web and example-site `npm ci` plus `npm run check && npm test && npm run build && npm audit --audit-level=high` (exit 0), `pip-audit` on the frozen export (exit 0), `npm audit` in `web/`, `example-site/`, and `ci/` (exit 0, `found 0 vulnerabilities`), `gitleaks detect` on `git archive HEAD` (exit 0, no leaks found), `npm ci` and `npx playwright install --with-deps chromium` in `ci/` (exit 0), `docker build --tag mosscms:smoke .` (exit 0), compose up, `npm test` in `ci/` (2 passed), compose down (exit 0).
