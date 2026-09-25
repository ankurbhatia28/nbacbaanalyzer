"""
Architecture tests.

These enforce ADR-001 at the repo level: the rules engine must never reach for
a language model. A unit test is a weaker guard than the CI grep, but it fails
locally and immediately, which is where you want to find this.
"""

from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[1]
ENGINE_SRC = REPO / "packages" / "engine" / "src"

LLM_IMPORT = re.compile(
    r"^\s*(?:import\s+(?:anthropic|openai)|from\s+(?:anthropic|openai)\b)", re.MULTILINE
)


def test_engine_imports_no_llm_client() -> None:
    offenders = [
        path.relative_to(REPO)
        for path in ENGINE_SRC.rglob("*.py")
        if LLM_IMPORT.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"packages/engine must not import an LLM client (ADR-001): {offenders}"


def test_expected_packages_exist() -> None:
    for pkg in ("engine", "data", "rag"):
        assert (REPO / "packages" / pkg / "pyproject.toml").is_file(), f"missing {pkg}"


def test_adrs_present() -> None:
    adrs = sorted((REPO / "docs" / "adr").glob("*.md"))
    assert len(adrs) >= 3, "the three founding ADRs should be committed"
