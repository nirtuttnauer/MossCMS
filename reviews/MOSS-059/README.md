# MOSS-059 private admin and public delivery

local

Recorded 11 November 2026 (UTC). `scripts/verify.sh MOSS-059` ran on a clean tree at `76ac4f0ae972be2f9b8fc09cb871d0d608e1f6d1`. The script refuses a dirty tree, writes this folder, and exits non-zero on a failed step or a runtime skip or xfail. There is no allowed-skip list and no audit ignore.

## Code under test

| | |
| --- | --- |
| Base | `58a0f15fa5e75e446b210911d727340dc4ca67dd` (main) |
| SHA tested | `76ac4f0ae972be2f9b8fc09cb871d0d608e1f6d1` |
| Branch | `cursor/private-admin-deployment-c8bf` |
| `git status --porcelain` at the start of this run | empty (clean) |
| Date | 2026-11-11T19:01:03Z through 2026-11-11T19:12:10Z |
| Command | `scripts/verify.sh MOSS-059` |
| Exit | 0 |
| Logs | [76ac4f0](76ac4f0/) |

The evidence files in this directory were committed after the run, so the pull request head is the evidence commit. The counts below are for `76ac4f0`.

This VM needed `iptables` pointed at `iptables-legacy` so Compose containers on a bridge can reach each other, and `python3.12-venv` so `pip-audit` can create its temporary environment. Neither change is in the repository.

## Counts against main `58a0f15`

Baseline is [reviews/MOSS-054/c684c24/counts.txt](../MOSS-054/c684c24/counts.txt), the recorded run of that main commit. The API total is 8 higher. Web, example-site, and production counts are unchanged. Zero skipped and zero failed.

| Run | Main collected / passed | This run collected / passed | Deselected | Skipped |
| --- | --- | --- | --- | --- |
| SQLite `-m "not postgres"` | 492 / 488 | 500 / 496 | 4 | 0 |
| PostgreSQL, no marker filter | 492 / 492 | 500 / 500 | 0 | 0 |
| web | 356 (36 files) | 356 (36 files) |  | 0 |
| example-site | 47 | 47 |  | 0 |
| production Playwright | 2 | 2 |  | 0 |

The eight new tests run in both required runs:

- `tests/test_route_classification.py` (documented table, unclassified route, missing route, section wording)
- `tests/test_forwarded_peer.py` (TestClient peer, and `python -m app.cli serve` with `FORWARDED_ALLOW_IPS=*`)
- `tests/test_delivery_exposure.py` (delivery token rejects mutations and admin-type introspection)
- `tests/test_private_admin_compose.py` (variant A allowlist proxy and variant B private listener)

The four ids deselected on SQLite are the same PostgreSQL-marked tests as the baseline. `tests/verify_required_runs.py` reported the union of passed ids. [counts.json](76ac4f0/counts.json).

## Commands and results

Every step in [exit-codes.txt](76ac4f0/exit-codes.txt) exited 0.

| Command | Exit |
| --- | --- |
| `uv sync --locked --group dev` | 0 |
| `ruff check` and `ruff format --check` for `app tests migrations` | 0 |
| ruff check/format of scripts, example-site setup, telemetry smoke | 0 |
| `mypy app` | 0 |
| SQLite required run | 0 |
| PostgreSQL required run in the throwaway container | 0 |
| `tests/verify_required_runs.py` | 0 |
| OTLP Collector smoke | 0 |
| web `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 |
| example-site `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 |
| `pip-audit` against the frozen lock | 0 |
| `npm audit` web, example-site, and ci | 0 |
| `gitleaks` on `git archive HEAD` | 0 |
| production image, compose, Playwright, teardown | 0 |

No `--ignore-vuln`, npm override, or gitleaks allowlist was added.

## What the compose test checked

`tests/test_private_admin_compose.py` builds the CMS and the example site with the overlays in this directory.

Variant A publishes the allowlist proxy in [nginx-allowlist.conf](nginx-allowlist.conf) and a loopback admin listener. Every private route from the generated table returns 404 through the proxy and does not carry `X-Request-ID`. Every public route reaches the app (`X-Request-ID` is present). Path-confusion targets and `X-HTTP-Method-Override`, `X-Original-URL`, and `X-Rewrite-URL` return 404 and do not appear in the app log. A delivery token on `/delivery/graphql` cannot run a mutation or read the `Mutation` type. An admin cookie and an admin bearer token through the proxy open no private route; the same cookie works on the private listener. `GET /health` is `{"status":"ok"}`. `/openapi.json` and `/docs` are 404 on the proxy. Spoofed `X-Forwarded-For` and `Forwarded` do not change the rate-limit key, the login audit `client`, or the request-log `client`. Preview redeem, a signed media variant, and a webhook delivery succeed on the private path. The example site renders the published page.

Variant B's rendered Compose config has no `ports` entry for the CMS service, and a host connection to that port fails. Publishing a port makes the health check succeed, and removing the port closes it again. The website still renders, and preview redeem plus the media variant are fetched from the website container over `http://app:8001`. `/openapi.json` and `/docs` on the website are 404.

## App changes the tests required

`python -m app.cli serve` starts Uvicorn with `proxy_headers=False`. Rate limits, the setup, login, and invitation audit rows, and the request log use `client_address()`, which reads the TCP peer and does not read `X-Forwarded-For` or `Forwarded`. The `mosscms` logger is attached at INFO so that request line is emitted. `api/tests/test_cli.py` expects `proxy_headers=False`.

`pip-audit` on the lock from main reports CVE-2026-119286 in `graphql-core` 3.3.0 and CVE-2026-119284 in `joserfc` 1.7.5. Those pins moved to 3.3.1 and 1.7.6, the versions the advisory names. `api/uv.lock` is the file that records them. The same audit is clean after that change.
