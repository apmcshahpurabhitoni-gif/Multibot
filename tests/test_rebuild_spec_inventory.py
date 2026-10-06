"""Completeness guard for the AI reconstruction contract.

``AI_REBUILD_SPEC.md`` is the document a rebuild is driven from. It had drifted:
section 25 listed 17 of the root modules, and omitted ``strategies/engulfing_66_sma/``
entirely, so a rebuild faithfully following it would have shipped an incomplete bot.

These tests pin the spec to the repository and to the live registry so the gap
cannot reopen.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from release_notes import APP_VERSION

SPEC = ROOT / "AI_REBUILD_SPEC.md"
PYPROJECT = ROOT / "pyproject.toml"


def _spec_text() -> str:
    return SPEC.read_text(encoding="utf-8")


def test_spec_exists_and_targets_the_current_release():
    text = _spec_text()
    assert "AI REBUILD SPECIFICATION" in text
    assert f"v{APP_VERSION}" in text, f"AI_REBUILD_SPEC.md does not declare v{APP_VERSION}"


def test_spec_names_every_root_module():
    """Section 25 must account for all root modules."""
    text = _spec_text()
    missing = sorted(
        path.stem for path in ROOT.glob("*.py") if path.stem not in text
    )
    assert not missing, f"AI_REBUILD_SPEC.md never mentions these modules: {missing}"


def test_spec_names_every_shipped_strategy_package():
    """Docs inventory covers the *shipped* strategies.

    A strategy dropped into strategies/ is registered automatically but is not
    part of the shipped contract, so it does not have to be in the rebuild
    spec. The three that ship must be.
    """
    from strategies.registry import BUILTIN_STRATEGY_IDS

    text = _spec_text()
    packages = sorted(
        path.parent.name
        for path in (ROOT / "strategies").glob("*/strategy.py")
        if path.parent.name != "_template"
    )
    assert packages, "no strategy packages discovered"
    missing = [name for name in BUILTIN_STRATEGY_IDS if name not in text]
    assert not missing, f"AI_REBUILD_SPEC.md omits shipped strategy packages: {missing}"
    # A dropped-in plugin must still be a real package, not a stray file.
    extra = [name for name in packages if name not in BUILTIN_STRATEGY_IDS]
    for name in extra:
        assert (ROOT / "strategies" / name / "__init__.py").is_file(), (
            f"{name} is discovered as a package but has no __init__.py"
        )


def test_spec_strategy_inventory_matches_the_live_registry():
    """Section 30 must list every shipped strategy with its exact version."""
    from strategies.registry import BUILTIN_STRATEGY_IDS, discover_strategies

    text = _spec_text()
    registry = discover_strategies()
    assert set(BUILTIN_STRATEGY_IDS) <= set(registry.ids())
    for strategy_id in BUILTIN_STRATEGY_IDS:
        strategy = registry.get(strategy_id)
        assert strategy.manifest.name in text, f"spec omits strategy {strategy.manifest.name}"
        assert strategy.manifest.version in text, (
            f"spec omits version {strategy.manifest.version} for {strategy.manifest.name}"
        )
        assert strategy.manifest.id in text, f"spec omits strategy id {strategy.manifest.id}"


def test_spec_names_the_real_registry_entrypoint():
    """`discover_strategies()` is the only entry point; the spec must name it.

    Asserted positively rather than by banning a name, because the spec is
    allowed to state that no hand-built registry exists.
    """
    import strategies.registry as registry

    assert hasattr(registry, "discover_strategies")
    assert not hasattr(registry, "build_default_registry")
    assert "discover_strategies()" in _spec_text()


def test_pyproject_declares_every_root_module():
    """Packaging drift: `startup.py` was missing from py-modules while
    render.yaml runs `python startup.py`, so a wheel install would not ship it."""
    declared = set(
        re.findall(
            r'"([a-z_0-9]+)"',
            re.search(
                r"py-modules\s*=\s*\[(.*?)\]", PYPROJECT.read_text(encoding="utf-8"), re.S
            ).group(1),
        )
    )
    actual = {path.stem for path in ROOT.glob("*.py")}
    assert declared == actual, (
        f"pyproject py-modules is missing {sorted(actual - declared)} "
        f"and lists absent {sorted(declared - actual)}"
    )