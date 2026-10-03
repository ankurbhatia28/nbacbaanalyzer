"""
Architecture tests.

These enforce ADR-001 at the repo level: the rules engine must never reach for
a language model. A unit test is a weaker guard than the CI grep, but it fails
locally and immediately, which is where you want to find this.
"""

from __future__ import annotations

import ast
import pathlib
import re
import subprocess

import pytest

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
    for pkg in ("engine", "data", "rag", "agent"):
        assert (REPO / "packages" / pkg / "pyproject.toml").is_file(), f"missing {pkg}"


# -- the division ADR-001 actually draws ---------------------------------

MODEL_CLIENTS = {"anthropic", "openai", "cohere", "voyageai", "litellm"}

LLM_FREE_PACKAGES = ("engine", "data", "rag")
"""
Packages whose answers must be reproducible with no API key present.

`agent` is deliberately absent: it is the one package allowed a model client,
which is the reason it exists separately at all. Stating that here means adding
a fifth package forces a decision rather than inheriting an exemption.
"""


def _imported_modules(path: pathlib.Path) -> set[str]:
    """Top-level modules a file imports, via the AST rather than a pattern."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


@pytest.mark.parametrize("package", LLM_FREE_PACKAGES)
def test_no_deterministic_package_imports_a_model_client(package: str) -> None:
    """
    Wider than the regex above in two ways: it covers the data and retrieval
    layers as well as the engine, and it parses imports instead of matching
    text, so an import written inside a function body is caught too.
    """
    sources = sorted((REPO / "packages" / package / "src").rglob("*.py"))
    assert sources, f"no sources found for {package}"
    for path in sources:
        offenders = _imported_modules(path) & MODEL_CLIENTS
        assert not offenders, f"{path.relative_to(REPO)} imports {offenders} (ADR-001)"


def test_the_api_reaches_a_model_only_through_the_agent() -> None:
    """
    `apps/api` is a transport. A model client imported there would be a second
    place model calls happen, outside the loop that audits their output.
    """
    sources = sorted((REPO / "apps" / "api" / "src").rglob("*.py"))
    assert sources, "no sources found for apps/api"
    for path in sources:
        offenders = _imported_modules(path) & MODEL_CLIENTS
        assert not offenders, f"{path.relative_to(REPO)} imports {offenders} (ADR-001)"


def test_the_engine_does_not_depend_on_where_figures_came_from() -> None:
    """
    The engine is the rules. Importing the data or retrieval layers would make
    it impossible to test a rule without a database.
    """
    for path in sorted(ENGINE_SRC.rglob("*.py")):
        imported = _imported_modules(path)
        assert "nbadata" not in imported, f"{path.relative_to(REPO)} imports nbadata"
        assert "rag" not in imported, f"{path.relative_to(REPO)} imports rag"


def test_no_env_file_is_tracked_except_the_example() -> None:
    """
    CLAUDE.md: no `.env` is ever tracked except `.env.example`. The real file
    holds the Anthropic and Raindrop keys.
    """
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    env_files = [name for name in tracked if pathlib.Path(name).name.startswith(".env")]
    assert env_files in ([], [".env.example"]), f"tracked env files: {env_files}"


def test_adrs_present() -> None:
    adrs = sorted((REPO / "docs" / "adr").glob("*.md"))
    assert len(adrs) >= 3, "the three founding ADRs should be committed"
