# CareerPilot AI backend — production image (docs/DEPLOYMENT.md §4). No Playwright, no embedded Postgres.
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-group local --no-install-project

FROM python:3.12-slim
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY --chown=app:app . .
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 APP_ENV=production PORT=8000
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/v1/health')" || exit 1
ENTRYPOINT ["./docker-entrypoint.sh"]
