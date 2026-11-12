# MOSS-036 Next.js live pages

local

Recorded 11 November 2026 (UTC). GitHub Actions was not used.

The prompt names an attached `MOSS-036.md`. That file was not in the upload or the repository. The outcome and done-when list in the prompt are the criteria recorded here.

## Code under test

| | |
| --- | --- |
| Base | `b6c66870b98af990ee91766e5a965e823bf2b03d` (`main`) |
| SHA tested | `85c6206d50e633fb2f9b95039d2a48a214036c5f` |
| Branch | `cursor/moss-036-nextjs-live-pages-ccb4` |
| `git status --porcelain` at the start of `scripts/verify.sh` | empty |
| Verify start | 2026-11-11T21:50:40Z |
| Python / uv | 3.12.3 / 0.13.7 |
| ruff / mypy | 0.16.10 / 2.4.0 |
| Node / npm | v22.23.4 / 10.9.9 |
| Docker / Compose | 29.1.3 / 2.40.3 |
| gitleaks | 8.30.1 |

`85c6206` changes `starters/nextjs/`. The review record does not change the starter. `shared/routes.mjs` and `shared/markdown.mjs` were not edited.

## Starter build, audit, test, and smoke

Working directory `starters/nextjs`. `node_modules` and `.next` were removed before the build.

| Command | Exit | Result |
| --- | --- | --- |
| `npm ci && npm run build` | 0 | Next.js 16.4.6 production build. `/[[...slug]]` is server-rendered on demand. |
| `npm audit` | 0 | `found 0 vulnerabilities` (devDependencies included, no `--audit-level`, no ignore) |
| `npm test` | 0 | 5 passed, 0 failed, 0 skipped |

Logs: [npm-ci-build.txt](starter/npm-ci-build.txt), [npm-audit.txt](starter/npm-audit.txt), [npm-test.txt](starter/npm-test.txt).

Pinned versions: `next` 16.4.6, `react` 19.3.1, `react-dom` 19.3.1, `react-markdown` 10.1.0, `remark-breaks` 4.0.0. Lockfile: `starters/nextjs/package-lock.json`.

Smoke against a local SQLite MossCMS. The API was `uv run python -m app.cli serve` with `MOSS_USE_SQLITE=true` on `http://127.0.0.1:18001`. Setup created an article type, published `starter-note` ("Moss starter published note", Markdown body), and left `starter-draft` ("Moss starter hidden draft", body `SECRET_DRAFT_BODY`) unpublished. A second token also covered published `sitePage` `home` and `journal`, published `sitePost` `c`, and unpublished `sitePost` `secret`. Delivery tokens were passed in the server environment and are not recorded. Production servers were `npx next start --port 3010` and `--port 3012`.

| Request | Status | Visible result |
| --- | --- | --- |
| `GET http://127.0.0.1:3010/` | 200 | List links `Moss starter published note`. Draft title and `SECRET_DRAFT_BODY` are absent. |
| `GET http://127.0.0.1:3010/starter-note` | 200 | `<h2>Live section</h2>`, `<strong>published</strong>`, and `https://example.com/moss`. Draft text is absent. |
| `GET http://127.0.0.1:3010/starter-draft` | 404 | Body contains `Page not found` and does not contain the draft title or `SECRET_DRAFT_BODY`. |
| `GET http://127.0.0.1:3012/` | 200 | Home page renders `Welcome <strong>home</strong>.` Navigation links Journal, Current, and the published note. |
| `GET http://127.0.0.1:3012/home` | 308 | `Location: /` |
| `GET http://127.0.0.1:3012/blog/c` | 200 | Published post `Live post`. |
| `GET http://127.0.0.1:3012/c` | 308 | `Location: /blog/c` |
| `GET http://127.0.0.1:3012/blog/secret` | 404 | `Page not found`. Draft title and `SECRET_DRAFT_BODY` are absent. |
| `GET http://127.0.0.1:3012/starter-draft` | 404 | `Page not found`. Draft text is absent. |

Full responses: [smoke.txt](starter/smoke.txt). Related responses (missing token, empty list, unreachable CMS) are in [edges.txt](starter/edges.txt). A 200 document also contains the string `Page not found` inside the Next.js router payload. The visible `<main>` on those 200 responses does not.

The pages were opened in a browser at desktop width and at 390×844. The published title, Markdown heading, strong text, and link were visible. The draft URL showed `Page not found`. Clicking Current opened `/blog/c`. Opening `/c` landed on `/blog/c`. Requests from the browser stayed on the starter port. The console on the draft URL reported the 404 response itself. No other console errors were reported.

## QA G0

Command: `scripts/verify.sh MOSS-036` on `85c6206`. Exit 1. Logs are in [85c6206](85c6206/). The same command on base `b6c6687` also exited 1. Those logs are in [b6c6687](b6c6687/). Both runs had an empty `git status --porcelain` at the start. Both stopped at the SQLite required run.

| Step | `85c6206` | `b6c6687` |
| --- | --- | --- |
| `uv sync --locked --group dev` | 0 | 0 |
| ruff check and format | 0 | 0 |
| ruff on scripts, example-site setup, telemetry smoke | 0 | 0 |
| `mypy app` | 0 | 0 |
| `MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest -m "not postgres"` | 1 | 1 |

`85c6206`:

```
collected 502 items / 4 deselected / 498 selected
2 failed, 496 passed, 4 deselected, 6 warnings in 138.23s
```

`b6c6687`:

```
collected 502 items / 4 deselected / 498 selected
2 failed, 496 passed, 4 deselected, 6 warnings in 107.95s
```

Failed on both SHAs:

```
FAILED tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests
FAILED tests/test_private_admin_compose.py::test_variant_a_proxy_and_variant_b_private_listener
```

The dependabot failure is:

```
starters/nextjs/package.json (npm /starters/nextjs) is not covered by .github/dependabot.yml
```

The compose failure on both SHAs is `curl: (28)` after 15 seconds with 0 bytes for `GET /delivery/entries` through the variant A proxy. No skip and no xfail. PostgreSQL, web, example-site, audits, gitleaks, and the production smoke did not start, because `scripts/verify.sh` exits when a step fails.

| Run | Base `b6c6687` | This run `85c6206` |
| --- | --- | --- |
| SQLite `-m "not postgres"` | 502 collected, 496 passed, 2 failed, 4 deselected, 0 skipped | 502 collected, 496 passed, 2 failed, 4 deselected, 0 skipped |
| PostgreSQL | not run | not run |
| web | not run | not run |
| example-site | not run | not run |
| production | not run | not run |

The selected SQLite counts match the base. The two failures match the base.

## Left unchanged

Covering the starter manifest means adding `"/starters/nextjs"` to the npm `directories` list in `.github/dependabot.yml`. That file is outside the file list for this ticket (MOSS-063), so it was not edited. `api/`, `example-site/`, `web/`, `CHANGELOG.md`, and `README.md` were not edited. Preview grants, media galleries, per-page metadata, and a CI job stay for MOSS-037 and MOSS-038.
