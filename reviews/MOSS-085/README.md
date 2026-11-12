# MOSS-085 library image alternative text

label: local

The asset picker warns and waits for confirmation before inserting a library image when alternative text is missing. Hebrew alternative text is accepted and the image is inserted without that warning. Markdown insert already requires alternative text, so that path is unchanged. Publishing stays available. `SeoEntryPanel` and the media upload modules were not edited.

## Behavior checked

- A library image with no alternative text field opens a dialog titled "Add alternative text before you insert this image". The dialog says the picker flags common accessibility problems before you publish. The image is not inserted until "Insert without alternative text" is confirmed. Go back and Escape leave the field unchanged.
- Hebrew alternative text is accepted, including surrounding whitespace, a required `alt *` label, and a localized `alt` field that has Hebrew in one locale.
- Alternative text on a different field in the entry form is not treated as this image's text.
- The Markdown control labeled "Image alt text", next to "Insert image", still selects a library image immediately.
- A non-image library file does not warn. An image chosen from a mixed library does.
- Confirmation still inserts the image, so this change does not block publish.

## Verification

| | |
| --- | --- |
| Ticket base | `b6c66870b98af990ee91766e5a965e823bf2b03d` |
| Branch base | `5ea1d037bb85e47c2efc1d97f72998d130130878` (`origin/main`). `web/`, `api/`, and `example-site/` match `b6c6687`. |
| Verified tree | `4d717424ae5ac14fc26a3ae5e42b0532b118687f` |
| Clean status | [summary.txt](4d71742/summary.txt) records an empty `git status --porcelain` when `scripts/verify.sh MOSS-085` started |
| Started | 2026-11-12T14:51:08Z |
| Continuation finished | 2026-11-12T15:11:09Z |

`scripts/verify.sh MOSS-085` exited 1 at `pytest-sqlite`. The failure is `tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests` (`starters/nextjs/package.json` is not covered by `.github/dependabot.yml`). The same SQLite command on `b6c6687` fails that assertion and no other: 1 failed, 497 passed, 4 deselected, 0 skipped ([pytest-sqlite.txt](b6c6687/pytest-sqlite.txt)). The verified tree is the same 1 failed, 497 passed, 4 deselected, 0 skipped. No new skip or xfail. This ticket does not edit `.github/dependabot.yml` or `starters/nextjs/` (MOSS-063).

The rest of `scripts/verify.sh` was run with the same commands and logged in [4d71742/](4d71742/). Exit codes are in [exit-codes.txt](4d71742/exit-codes.txt).

## Counts

| Suite | Base `b6c6687` | Verified tree `4d71742` |
| --- | --- | --- |
| API pytest, SQLite, `-m "not postgres"` | 497 passed, 1 failed, 4 deselected, 0 skipped | 497 passed, 1 failed, 4 deselected, 0 skipped |
| API pytest, PostgreSQL | same API tree as the verified run; the SQLite deselection list is the four PostgreSQL-only tests | 501 passed, 1 failed, 0 skipped |
| Admin web vitest | 36 files, 356 passed, 0 skipped | 36 files, 364 passed, 0 skipped |
| Example site `node --test` | 50 pass, 0 fail, 0 skipped | 50 pass, 0 fail, 0 skipped |
| Production Playwright | not re-run on the base in this session | 2 passed, 0 skipped |

The web difference is the eight asset-picker cases. API and example-site sources are unchanged from `b6c6687`, and the API failure is the Dependabot test above. On PostgreSQL that test fails and the four tests deselected on SQLite pass. `tests/verify_required_runs.py` exits 1 because that Dependabot test is the collected id that did not pass. The same id is the failure on `b6c6687`.

Base commands (2026-11-12, label local), from a checkout of `b6c6687`:

- `npm test` in `web/` — exit 0, 356 passed, 0 skipped ([web-test.txt](b6c6687/web-test.txt))
- `npm test` in `example-site/` — exit 0, 50 pass, 0 skipped ([example-site-test.txt](b6c6687/example-site-test.txt))
- `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest -m "not postgres"` in `api/` — exit 1, the Dependabot failure above

## Head commands

`scripts/verify.sh MOSS-085` from a clean tree at `4d71742` (exit 1 at `pytest-sqlite`). Remaining script commands, labeled local:

- PostgreSQL pytest — exit 1, same Dependabot failure; 501 passed, 0 skipped
- `tests/verify_required_runs.py` — exit 1, same id
- OpenTelemetry smoke — exit 0
- web `npm ci`, then `npm run check && npm test && npm run build && npm audit --audit-level=high` — exit 0, 364 passed, 0 skipped
- example-site `npm ci`, then `npm run check && npm test && npm run build && npm audit --audit-level=high` — exit 0, 50 pass, 0 skipped
- `pip-audit` — an earlier attempt exited 1 because `python3-venv` was missing ([pip-audit-venv.txt](4d71742/pip-audit-venv.txt)). After that package was installed, `pip-audit` 2.10.1 reported no known vulnerabilities, exit 0. `api/uv.lock` is unchanged.
- `npm audit` in `web/`, `example-site/`, and `ci/` — exit 0, found 0 vulnerabilities
- `gitleaks detect` on `git archive HEAD` — exit 0, no leaks found
- `npm ci` and `npx playwright install --with-deps chromium` in `ci/` — exit 0
- `docker build --tag mosscms:smoke .` — exit 0
- `docker compose -f ci/compose.yaml -p mosscms-smoke up --no-build -d --wait --wait-timeout 180` — exit 0
- `npm test` in `ci/` — exit 0, 2 passed, 0 skipped
- `docker compose -f ci/compose.yaml -p mosscms-smoke down --volumes` — exit 0

Earlier script steps on `4d71742`, all exit 0: `uv sync --locked --group dev`, ruff, ruff on scripts, mypy.

## Files

`web/src/components/AssetPicker.tsx`, `web/src/components/AssetPicker.test.tsx`, and this directory. `SeoEntryPanel`, `MarkdownInput`, `Fields`, and the media upload modules were not edited.
