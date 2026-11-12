# MOSS-075 admin Markdown preview

label: local

The admin preview in `web/src/components/Markdown.tsx` keeps `skipHtml` and `urlTransform={markdownUrl(assets)}`. This change adds component tests that lock that behavior. `Markdown.tsx` and `shared/markdown.mjs` are unchanged. The rendered preview already keeps raw HTML and script from becoming elements, and it already keeps `javascript:` and `data:` URLs off `href` and `src`, so there was no component wrapper to add and no shared-helper limitation to record.

| | |
| --- | --- |
| Ticket base | `b6c66870b98af990ee91766e5a965e823bf2b03d` |
| PR base | `5ea1d037bb85e47c2efc1d97f72998d130130878` (`origin/main`) |
| Verified tree | `d434df157c5e5503862b6b63cf78b75618b1cc81` |
| Clean status | [d434df1/summary.txt](d434df1/summary.txt) records an empty `git status --porcelain` when `scripts/verify.sh MOSS-075` started |
| Started | 2026-11-12T14:47:49Z |
| Evidence finished | 2026-11-12T15:01:11Z |

`git diff b6c6687 -- . ':(exclude).github' ':(exclude)web/src/components/Markdown.test.tsx'` is empty. `origin/main` adds the GitHub Actions pin bump in `.github/workflows` and nothing else. API sources on the verified tree match `b6c6687`.

## What the tests lock

`web/src/components/Markdown.test.tsx` renders a preview fixture with raw HTML, a script element, an image `onerror` attribute, an iframe, markdown links and images, asset URLs, a reference link, and autolinks. The rendered DOM and the static markup have no `script`, `iframe`, `object`, `embed`, or event-handler attributes. `window.alert` is not called. `href` and `src` do not use the `javascript:` or `data:` schemes, including uppercase spellings and asset URLs that point at those schemes. HTTPS links, `mailto:` links, HTTPS images, and an allowed image asset still render.

A separate fixture renders Hebrew with niqqud as text: `שָׁלוֹם עוֹלָם` and `בְּרֵאשִׁית`, including a heading, strong text, and a link label. The source string is the text that appears.

Replacing `urlTransform` with an identity function made the new preview test fail. That edit was reverted before the commit. `shared/markdown.mjs` was not edited.

## Commands

`scripts/verify.sh MOSS-075` on a clean tree at `d434df1` (label local). Exit 1 at `pytest-sqlite`.

The failing test is `tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests`. `python3 scripts/check_dependabot.py` on a worktree of `b6c6687` exits 1 with the same line: `starters/nextjs/package.json (npm /starters/nextjs) is not covered by .github/dependabot.yml` ([b6c6687/dependabot.txt](b6c6687/dependabot.txt)). `starters/nextjs/` and `.github/dependabot.yml` are outside this ticket's file list. No skip, xfail, ignore, allowlist, or override was added.

The steps after `pytest-sqlite` were run with the same commands and written into [d434df1](d434df1/). Exit codes are in [d434df1/exit-codes.txt](d434df1/exit-codes.txt). `pytest-postgres` and `tests/verify_required_runs.py` exit 1 for that same Dependabot test. The other continued steps exit 0.

This VM's `iptables-legacy` `FORWARD` policy was `DROP`. With that policy, `test_variant_a_proxy_and_variant_b_private_listener` timed out on `curl` to the published proxy. After `iptables-legacy -P FORWARD ACCEPT`, the same test passed. That is a VM firewall adjustment. It is not a repository change.

## Counts

Web baseline, label local, 2026-11-12, checkout `5ea1d03` before this test existed. `web/` at that commit matches `b6c6687`. Command: `npm test` in `web/`. Exit 0. 36 files, 356 passed, 0 skipped.

| Suite | `b6c6687` (API sources match; web measured before the new tests) | Verified tree `d434df1` |
| --- | --- | --- |
| API pytest, SQLite, `-m "not postgres"` | same API tree, so the same result | 497 passed, 1 failed, 4 deselected, 0 skipped |
| API pytest, PostgreSQL | same API tree, so the same result | 501 passed, 1 failed, 0 skipped |
| Admin web vitest | 36 files, 356 passed, 0 skipped | 36 files, 358 passed, 0 skipped |
| Example site `node --test` | sources unchanged | 50 pass, 0 fail, 0 skipped, 0 todo |
| Production Playwright | | 2 passed, 0 skipped |

The failed API test on both required runs is the Dependabot manifest check above. The four ids deselected on SQLite are the PostgreSQL-marked tests, and those four passed in the PostgreSQL run. The web delta is the two new preview tests. `pip-audit` exited 0 (`No known vulnerabilities found`). `npm audit` in `web/`, `example-site/`, and `ci/` exited 0. `gitleaks` on `git archive HEAD` exited 0.
