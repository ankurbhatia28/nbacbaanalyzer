"""
The deployed process. Locally:

    uv run --env-file .env uvicorn api.main:app --port 8000

Nothing here reads `.env` itself -- `--env-file` is what loads it. Without it
the process stops at startup with "ANTHROPIC_API_KEY is not set" even though
the key is in the file. A deployment sets these as platform env vars (8.5).

Configuration comes from the environment, and everything that can be wrong is
checked at startup rather than on the first question -- a missing artifact or
key should stop the process, not produce a 500 for whoever asks first.

    NBACBA_LEAGUE_DB        league database   (default build/nbacba.db)
    NBACBA_CBA_INDEX        retrieval index   (default build/cba-index.db)
    NBACBA_ALLOWED_ORIGINS  comma-separated origins for the web app's CORS;
                            unset in development, the local web app's
                            http://localhost:3000
    NBACBA_ENVIRONMENT      trace environment (default development)
    ANTHROPIC_API_KEY       required
    LANGFUSE_*              optional; traces go to Langfuse when set (D16)
    TRACE_ENABLED, TRACE_EXPORT_DIR
                            the local JSONL copy of every trace (6.10a)

Build the two artifacts with:

    uv run python -m nbadata.ingest.load --out build/nbacba.db
    uv run python -m rag --out build/cba-index.db
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from fastapi import FastAPI

from agent import langfuse_export
from agent.budget import ANTHROPIC_PRICES, Budget
from agent.llm import AnthropicCaller
from agent.tools import Resources
from agent.trace import CappedExporter, Exporter, FileExporter, NullExporter
from nbadata.db import open_readonly
from rag import index as ix

from .app import Service, create_app
from .origins import allowed_origins

BASE_SEASON = "2023-2024"
"""The season the Expanded exception's growth factor is measured from."""


class ConfigError(RuntimeError):
    pass


def _artifact(variable: str, default: str) -> Path:
    path = Path(os.environ.get(variable, default))
    if not path.is_file():
        raise ConfigError(
            f"{variable}: no file at {path}. Build it first -- see the api.main docstring."
        )
    return path


def resources() -> Resources:
    league = open_readonly(_artifact("NBACBA_LEAGUE_DB", "build/nbacba.db"))
    cba = ix.open_index(_artifact("NBACBA_CBA_INDEX", "build/cba-index.db"))
    # Read from the database rather than written here, so the figure has one
    # source; and read now, so a database without it fails at startup.
    row = league.execute(
        "SELECT salary_cap FROM seasons WHERE season_id = ?", (BASE_SEASON,)
    ).fetchone()
    if row is None:
        raise ConfigError(f"the league database has no {BASE_SEASON} salary cap")
    return Resources(league=league, cba=cba, base_season_cap=int(row[0]))


def exporter(budget: Budget) -> Exporter:
    inner: Exporter
    if langfuse_export.configured():
        # Keys without the SDK would drop every trace in silence: tracing
        # degrades per trace by design (6.13), so nothing else would say so.
        # The first deploy shipped exactly this (8.5).
        if importlib.util.find_spec("langfuse") is None:
            raise ConfigError(
                "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set but the langfuse "
                "package is not installed; install the agent's `langfuse` extra."
            )
        inner = langfuse_export.LangfuseExporter()
    elif os.environ.get("TRACE_ENABLED", "true").lower() == "true":
        directory = Path(os.environ.get("TRACE_EXPORT_DIR", "traces"))
        inner = FileExporter(directory / "api.jsonl")
    else:
        inner = NullExporter()
    # The free tier's allowance binds however traces are stored (6.13).
    return CappedExporter(inner, max_units=budget.max_trace_units)


def build() -> FastAPI:
    budget = Budget(prices=ANTHROPIC_PRICES)
    environment = os.environ.get("NBACBA_ENVIRONMENT", "development")
    service = Service(
        res=resources(),
        caller=AnthropicCaller(),
        budget=budget,
        exporter=exporter(budget),
        environment=environment,
    )
    return create_app(service, allowed_origins=allowed_origins(environment))


app = build()
