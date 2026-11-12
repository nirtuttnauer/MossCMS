# MOSS-035 Next.js starter

local

Recorded 11 November 2026 (UTC). GitHub Actions was not used.

## Code under test

| | |
| --- | --- |
| Base | `58a0f15fa5e75e446b210911d727340dc4ca67dd` (`main`) |
| SHA tested | `cb60f95d71daf36ceb047ec0268ecdf3ad269df3` |
| Branch | `cursor/moss-035-nextjs-starter-e8b5` |
| `git status --porcelain` at the start of `scripts/verify.sh` | empty |
| Verify start | 2026-11-11T18:21:55Z |
| Python / uv | 3.12.3 / 0.13.7 |
| ruff / mypy | 0.16.10 / 2.4.0 |
| Node / npm | v22.23.4 / 10.9.9 |
| Docker / Compose | 29.1.3 / 2.40.3 |
| gitleaks | 8.30.1 |

`cb60f95` adds `starters/nextjs/`. This later commit adds the run record. It does not change the starter.

## Starter build, audit, and smoke

Working directory `starters/nextjs`. `node_modules` and `.next` were removed before the commands.

| Command | Exit | Result |
| --- | --- | --- |
| `npm ci && npm run build` | 0 | Next.js 16.4.6 production build. `/` is server-rendered on demand. |
| `npm audit` | 0 | `found 0 vulnerabilities` (devDependencies included, no `--audit-level`, no ignore) |

Logs: [npm-ci-build.txt](starter/npm-ci-build.txt), [npm-audit.txt](starter/npm-audit.txt).

Pinned versions: `next` 16.4.6, `react` 19.3.1, `react-dom` 19.3.1. Lockfile: `starters/nextjs/package-lock.json`.

Smoke against a local SQLite MossCMS. The API was `uv run python -m app.cli serve` with `MOSS_USE_SQLITE=true` on `http://127.0.0.1:18001`. Setup created an article type, published `starter-note` ("Moss starter published note"), and left `starter-draft` ("Moss starter hidden draft") unpublished. A delivery token scoped to `article` was passed in the server environment and is not recorded. The production server was `npm start --port 3010`.

| Command | Exit | Result |
| --- | --- | --- |
| `curl -sS -D - http://127.0.0.1:3010/` | 0 | HTTP 200. The HTML contains `Moss starter published note`, `article`, and `starter-note`. It does not contain `Moss starter hidden draft` or the delivery token. |

Full response: [smoke.txt](starter/smoke.txt). Related responses (missing token, empty list, unreachable CMS) are in [edges.txt](starter/edges.txt).

The page was also opened in a browser at desktop width and at 390×844. The published title was visible, the draft was absent, and the console reported no errors. Requests from the browser stayed on port 3010. The client bundles do not contain `delivery/graphql` or the delivery token.

## QA G0

Command: `scripts/verify.sh MOSS-035`. Exit 1. Logs are in [cb60f95](cb60f95/). The script stopped at the SQLite required run.

| Step | Exit |
| --- | --- |
| `uv sync --locked --group dev` | 0 |
| ruff check and format | 0 |
| ruff on scripts, example-site setup, telemetry smoke | 0 |
| `mypy app` | 0 |
| `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest -m "not postgres"` | 1 |

```
collected 492 items / 4 deselected / 488 selected
1 failed, 487 passed, 4 deselected, 6 warnings in 73.54s
FAILED tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests
```

The failure is:

```
starters/nextjs/package.json (npm /starters/nextjs) is not covered by .github/dependabot.yml
```

No skip and no xfail. PostgreSQL, web, example-site, audits, gitleaks, and the production smoke did not start, because `scripts/verify.sh` exits when a step fails.

Suite files under `api/`, `web/`, `example-site/`, `ci/`, and `scripts/` match `58a0f15`. The recorded MOSS-054 run on that same suite (`reviews/MOSS-054/c684c24/counts.txt`) is the comparison baseline:

| Run | Baseline `58a0f15` suite | This run |
| --- | --- | --- |
| SQLite `-m "not postgres"` | 492 collected, 488 passed, 4 deselected, 0 failed, 0 skipped | 492 collected, 487 passed, 1 failed, 4 deselected, 0 skipped |
| PostgreSQL | 492 passed, 0 skipped | not run |
| web | 356 passed, 0 skipped | not run |
| example-site | 47 passed, 0 skipped | not run |
| production | 2 passed, 0 skipped | not run |

The new failure is the manifest-coverage assertion. The other 487 selected SQLite tests passed, matching the baseline aside from that one assertion.

## File left unchanged

Covering the new manifest means adding `"/starters/nextjs"` to the existing npm `directories` list in `.github/dependabot.yml`. That file is outside the file list for this ticket, so it was not edited. `shared/delivery.mjs` was not edited.
