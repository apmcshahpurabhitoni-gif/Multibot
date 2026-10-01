"""Verify every declared version mirrors the canonical release source.

release_notes.APP_VERSION is the single source of truth. The packaging
metadata drifted from it for several releases because nothing checked it.
"""
from __future__ import annotations
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from release_notes import APP_VERSION, RELEASE_HIGHLIGHTS


def expected_block() -> str:
    return "\n".join(f"- {item}" for item in RELEASE_HIGHLIGHTS)

def declared_version(path: Path, pattern: str) -> str | None:
    match = re.search(pattern, path.read_text(encoding="utf-8"), re.M)
    return match.group(1) if match else None

def main() -> int:
    errors = []
    whats = (ROOT / "WHATS_NEW.md").read_text(encoding="utf-8")
    if f"v{APP_VERSION}" not in whats or expected_block() not in whats:
        errors.append("WHATS_NEW.md is out of sync with release_notes.py")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if f"## 🆕 What's New — v{APP_VERSION}" not in readme or expected_block() not in readme:
        errors.append("README.md release block is out of sync with release_notes.py")
    # The published package version and the shipped file manifest must agree
    # with the runtime version, not just with the markdown release notes.
    packaged = declared_version(ROOT / "pyproject.toml", r'^version\s*=\s*"([^"]+)"')
    if packaged != APP_VERSION:
        errors.append(f"pyproject.toml version {packaged!r} != release_notes.py {APP_VERSION!r}")
    manifest = (ROOT / "MANIFEST.txt").read_text(encoding="utf-8")
    if f"MULTIBOT2 v{APP_VERSION}" not in manifest:
        errors.append(f"MANIFEST.txt does not declare MULTIBOT2 v{APP_VERSION}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Release documentation is in sync with MULTIBOT2 v{APP_VERSION}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
