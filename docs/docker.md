# Docker images and Compose

MossCMS uses one multistage image for the Python API and compiled React admin. The runtime runs as UID 10001, listens on port 8001, stores local media in `/data`, and checks database readiness at `/ready`. Startup applies database migrations before serving. By default, `compose.yaml` provides PostgreSQL with persistent database and media volumes. Set `MOSS_USE_SQLITE=true` to use SQLite in the media volume instead.

## Run from Docker Hub

After the first publication, the public image is `nirtuttnauer/mosscms`; pulling it requires no Docker Hub sign-in. Clone this repository to obtain Compose, configuration and backup tools:

```sh
git clone https://github.com/nirtuttnauer/MossCMS.git
cd MossCMS
python3 scripts/configure.py
docker compose pull app db
docker compose up --no-build -d --wait app
```

Open http://localhost:8001 and create your first administrator using `MOSS_SETUP_TOKEN` from `.env`. The image includes no preset account or database credentials. Keep `.env` private. `docker compose logs --tail 100 app db` shows startup diagnostics.

`MOSS_IMAGE` selects the app image; its default is `nirtuttnauer/mosscms:latest`. Published images support `linux/amd64` and `linux/arm64`. `latest` follows `main`; `sha-FULL_COMMIT_SHA` identifies a build; a Git tag `v1.2.3` publishes `1.2.3` and `1.2`. Pin a version or digest in `.env` for production. Pre-release tags produce the full pre-release version rather than a stable minor alias.

For a fresh production instance, generate configuration with `python3 scripts/configure.py --production --public-url https://cms.example.com` instead. Terminate TLS at a reverse proxy forwarding to the default loopback binding. Follow [deployment and recovery](deployment-recovery.md) for authentication, proxy, storage and backup configuration.

`MOSS_PORT` changes only the host port. Keep the default `MOSS_BIND_HOST=127.0.0.1` when using a host reverse proxy. The container's port and health check remain on 8001.

## Run without PostgreSQL

```sh
python3 scripts/configure.py --sqlite
docker compose pull app
docker compose up --no-build -d --wait
```

`--sqlite` sets the boolean `MOSS_USE_SQLITE=true` in `.env`. For a local build, replace `--no-build` with `--build`. Production also supports SQLite: add `--production --public-url https://cms.example.com` to the configuration command. The SQLite database persists at `/data/mosscms.db`, including when S3 stores uploads.

With `MOSS_USE_SQLITE=true`, ordinary `docker compose up` stops any existing Postgres container and starts the app without PostgreSQL credentials; `false` or an unset flag keeps the PostgreSQL dependency. SQLite mode replaces `db` with the app image running `/bin/true`, which exits immediately without mounting or changing the Postgres data volume. After the app is ready, the optional website can start with `docker compose --profile website up --build -d example-site`. Use one app instance and preserve the data volume. Switching backends does not migrate content. Follow [SQLite backup and recovery](deployment-recovery.md#sqlite-backup-and-recovery).

## Build locally

```sh
python3 scripts/configure.py
MOSS_IMAGE=mosscms:local docker compose up --build -d --wait app
```

The existing `docker compose up --build -d` command also works and tags the local build with the selected `MOSS_IMAGE`. For a direct image build, use `docker build -t mosscms:local .`. The image needs the database and environment settings provided by Compose to run.

The optional example website remains a separate local build; see [website setup](../example-site/README.md). Start it with `docker compose --profile website up --build -d example-site` after configuring its environment.

## Upgrade a published image

To add optional OTLP tracing and histogram metrics, use the [OpenTelemetry guide](observability.md) and `compose.observability.yaml`. The overlay includes a pinned local Collector; ordinary Compose remains telemetry-disabled by default.

Stop writers and [back up database and media](deployment-recovery.md#backup-with-writers-stopped). Retain the old image and its matching backup/configuration. Set `MOSS_IMAGE` in `.env` to the new published version or digest, then:

```sh
docker compose pull app
docker compose up --no-build -d --wait app
```

Check readiness, sign-in and delivery access. Migrations run automatically. Rollback requires the old image plus its matching database/media backup; do not downgrade the schema alone or delete volumes during an upgrade.

## Publish to Docker Hub

1. Create `nirtuttnauer/mosscms` on Docker Hub with **Public** visibility.
2. Add GitHub Actions repository secrets `DOCKERHUB_USERNAME` (the Docker Hub account with push access) and `DOCKERHUB_TOKEN` (an access token with read/write permission). Never commit the token or put it in `.env`.
3. Push the workflow to `main` or run **Docker** manually from GitHub Actions on `main` for the first publication. Push a semantic version tag such as `v1.2.3` for a versioned image.
4. Verify an anonymous pull with `docker pull nirtuttnauer/mosscms:latest` from a signed-out Docker client.

The [Docker workflow](../.github/workflows/docker.yml) calls the complete **Checks** workflow from the same commit before publishing. All checks must pass: API validation (including pip-audit of `api/uv.lock`), PostgreSQL tests, admin tests, example-site tests, gitleaks, and the production Docker login/branding smoke test. Admin and example-site `npm audit` include dev dependencies and fail on any advisory. Failed or cancelled checks prevent publishing; pull requests never log in or push. Main pushes, version tags and manual runs each validate the source they will publish, including future checks added to the shared suite. Both Docker Hub secrets must be configured; missing credentials explicitly skip publication. The production smoke test's screenshots and diagnostics are available in the workflow artifacts.
