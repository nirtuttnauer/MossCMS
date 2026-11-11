# MOSS-061 local verification

label: local

| | |
| --- | --- |
| Base | `58a0f15fa5e75e446b210911d727340dc4ca67dd` (`origin/main` on 2026-11-11) |
| Verified tree | `f15a9a654e2712bd4609e82573fde315ff57eca5` |
| Clean status | `reviews/MOSS-061/f15a9a6/summary.txt` records an empty `git status --porcelain` when `scripts/verify.sh MOSS-061` started |
| Started | 2026-11-11T18:22:42Z |

`scripts/verify.sh MOSS-061` was run on that verified tree and exited 1 at `pip-audit`. The same command on the base lockfile reports the same two advisories (`reviews/MOSS-061/58a0f15/pip-audit.txt`): `graphql-core` 3.3.0 `CVE-2026-119286` and `joserfc` 1.7.5 `CVE-2026-119284`. `api/uv.lock` and `api/pyproject.toml` are unchanged from the base. No ignore, allowlist, or override was added. Those files are outside this ticket's file list.

The steps after `pip-audit` were run with the same commands and logged beside the script output. Exit codes are in `reviews/MOSS-061/f15a9a6/exit-codes.txt`.

## Counts

| Suite | Base `58a0f15` | Verified tree `f15a9a6` |
| --- | --- | --- |
| API pytest, SQLite, `-m "not postgres"` | 488 passed, 4 deselected, 0 skipped | 490 passed, 4 deselected, 0 skipped |
| API pytest, PostgreSQL | 492 passed, 0 skipped | 494 passed, 0 skipped |
| Admin web vitest | 36 files, 356 passed, 0 skipped | 36 files, 356 passed, 0 skipped |
| Example site `node --test` | 47 pass, 0 fail, 0 skipped | 50 pass, 0 fail, 0 skipped |
| Production Playwright | not re-run on the base in this session | 2 passed on the retry (see below) |

The API delta is the new SEO test and the copy scan. The example-site delta is the three axe-core fixture tests. Web counts match; `web/` is unchanged.

Base commands (2026-11-11, label local), from a checkout of `58a0f15`:

- `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest -m "not postgres"` in `api/` — exit 0
- `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=postgres MOSS_TEST_DATABASE_URL=postgresql+psycopg://pg:pgtestpw@localhost:5432/postgres uv run pytest` in `api/` — exit 0
- `npm test` in `web/` — exit 0
- `npm test` in `example-site/` — exit 0
- `uv export --frozen --all-groups --no-emit-project` then `uv run --with pip-audit pip-audit --progress-spinner off -r requirements.txt` in `api/` — exit 1, same two advisories

Logs: `reviews/MOSS-061/58a0f15/`.

## Head commands

`scripts/verify.sh MOSS-061` from a clean tree at `f15a9a6` (exit 1 at pip-audit). Remaining script commands, logged with `label: local`:

- `npm audit` in `web/`, `example-site/`, and `ci/` — exit 0, `found 0 vulnerabilities`
- `gitleaks detect` on `git archive HEAD` — exit 0, no leaks found
- `npm ci` in `ci/` — exit 0
- `npx playwright install --with-deps chromium` in `ci/` — exit 0
- `docker build --tag mosscms:smoke .` — exit 0
- `docker compose -f ci/compose.yaml -p mosscms-smoke up --no-build -d --wait --wait-timeout 180` — exit 1 on the earlier attempt
- `npm test` in `ci/` — exit 1 on that attempt (2 failed, `ECONNRESET` on `/ready`)
- `docker compose -f ci/compose.yaml -p mosscms-smoke down --volumes` — exit 0

The app container was running `python -m app.cli serve` and could resolve `db`, but TCP to Postgres timed out. The host `iptables-legacy` `FORWARD` policy was `DROP`, and its Docker rules accepted `docker0` while the compose bridge was dropped. After `iptables-legacy -P FORWARD ACCEPT`, the same image became healthy. The retry logs are `production-up-retry.txt`, `production-test-retry.txt` (2 passed), and `production-down-retry.txt`, each exit 0, dated 2026-11-11T18:36:19Z onward.

Earlier script steps on `f15a9a6`, all exit 0: `uv sync --locked --group dev`, ruff, ruff on scripts, mypy, both pytest runs, `tests/verify_required_runs.py` (`ok: true`), OpenTelemetry smoke, web and example-site `npm ci` plus `npm run check && npm test && npm run build && npm audit --audit-level=high`.

## Publish-time receipt

The publish-time receipt is not in this change. The prompt says that check (MOSS-059) is not built. The ticket text names MOSS-062 for the same receipt. Findings are returned by `seoAudit` and `seoEntryAudit`.

## Notes left outside the file list

`docs/seo-audit.md` still says website HTML is not checked. It was not edited. `NOT_CHECKED` in `api/app/seo.py` is what `seoAudit` returns, and it names the starter checks: button-name, label, html-has-lang, html-lang-valid, image-alt, link-name. The string still includes `Captured schedules`.

axe-core 4.14.0 is an example-site devDependency. Its license is MPL-2.0 (`reviews/MOSS-061/axe-core-license.txt`, and the lockfile). jsdom 31.0.0 (MIT, devDependency) is the DOM harness for the node test, because axe-core needs a document.
