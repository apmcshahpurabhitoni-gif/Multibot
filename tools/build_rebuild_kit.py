"""Build a fresh, source-synchronized MULTIBOT2 AI rebuild kit ZIP."""
from __future__ import annotations

import argparse
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
STRATEGY_IDS = ("adaptive_trend", "engulfing_66_sma", "sweep_v2", "_template")

FILES = [
    ("README.md", "docs/KIT_README.md"),
    *[(f"docs/{name}", f"docs/{name}") for name in (
        "API.md", "THEME_SYSTEM.md", "LOCKED_RULES.md",
        "REBUILD_BRIEF.md", "LESSONS_LEARNED.md", "START_HERE.md",
    )],
    *[(f"docs/DESIGN_SYSTEM/{name}", f"docs/DESIGN_SYSTEM/{name}") for name in (
        "geometry.md", "type.md", "components.md", "motion.md", "icons.md", "validation.md",
    )],
    *[(f"reference/{name}", name) for name in (
        "AI_REBUILD_SPEC.md", "AI_CONTEXT.md", "STRATEGY_DEVELOPER_GUIDE.md", "DESIGN.md",
        "MANIFEST.txt", "schema.sql", "pyproject.toml",
    )],
    *[(f"guards/{name}", f"tests/{name}") for name in (
        "test_api_contract.py", "test_contrast_tokens.py", "test_frontend_syntax.py",
        "test_keepalive_health.py", "test_no_wall_clock_dependence.py", "test_rebuild_kit.py",
        "test_rebuild_spec_inventory.py", "test_schema_parity.py",
    )],
    ("reference/strategies/__init__.py", "strategies/__init__.py"),
    ("reference/strategies/base.py", "strategies/base.py"),
    ("reference/strategies/registry.py", "strategies/registry.py"),
]


def build_archive(output: str | Path) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    files = list(FILES)
    for strategy in STRATEGY_IDS:
        folder = f"strategies/{strategy}"
        files.append((f"reference/{folder}/strategy.py", f"{folder}/strategy.py"))
        init_path = ROOT / folder / "__init__.py"
        if init_path.is_file():
            files.append((f"reference/{folder}/__init__.py", f"{folder}/__init__.py"))

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for archive_name, source_name in files:
            source = ROOT / source_name
            if not source.is_file():
                raise FileNotFoundError(f"Required rebuild-kit source is missing: {source_name}")
            archive.write(source, f"multibot2-ai-rebuild-kit/{archive_name}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", default="multibot2-ai-rebuild-kit.zip",
        help="Output ZIP path (default: multibot2-ai-rebuild-kit.zip)",
    )
    args = parser.parse_args()
    output = build_archive(args.output)
    with zipfile.ZipFile(output) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"Corrupt ZIP entry: {bad}")
        print(f"Built {output} | files={len(archive.namelist())} | integrity=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
