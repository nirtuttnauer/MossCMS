# Production Docker smoke test

The `production_docker` job in [Checks](../.github/workflows/checks.yml) builds the repository's production Dockerfile and starts it with PostgreSQL, `MOSS_ENV=production`, a non-root user and a read-only filesystem. It runs on every push and pull request and needs no repository secrets.

The [Docker Hub workflow](../.github/workflows/docker.yml) also calls the complete Checks workflow from the same commit. Publishing depends on that call succeeding, including every current or future check. Failed, cancelled or skipped checks prevent publishing; pull requests never publish. Main pushes, version tags and manual Docker runs each validate the commit they will publish. Missing Docker Hub credentials explicitly skip publication until both repository secrets are configured.

The Chromium tests check readiness; the packaged logo and WebP artwork's contents, MIME types and decoding; administrator setup; login, logout and failed-password feedback; Secure/HttpOnly session cookies; sidebar branding; desktop/mobile layouts; and browser errors or failed asset requests. The job uploads screenshots, traces and the HTML report, with container logs on failure, and always removes the disposable stack.

Run from the repository root with Docker Compose and Node.js 22 or newer:

```sh
npm ci --prefix ci
cd ci
npx playwright install --with-deps chromium
cd ..
docker compose -f ci/compose.yaml -p mosscms-smoke up --build -d --wait --wait-timeout 180
npm test --prefix ci
docker compose -f ci/compose.yaml -p mosscms-smoke down --volumes
```

Always run the final cleanup command, including after a failed test. The stack uses only disposable fixture credentials, a private Docker network and loopback port 18081. It does not use the root `.env` or existing application volumes. Run it against a fresh stack: the test creates the first administrator.

Artifacts are saved in `ci/test-results/` and `ci/playwright-report/`. The browser uses localhost's Secure-cookie exception; external TLS termination, OAuth providers, S3 and other browser engines are outside this test's coverage.
