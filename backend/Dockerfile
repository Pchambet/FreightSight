FROM python:3.13-slim AS base
# The venv lives outside /app so a dev bind mount of ./backend never shadows it.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /uvx /bin/
WORKDIR /app
# pg_dump/pg_restore for `python -m app.backup`, from Debian 13 (trixie), whose postgresql-client is
# version 17 — the same major as the server. pg_dump refuses a server newer than itself, so this pin
# has to move with the database.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-17 \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd -r app && useradd -r -g app app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev
ENV PATH="/opt/venv/bin:$PATH"
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s CMD python -c "import os,urllib.request as u;u.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT','8000')}/healthz\")"
CMD sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
