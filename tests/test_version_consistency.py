"""Version drift guard.

release_notes.APP_VERSION is the single source of truth. Packaging metadata
and the shipped manifest drifted from it for several releases because nothing
asserted the equality, so the checks live here rather than only in the manual
tools/check_release_docs.py run.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from release_notes import APP_VERSION, RELEASE_HIGHLIGHTS


def test_pyproject_version_matches_release_notes():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M)
    assert match, "pyproject.toml does not declare a project version"
    assert match.group(1) == APP_VERSION


def test_manifest_declares_the_current_release():
    manifest = (ROOT / "MANIFEST.txt").read_text(encoding="utf-8")
    assert f"MULTIBOT2 v{APP_VERSION}" in manifest


def test_every_shipped_strategy_is_listed_in_the_manifest():
    """MANIFEST.txt shipped a 2-strategy list while 3 were registered.

    The names and versions are read from the live registry so the document
    cannot quietly go stale again. Only the shipped strategies are required:
    a strategy dropped into strategies/ is a local plugin, not part of the
    release manifest.
    """
    from strategies.registry import BUILTIN_STRATEGY_IDS, discover_strategies

    manifest = (ROOT / "MANIFEST.txt").read_text(encoding="utf-8")
    registry = discover_strategies()
    for strategy_id in BUILTIN_STRATEGY_IDS:
        strategy = registry.get(strategy_id)
        entry = f"{strategy.manifest.name} {strategy.manifest.version}"
        assert entry in manifest, f"MANIFEST.txt is missing strategy {entry!r}"


def test_release_docs_mirror_the_release_highlights():
    block = "\n".join(f"- {item}" for item in RELEASE_HIGHLIGHTS)
    for name in ("WHATS_NEW.md", "README.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert f"v{APP_VERSION}" in text, f"{name} does not mention v{APP_VERSION}"
        assert block in text, f"{name} release block is out of sync"
