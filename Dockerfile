# The API as deployed on Render (task 8.3). Built by render.yaml; runs locally
# the same way:
#
#   docker build -t nbacba-api .
#   docker run --rm -p 8000:8000 --env-file .env nbacba-api
#
# Two stages. The first does what CI's `artifacts` job does -- fetch the CBA PDF
# and check it against the pinned hash (D20), then build the league database
# and the retrieval index (8.1) -- so the deployed artifacts are rebuilt from
# source on every deploy and never committed (ADR-004). The second keeps only
# what the running API reads: the virtualenv, the package sources it imports,
# and the two databases. The PDF and the scraper output stay behind.

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY . .
# The langfuse extra: without it, keys set on Render select the Langfuse
# exporter and every trace is dropped on import (found in 8.5).
RUN uv sync --frozen --all-packages --no-dev --extra langfuse
RUN uv run --no-sync python -m rag.fetch \
 && uv run --no-sync python -m nbadata.ingest.load --out build/nbacba.db \
 && uv run --no-sync python -m rag --out build/cba-index.db

FROM python:3.12-slim
WORKDIR /app
# Editable installs: the virtualenv points at these source directories.
COPY --from=build /app/.venv .venv
COPY --from=build /app/packages packages
COPY --from=build /app/apps/api apps/api
COPY --from=build /app/build build
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    NBACBA_LEAGUE_DB=/app/build/nbacba.db \
    NBACBA_CBA_INDEX=/app/build/cba-index.db
# The databases are read-only at runtime (ADR-004); so is everything else.
RUN useradd --no-create-home app
USER app
# Render sets PORT; 8000 locally.
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
