FROM python:3.13-slim

# uv for fast, reproducible installs (lockfile)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies first (cache-friendly layer)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --frozen --no-install-project

# Source code + logo
COPY src/ src/
COPY docs/assets/logo.png docs/assets/logo.png
RUN uv sync --no-dev --frozen

# Unprivileged user; /data is where the SQLite databases live (mounted volume)
RUN useradd --system --uid 10001 --home /app argos \
    && mkdir -p /data && chown -R argos:argos /data
USER argos

ENV RADAR_DB_PATH=/data/radar.db \
    RADAR_INDICADORES_DB=/data/indicadores.db

EXPOSE 8061

# The venv is first in PATH: "python" here (and in `docker compose exec argos python ...`)
# already has every dependency, with no extra "uv run" process in memory
CMD ["python", "-c", "from mcp_brasil.server import mcp; mcp.run(transport='streamable-http', host='0.0.0.0', port=8061)"]
