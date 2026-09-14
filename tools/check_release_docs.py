"""Verify release documentation mirrors the canonical release source."""
from __future__ import annotations
from pathlib import Path
from release_notes import APP_VERSION, RELEASE_HIGHLIGHTS

ROOT = Path(__file__).resolve().parents[1]

def expected_block() -> str:
    return "\n".join(f"- {item}" for item in RELEASE_HIGHLIGHTS)

def main() -> int:
    errors = []
    whats = (ROOT / "WHATS_NEW.md").read_text(encoding="utf-8")
    if f"v{APP_VERSION}" not in whats or expected_block() not in whats:
        errors.append("WHATS_NEW.md is out of sync with release_notes.py")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if f"## 🆕 What's New — v{APP_VERSION}" not in readme or expected_block() not in readme:
        errors.append("README.md release block is out of sync with release_notes.py")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Release documentation is in sync with MULTIBOT2 v{APP_VERSION}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
