FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS web-build
WORKDIR /web
COPY shared/ /shared/
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
ARG VITE_GRAPHQL_URL=/graphql
ENV VITE_GRAPHQL_URL=${VITE_GRAPHQL_URL}
RUN npm run check && npm run build

FROM python:3.12-slim@sha256:02108f5d322dd89f1c9e552442c25acb0543dfdbc455693a5599624f20d9155d AS api-deps
WORKDIR /api
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv
RUN pip install --no-cache-dir uv==0.12.23
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

FROM python:3.12-slim@sha256:02108f5d322dd89f1c9e552442c25acb0543dfdbc455693a5599624f20d9155d AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH="/app/.venv/bin:$PATH" PORT=8001 MOSS_STORAGE_DIR=/data
WORKDIR /app
RUN useradd --create-home --uid 10001 appuser && mkdir /data && chown appuser:appuser /data
COPY --from=api-deps /app/.venv /app/.venv
COPY api/app ./app
COPY api/migrations ./migrations
COPY api/alembic.ini ./alembic.ini
COPY shared/ /shared/
COPY --from=web-build /web/dist ./static
USER appuser
EXPOSE 8001
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/ready', timeout=3)"
CMD ["python", "-m", "app.cli", "serve"]
