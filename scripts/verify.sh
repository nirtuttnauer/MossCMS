#!/usr/bin/env bash
# One-command local evidence for the checks in .github/workflows/checks.yml.
# Usage: scripts/verify.sh <label>
# Writes reviews/<label>/<short-sha>/ and exits non-zero on the first failure,
# or on any runtime skip or xfail. Refuses a dirty tree. No secrets.
set -euo pipefail

if [[ $# -ne 1 || "$1" == -* || ! "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo "usage: scripts/verify.sh <label>" >&2
  exit 2
fi
LABEL="$1"

if [[ -d "${HOME}/.local/bin" ]]; then
  export PATH="${HOME}/.local/bin:${PATH}"
fi

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "verify.sh: not a git checkout" >&2
  exit 2
}
cd "$ROOT"

STATUS="$(git status --porcelain)"
if [[ -n "$STATUS" ]]; then
  echo "verify.sh: refusing to run on a dirty tree" >&2
  printf '%s\n' "$STATUS" >&2
  exit 1
fi

ensure_gitleaks() {
  if command -v gitleaks >/dev/null 2>&1; then
    return
  fi
  local version="8.30.1"
  local sha="551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"
  local dest="${XDG_CACHE_HOME:-$HOME/.cache}/moss-verify/gitleaks-${version}"
  local bin="${dest}/gitleaks"
  if [[ ! -x "$bin" ]]; then
    local tmp archive
    tmp="$(mktemp -d)"
    archive="${tmp}/gitleaks.tar.gz"
    curl -fsSL -o "$archive" \
      "https://github.com/gitleaks/gitleaks/releases/download/v${version}/gitleaks_${version}_linux_x64.tar.gz"
    echo "${sha}  ${archive}" | sha256sum -c -
    tar -xzf "$archive" -C "$tmp" gitleaks
    mkdir -p "$dest"
    install -m 755 "${tmp}/gitleaks" "$bin"
    rm -rf "$tmp"
  fi
  export PATH="${dest}:${PATH}"
}

require_tools() {
  local missing=()
  local tool
  for tool in uv node npm python3 docker git curl sha256sum; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      missing+=("$tool")
    fi
  done
  if ! docker compose version >/dev/null 2>&1; then
    missing+=("docker-compose")
  fi
  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "verify.sh: missing tools: ${missing[*]}" >&2
    exit 1
  fi
  ensure_gitleaks
}

require_tools

SHA="$(git rev-parse HEAD)"
SHA7="${SHA:0:7}"
EVIDENCE="${ROOT}/reviews/${LABEL}/${SHA7}"
export EVIDENCE ROOT
export GITHUB_WORKSPACE="$ROOT"
mkdir -p "$EVIDENCE"

# A caller environment must not narrow or retarget the suite.
unset PYTEST_ADDOPTS MOSS_REQUIRED_RUN MOSS_TEST_DATABASE_URL || true

PG_CONTAINER=""
PRODUCTION_STARTED=""

cleanup() {
  local status=$?
  if [[ -n "${PG_CONTAINER}" ]]; then
    docker rm -f "$PG_CONTAINER" >/dev/null 2>&1 || true
  fi
  docker rm -f moss-otel-smoke >/dev/null 2>&1 || true
  if [[ -n "${PRODUCTION_STARTED}" ]]; then
    docker compose -f "${ROOT}/ci/compose.yaml" -p mosscms-smoke down --volumes >/dev/null 2>&1 || true
  fi
  exit "$status"
}
trap cleanup EXIT

{
  echo "label: local"
  echo "sha: ${SHA}"
  echo "short_sha: ${SHA7}"
  echo "started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "git status --porcelain: empty"
} >"${EVIDENCE}/summary.txt"

{
  echo "label: local"
  echo "sha: ${SHA}"
  echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "git status --porcelain:"
  echo "(empty)"
  echo "python: $(python3 --version 2>&1)"
  echo "uv: $(uv --version 2>&1)"
  echo "node: $(node --version 2>&1)"
  echo "npm: $(npm --version 2>&1)"
  echo "docker: $(docker version --format '{{.Server.Version}}' 2>&1)"
  echo "compose: $(docker compose version 2>&1)"
  echo "gitleaks: $(gitleaks version 2>&1)"
} >"${EVIDENCE}/versions.txt"

step() {
  local workdir="$1"
  local name="$2"
  local command target code
  command="$(cat)"
  local logfile="${EVIDENCE}/${name}.txt"
  {
    echo "label: local"
    echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "sha: ${SHA}"
    echo "workdir: ${workdir}"
    echo "command:"
    printf '%s\n' "$command"
    local var
    for var in MOSS_USE_SQLITE MOSS_REQUIRED_RUN MOSS_TEST_DATABASE_URL GITHUB_WORKSPACE; do
      if [[ -n "${!var:-}" ]]; then
        printf '%s=%s\n' "$var" "${!var}"
      fi
    done
    echo "---- output ----"
  } >"$logfile"
  if [[ "$workdir" == "." ]]; then
    target="$ROOT"
  else
    target="${ROOT}/${workdir}"
  fi
  echo "verify.sh: ${name}" >&2
  set +e
  (cd "$target" && bash -euo pipefail -c "$command") >>"$logfile" 2>&1
  code=$?
  set -e
  echo "exit_code: ${code}" >>"$logfile"
  echo "${name} ${code}" >>"${EVIDENCE}/exit-codes.txt"
  if [[ "$code" -ne 0 ]]; then
    if [[ "$name" == "production-test" ]]; then
      capture_production_logs || true
    fi
    echo "verify.sh: ${name} failed with exit ${code}" | tee -a "${EVIDENCE}/summary.txt" >&2
    exit "$code"
  fi
}

reject_skips() {
  local logfile="$1"
  local scan
  scan="$(mktemp)"
  if ! python3 "${ROOT}/scripts/verify_report.py" scan "$logfile" >"$scan" 2>&1; then
    cat "$scan" | tee -a "$logfile" >&2
    rm -f "$scan"
    echo "verify.sh: skip or xfail in ${logfile}" | tee -a "${EVIDENCE}/summary.txt" >&2
    exit 1
  fi
  rm -f "$scan"
}

capture_production_logs() {
  step . production-logs <<'EOF'
mkdir -p ci/test-results
docker compose -f ci/compose.yaml -p mosscms-smoke logs --no-color > ci/test-results/containers.log 2>&1
EOF
}

start_postgres() {
  local logfile="${EVIDENCE}/postgres-container.txt"
  PG_CONTAINER="moss-verify-pg"
  docker rm -f "$PG_CONTAINER" >/dev/null 2>&1 || true
  {
    echo "label: local"
    echo "sha: ${SHA}"
    echo "image: postgres:17-alpine"
    echo "command: docker run --rm -d --name ${PG_CONTAINER} -e POSTGRES_USER=pg -e POSTGRES_PASSWORD=pgtestpw -e POSTGRES_DB=postgres -p 127.0.0.1:5432:5432 postgres:17-alpine"
    echo "---- output ----"
  } >"$logfile"
  echo "verify.sh: postgres-container" >&2
  if ! docker run --rm -d --name "$PG_CONTAINER" \
    -e POSTGRES_USER=pg \
    -e POSTGRES_PASSWORD=pgtestpw \
    -e POSTGRES_DB=postgres \
    -p 127.0.0.1:5432:5432 \
    postgres:17-alpine >>"$logfile" 2>&1; then
    echo "verify.sh: postgres container failed to start" | tee -a "${EVIDENCE}/summary.txt" >&2
    exit 1
  fi
  local ready=0 attempt
  for attempt in $(seq 1 60); do
    if docker exec "$PG_CONTAINER" pg_isready -U pg -d postgres >>"$logfile" 2>&1; then
      ready=1
      break
    fi
    sleep 1
  done
  docker exec "$PG_CONTAINER" postgres --version >>"$logfile" 2>&1 || true
  if [[ "$ready" -ne 1 ]]; then
    echo "verify.sh: postgres container did not become ready" | tee -a "${EVIDENCE}/summary.txt" >&2
    exit 1
  fi
  echo "postgres-container 0" >>"${EVIDENCE}/exit-codes.txt"
}

stop_postgres() {
  if [[ -n "${PG_CONTAINER}" ]]; then
    docker rm -f "$PG_CONTAINER" >/dev/null 2>&1 || true
    PG_CONTAINER=""
  fi
}

# Same commands as .github/workflows/checks.yml, in the ticket's order.
# Local evidence steps (pip-audit, plain npm audit, gitleaks, the throwaway
# Postgres container, and the required-run union check) sit with the group
# they belong to. Nothing here is an audit ignore or an allowlist.

step api uv-sync <<'EOF'
uv sync --locked --group dev
EOF

step api ruff <<'EOF'
uv run ruff check app tests migrations && uv run ruff format --check app tests migrations
EOF

step api ruff-scripts <<'EOF'
uv run ruff check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py
uv run ruff format --check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py
uv run ruff check --config pyproject.toml ../ci/telemetry_smoke.py
uv run ruff format --check --config pyproject.toml ../ci/telemetry_smoke.py
EOF

step api mypy <<'EOF'
uv run mypy app
EOF

{
  echo "ruff: $(cd "$ROOT/api" && uv run ruff --version)"
  echo "mypy: $(cd "$ROOT/api" && uv run mypy --version)"
} >>"${EVIDENCE}/versions.txt"

export MOSS_USE_SQLITE=false
export MOSS_REQUIRED_RUN=sqlite
step api pytest-sqlite <<'EOF'
uv run pytest -m "not postgres"
EOF
reject_skips "${EVIDENCE}/pytest-sqlite.txt"
unset MOSS_REQUIRED_RUN

start_postgres
export MOSS_REQUIRED_RUN=postgres
export MOSS_TEST_DATABASE_URL='postgresql+psycopg://pg:pgtestpw@localhost:5432/postgres'
step api pytest-postgres <<'EOF'
uv run pytest
EOF
reject_skips "${EVIDENCE}/pytest-postgres.txt"
unset MOSS_REQUIRED_RUN MOSS_TEST_DATABASE_URL MOSS_USE_SQLITE
stop_postgres

step api verify-required-runs <<'EOF'
uv run python tests/verify_required_runs.py
EOF

docker rm -f moss-otel-smoke >/dev/null 2>&1 || true
step api otel <<'EOF'
docker run --rm -d --name moss-otel-smoke \
  -p 127.0.0.1:14318:4318 -p 127.0.0.1:19464:9464 \
  -v "$GITHUB_WORKSPACE/ops/otel-collector.yaml:/etc/otelcol/config.yaml:ro" \
  otel/opentelemetry-collector-contrib:0.156.0@sha256:125bdbeb7590cc1952c5b3430ecf14063568980c2c93d5b38676cc0446ed8108 \
  --config=/etc/otelcol/config.yaml
trap 'docker rm -f moss-otel-smoke >/dev/null 2>&1 || true' EXIT
MOSS_USE_SQLITE=false PYTHONPATH=. uv run python ../ci/telemetry_smoke.py \
  --endpoint http://127.0.0.1:14318 --metrics-url http://127.0.0.1:19464/metrics \
  --output /tmp/moss-otel-evidence/collector-smoke.json
EOF

step web web-npm-ci <<'EOF'
npm ci
EOF

step web web <<'EOF'
npm run check && npm test && npm run build && npm audit --audit-level=high
EOF
reject_skips "${EVIDENCE}/web.txt"

step example-site example-site-npm-ci <<'EOF'
npm ci
EOF

step example-site example-site <<'EOF'
npm run check && npm test && npm run build && npm audit --audit-level=high
EOF
reject_skips "${EVIDENCE}/example-site.txt"

# pip-audit reads the locked requirements from api/uv.lock. No --ignore-vuln.
step api pip-audit <<'EOF'
uv export --frozen --all-groups --no-emit-project -o "$EVIDENCE/requirements.txt"
uv run --with pip-audit pip-audit --version
uv run --with pip-audit pip-audit --progress-spinner off -r "$EVIDENCE/requirements.txt"
EOF
(cd "$ROOT/api" && uv run --with pip-audit pip-audit --version) >>"${EVIDENCE}/versions.txt"

# Default npm audit: devDependencies stay included (no --omit=dev) and any advisory fails (no --audit-level).
step web npm-audit-web <<'EOF'
npm audit
EOF

step example-site npm-audit-example-site <<'EOF'
npm audit
EOF

step ci npm-audit-ci <<'EOF'
npm audit
EOF

# gitleaks on the tracked tree at HEAD. git archive is that checkout, so
# dependency installs and evidence written by this run stay out of scope.
# Walking history would still report a fixture removed from the tip, because
# that commit is already on main. No allowlist and no history rewrite.
step . gitleaks <<'EOF'
snapshot="$(mktemp -d)"
trap 'rm -rf "$snapshot"' EXIT
git archive HEAD | tar -x -C "$snapshot"
gitleaks detect --no-git --source "$snapshot" --redact=100 --no-banner --exit-code 1
EOF

step ci ci-npm-ci <<'EOF'
npm ci
EOF

step ci playwright-install <<'EOF'
npx playwright install --with-deps chromium
EOF

step . production-build <<'EOF'
docker build --tag mosscms:smoke .
EOF

PRODUCTION_STARTED=1
step . production-up <<'EOF'
docker compose -f ci/compose.yaml -p mosscms-smoke up --no-build -d --wait --wait-timeout 180
EOF

step ci production-test <<'EOF'
npm test
EOF
reject_skips "${EVIDENCE}/production-test.txt"

step . production-down <<'EOF'
docker compose -f ci/compose.yaml -p mosscms-smoke down --volumes
EOF
PRODUCTION_STARTED=""

python3 "${ROOT}/scripts/verify_report.py" counts "$EVIDENCE" >"${EVIDENCE}/counts.txt"
{
  echo "finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "result: passed"
} >>"${EVIDENCE}/summary.txt"
echo "verify.sh: passed ${EVIDENCE}" >&2
