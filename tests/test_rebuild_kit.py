"""Guard the AI rebuild starter kit against the two ways it silently rots.

The kit is a copy of tracked repo files, so it has no build step to fail loudly.
Two defects shipped in its first build and neither raised an error:

1. ``reference/strategies/`` was flattened to ``<id>.py``. The repo is a package
   tree (``strategies/<id>/strategy.py``); the flat copy was byte-identical in
   content, so a rebuild from the kit would have produced a strategy layout that
   ``registry.discover_strategies()`` does not recognise.
2. The four reference contracts (``AI_REBUILD_SPEC.md`` and friends) live at the
   repository ROOT, not under ``docs/``. Copying them from ``docs/`` yields a kit
   that is missing four contracts and still builds cleanly.

Both are content defects that ``zipfile.testzip()`` cannot see. These tests
compare the shipped archive byte-for-byte against its sources.
"""
from __future__ import annotations

import filecmp
import io
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
KIT_ZIP = ROOT / "multibot2-ai-rebuild-kit.zip"
KIT_PREFIX = "multibot2-ai-rebuild-kit/"

# kit path -> repository path. Kept explicit on purpose: an inferred mapping is
# what produced the flattened strategies/ tree in the first place.
DOCS = (
    "API.md", "THEME_SYSTEM.md", "LOCKED_RULES.md", "REBUILD_BRIEF.md",
    "LESSONS_LEARNED.md", "START_HERE.md",
)
DESIGN_SYSTEM = ("geometry.md", "type.md", "components.md", "motion.md", "icons.md", "validation.md")
# Root-level, NOT under docs/ -- see module docstring.
REFERENCE_ROOT = ("AI_REBUILD_SPEC.md", "AI_CONTEXT.md", "STRATEGY_DEVELOPER_GUIDE.md", "DESIGN.md")
REFERENCE_FLAT = ("MANIFEST.txt", "schema.sql", "render.yaml", "pyproject.toml")
GUARDS = (
    "test_api_contract.py", "test_contrast_tokens.py", "test_frontend_syntax.py",
    "test_keepalive_health.py", "test_no_wall_clock_dependence.py", "test_rebuild_kit.py",
    "test_rebuild_spec_inventory.py", "test_schema_parity.py",
)
STRATEGY_IDS = ("adaptive_trend", "engulfing_66_sma", "sweep_v2", "_template")

EXPECTED_FILE_COUNT = 1 + len(DOCS) + len(DESIGN_SYSTEM) + len(REFERENCE_ROOT) + len(REFERENCE_FLAT) + len(GUARDS) + 10


@pytest.fixture(scope="module")
def archive() -> zipfile.ZipFile:
    if not KIT_ZIP.is_file():
        pytest.skip(f"{KIT_ZIP.name} is not built; rebuild it per docs/KIT_README.md")
    handle = zipfile.ZipFile(KIT_ZIP)
    bad = handle.testzip()
    assert bad is None, f"corrupt entry in {KIT_ZIP.name}: {bad}"
    return handle


@pytest.fixture(scope="module")
def payload(archive: zipfile.ZipFile) -> dict[str, bytes]:
    return {
        name[len(KIT_PREFIX):]: archive.read(name)
        for name in archive.namelist()
        if not name.endswith("/")
    }


def _source_bytes(relative: str) -> bytes:
    return (ROOT / relative).read_bytes()


def test_archive_has_a_single_top_level_directory(archive: zipfile.ZipFile):
    roots = {name.split("/")[0] for name in archive.namelist()}
    assert roots == {"multibot2-ai-rebuild-kit"}, (
        f"kit must unzip into exactly one folder, found {sorted(roots)}"
    )


def test_archive_file_count_is_exact(payload):
    assert len(payload) == EXPECTED_FILE_COUNT, (
        f"expected {EXPECTED_FILE_COUNT} kit files, found {len(payload)}"
    )


def test_generated_architecture_html_is_excluded(payload):
    """819KB of generated HTML is not a rebuild input and bloats every handoff."""
    leaked = [name for name in payload if name.startswith("docs/architecture/")]
    assert not leaked, f"docs/architecture/ must stay out of the kit: {leaked}"


def test_no_bytecode_or_cache_leaked(payload):
    junk = [n for n in payload if "__pycache__" in n or n.endswith(".pyc")]
    assert not junk, f"bytecode leaked into the kit: {junk}"


def test_readme_is_the_kit_readme(payload):
    assert payload["README.md"] == _source_bytes("docs/KIT_README.md")


def test_contract_docs_match_source(payload):
    for name in DOCS:
        assert payload[f"docs/{name}"] == _source_bytes(f"docs/{name}"), f"docs/{name} is stale in the kit"
    for name in DESIGN_SYSTEM:
        assert payload[f"docs/DESIGN_SYSTEM/{name}"] == _source_bytes(f"docs/DESIGN_SYSTEM/{name}"), (
            f"docs/DESIGN_SYSTEM/{name} is stale in the kit"
        )


def test_reference_contracts_are_present_and_current(payload):
    """Regression: these four were copied from docs/ and silently omitted."""
    for name in REFERENCE_ROOT:
        key = f"reference/{name}"
        assert key in payload, f"{key} is missing from the kit"
        assert payload[key] == _source_bytes(name), f"{key} is stale in the kit"


def test_deploy_and_manifest_files_match_source(payload):
    for name in REFERENCE_FLAT:
        assert payload[f"reference/{name}"] == _source_bytes(name), f"reference/{name} is stale in the kit"


def test_guards_match_the_tests_they_copied(payload):
    for name in GUARDS:
        assert payload[f"guards/{name}"] == _source_bytes(f"tests/{name}"), (
            f"guards/{name} has drifted from tests/{name}"
        )


def test_strategies_keep_the_repository_package_layout(payload):
    """Regression: the kit shipped strategies/<id>.py instead of a package tree."""
    flat = [n for n in payload if n.startswith("reference/strategies/") and n.count("/") == 2 and n.endswith(".py")
            and Path(n).stem in STRATEGY_IDS]
    assert not flat, (
        "reference/strategies/ was flattened; the repo layout is "
        f"strategies/<id>/strategy.py, found {sorted(flat)}"
    )

    for name in ("__init__.py", "base.py", "registry.py"):
        key = f"reference/strategies/{name}"
        assert key in payload, f"{key} is missing from the kit"
        assert payload[key] == _source_bytes(f"strategies/{name}"), f"{key} has drifted from strategies/{name}"

    for strategy in STRATEGY_IDS:
        key = f"reference/strategies/{strategy}/strategy.py"
        assert key in payload, f"{key} is missing from the kit"
        assert payload[key] == _source_bytes(f"strategies/{strategy}/strategy.py"), (
            f"{key} has drifted from strategies/{strategy}/strategy.py"
        )
        init = f"reference/strategies/{strategy}/__init__.py"
        source_init = ROOT / "strategies" / strategy / "__init__.py"
        if source_init.is_file():
            assert init in payload, f"{init} is missing from the kit"
            assert payload[init] == source_init.read_bytes(), f"{init} has drifted"


def test_kit_readme_documents_the_rebuild_recipe():
    readme = (ROOT / "docs" / "KIT_README.md").read_text(encoding="utf-8")
    assert "Rebuilding this kit" in readme, "KIT_README must ship the rebuild recipe"
    # The recipe is only useful if its paths are right. These two mistakes are
    # the ones that produced a broken kit with no error.
    assert "cp AI_REBUILD_SPEC.md" in readme, (
        "the reference contracts live at the repo root; a docs/ path is wrong"
    )
    assert "strategies/$d/strategy.py" in readme, "the recipe must copy strategies as a package tree"
    assert "diff -r strategies" in readme, "the recipe must include the diff that catches a flattened tree"
