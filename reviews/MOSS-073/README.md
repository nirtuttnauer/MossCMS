# MOSS-073 Hebrew and Arabic field values

local

Recorded 12 November 2026 (UTC). The product tree was clean at `25b5b3e1bd6e7e02fec7fc4983860f0f6f9c34b7`. `scripts/verify.sh MOSS-073` refuses a dirty tree, writes this folder, and exits non-zero on a failed step or a runtime skip or xfail. There is no allowed-skip list and no audit ignore.

`scripts/verify.sh MOSS-073` stopped at the SQLite pytest step. The remaining steps from that script were run with the same commands and recorded in the same folder. The database password printed by those commands is replaced with `<redacted>` in the two logs that contained it. It is the password `scripts/verify.sh` already uses, and it is not repeated here.

## Code under test

| | |
| --- | --- |
| Base | `5ea1d037bb85e47c2efc1d97f72998d130130878` (main) |
| SHA tested | `25b5b3e1bd6e7e02fec7fc4983860f0f6f9c34b7` |
| Branch | `cursor/rtl-locale-field-values-2f7a` |
| `git status --porcelain` at the start of this run | empty (clean) |
| Date | 2026-11-12T14:44:38Z through 2026-11-12T15:01:50Z |
| Commands | `scripts/verify.sh MOSS-073`, then the same later steps after the SQLite stop |
| Logs | [25b5b3e](25b5b3e/) |

The evidence files in this directory were committed after the run, so the pull request head is the evidence commit. The counts below are for `25b5b3e`.

This VM needed `python3.12-venv` so `pip-audit` could create its temporary environment, and the Docker bridge needed forwarding accepted so Compose containers could reach each other. Neither change is in the repository.

## What changed

`localeValueProps` in `web/src/lib/locales.ts` sets `dir` and `lang` for a localized value.

- `he` and `ar`, including a suffix `LOCALE_PATTERN` already accepts (`he-IL`, `ar-EG`, `ar-SA`, `he-Latn`), use `dir="rtl"` and `lang` set to that locale key.
- Other keys the pattern accepts, including `en`, `fr`, `pt-BR`, `fr-CA`, and `en-he`, use `dir="ltr"` and `lang` set to that key.
- A missing or empty locale key keeps `dir="auto"` and does not set `lang`.
- A key the pattern rejects still gets a direction from its language subtag and does not get `lang`.

Text values and Markdown (the editor, the preview, and the image alt field) use those props. Numbers and dates stay `dir="ltr"` with no `lang`. The locale-code input and the suggested-locale select stay `dir="ltr"` with no `lang`. The admin document and the example site are unchanged. The diff against main, apart from this review folder, is the six files under `web/src/components` and `web/src/lib`.

A local admin session showed the Hebrew title `שלום` and the Hebrew Markdown preview `שלום עולם` aligned to the right. The document element had no `dir` attribute. Screenshots: [hebrew-title-field.png](25b5b3e/hebrew-title-field.png), [hebrew-markdown-preview.png](25b5b3e/hebrew-markdown-preview.png).

## Counts against main `5ea1d03`

The API, example-site, and production trees match `5ea1d03`. Web is that tree plus 29 tests: 18 in `locales.test.ts`, 4 in `Fields.test.tsx`, and 7 in `MarkdownInput.test.tsx`. [counts.json](25b5b3e/counts.json).

| Run | Main | This run | Skipped |
| --- | --- | --- | --- |
| SQLite `-m "not postgres"` | same suite; the Dependabot test below fails on main | 497 passed, 1 failed, 4 deselected, 502 collected | 0 |
| PostgreSQL, no marker filter | same suite; the same test fails on main | 501 passed, 1 failed, 502 collected | 0 |
| web | 356 (36 files) | 385 passed (36 files) | 0 |
| example-site | 50 passed (tree unchanged) | 50 passed, 0 failed | 0 |
| production Playwright | 2 (tree unchanged) | 2 passed | 0 |

The SQLite and PostgreSQL failure is `tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests`: `starters/nextjs/package.json` is not covered by `.github/dependabot.yml`. The same assertion fails on main `5ea1d03` in a detached worktree. Log: [5ea1d03/dependabot.txt](5ea1d03/dependabot.txt). This branch does not change `.github/dependabot.yml` or `starters/nextjs`.

`tests/verify_required_runs.py` then exits 1 because that test is missing from the passed ids. The four ids deselected on SQLite are the PostgreSQL-marked tests. No test was skipped, xfailed, or removed.

## Commands and results

| Command | Exit |
| --- | --- |
| `uv sync --locked --group dev` | 0 |
| `ruff check` and `ruff format --check` for `app tests migrations` | 0 |
| ruff check/format of scripts, example-site setup, telemetry smoke | 0 |
| `mypy app` | 0 |
| SQLite required run | 1 (Dependabot test, also on main) |
| PostgreSQL required run in the throwaway container | 1 (same test, also on main) |
| `tests/verify_required_runs.py` | 1 (that test missing from passed ids) |
| OTLP Collector smoke | 0 |
| web `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 |
| example-site `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 |
| `pip-audit` before `python3.12-venv` was installed | 1 ([pip-audit-missing-venv.txt](25b5b3e/pip-audit-missing-venv.txt)) |
| `pip-audit` against the frozen lock after that install | 0 (`No known vulnerabilities found`) |
| `npm audit` web, example-site, and ci | 0 (`found 0 vulnerabilities`) |
| `gitleaks` on `git archive HEAD` | 0 (`no leaks found`) |
| production image, compose, Playwright, teardown | 0 (2 passed) |

No `--ignore-vuln`, npm override, or gitleaks allowlist was added.
