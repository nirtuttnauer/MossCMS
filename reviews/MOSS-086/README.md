# MOSS-086 local verification

label: local

| | |
| --- | --- |
| Ticket base named in the prompt | `b6c66870b98af990ee91766e5a965e823bf2b03d` |
| Branch point | `5ea1d037bb85e47c2efc1d97f72998d130130878` (`origin/main` on 2026-11-12) |
| Verified code | `7ef81619fa9d40e0cd1b48e63c3caef6d50b421a` |
| Clean status | `reviews/MOSS-086/7ef8161/summary.txt` records an empty `git status --porcelain` when `scripts/verify.sh MOSS-086` started |
| Started | 2026-11-12T14:46:52Z |
| Finished | 2026-11-12T15:05:07Z |

`b6c6687..5ea1d03` changes action SHAs in `.github/workflows/checks.yml` and `.github/workflows/docker.yml`. `api/`, `example-site/`, `web/` apart from this ticket, and `.github/dependabot.yml` match `b6c6687`.

## What the compare view does

A Hebrew change that adds niqqud stays visible in the revision table, including the vowel marks, with `dir="auto"` on the value cells. Revision Markdown is rendered so raw HTML is text, and `javascript:` links are text rather than `href` values. Fenced and inline code keep their source text. An `https` link and an asset image still render. Restore confirmation is unchanged.

`web/src/components/Markdown.tsx` and `web/src/components/SeoEntryPanel.tsx` were not edited.

## Counts

| Suite | Base `5ea1d03` (same product tree as `b6c6687`) | Verified code `7ef8161` |
| --- | --- | --- |
| API pytest, SQLite, `-m "not postgres"` | same tree as the head API suite | 497 passed, 1 failed, 4 deselected, 0 skipped |
| API pytest, PostgreSQL | same tree as the head API suite | 501 passed, 1 failed, 0 skipped |
| Admin web vitest | 36 files, 356 passed, 0 skipped | 36 files, 358 passed, 0 skipped |
| Example site `node --test` | tree matches the head | 50 pass, 0 fail, 0 skipped |
| Production Playwright | tree matches the head | 2 passed, 0 skipped |

The web delta is the two revision-compare tests. The API failure on both database runs is `tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests`. On `5ea1d03` that test fails with `starters/nextjs/package.json (npm /starters/nextjs) is not covered by .github/dependabot.yml` (`reviews/MOSS-086/base-5ea1d03/dependabot.txt`). `.github/dependabot.yml` was not edited. `tests/verify_required_runs.py` exits 1 because that test did not pass. The four PostgreSQL-marked tests are deselected on SQLite and run on PostgreSQL. The logs have 0 skipped.

Base web command (2026-11-12, label local), from a checkout of `5ea1d03`: `npm ci && npm test` in `web/` — exit 0. Log: `reviews/MOSS-086/base-5ea1d03/web-test.txt`.

## Head commands

`scripts/verify.sh MOSS-086` from a clean tree at `7ef8161` (exit 1 at `pytest-sqlite`). The host `iptables-legacy` `FORWARD` policy was `DROP`, and the private-admin compose test timed out. After `iptables-legacy -P FORWARD ACCEPT`, the same SQLite command is 1 failed, 497 passed, 4 deselected, 0 skipped. The compose test passes in that run.

The following `scripts/verify.sh` commands were then run on the same SHA and logged beside it. Exit codes are in `reviews/MOSS-086/7ef8161/exit-codes.txt`.

- `uv run pytest` with PostgreSQL — exit 1, same Dependabot test, 501 passed, 0 skipped
- `uv run python tests/verify_required_runs.py` — exit 1, same missing pass
- OpenTelemetry smoke — exit 0
- web `npm ci`, `npm run check && npm test && npm run build && npm audit --audit-level=high` — exit 0
- example-site `npm ci` and the same check, test, build, and audit — exit 0
- `pip-audit` on the locked requirements — exit 0, `No known vulnerabilities found` (an earlier attempt exited 1 because `python3.12-venv` was not installed)
- `npm audit` in `web/`, `example-site/`, and `ci/` — exit 0, `found 0 vulnerabilities`
- `gitleaks detect` on `git archive HEAD` — exit 0, no leaks found
- `npm ci` and `npx playwright install --with-deps chromium` in `ci/` — exit 0
- `docker build --tag mosscms:smoke .` — exit 0
- compose up, `npm test` in `ci/`, compose down — exit 0, 2 passed

No ignore, allowlist, or override was added.
