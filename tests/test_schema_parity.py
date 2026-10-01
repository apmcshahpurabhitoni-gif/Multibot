"""Guard against persistence-schema drift.

The repository historically carried two independent copies of the Supabase DDL:
``schema.sql`` at the root and ``supabase/schema.sql``. They drifted, and the
Supabase copy silently dropped ``scan_runs`` and ``market_data_cache`` even
though ``db.py`` writes to both through the Supabase REST API. ``db.py`` guards
that failure with a ``PGRST205`` check, so the breakage was invisible: the bot
kept running on the SQLite fallback while scan history silently stopped
persisting remotely.

These tests make the invariant explicit and permanent.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_SCHEMA = ROOT / "schema.sql"
SUPABASE_SCHEMA = ROOT / "supabase" / "schema.sql"
DB_MODULE = ROOT / "db.py"

CREATE_TABLE = re.compile(
    r"create\s+table\s+if\s+not\s+exists\s+(?:public\.)?([a-z_][a-z0-9_]*)",
    re.IGNORECASE,
)
SUPABASE_REQUEST = re.compile(
    r"_supabase_request\(\s*[\"'](?:GET|POST|PATCH|DELETE|PUT)[\"']\s*,\s*[\"']([a-z_][a-z0-9_]*)[\"']"
)

# Every table the persistence layer is allowed to address remotely.
EXPECTED_TABLES = {
    "accounts",
    "active_trades",
    "closed_trades",
    "market_data_cache",
    "scan_runs",
    "sent_signals",
    "signal_deliveries",
    "signal_events",
}


def _tables(path: Path) -> set[str]:
    assert path.is_file(), f"missing schema file: {path}"
    return {match.lower() for match in CREATE_TABLE.findall(path.read_text(encoding="utf-8"))}


def _runtime_tables() -> set[str]:
    source = DB_MODULE.read_text(encoding="utf-8")
    return {match.lower() for match in SUPABASE_REQUEST.findall(source)}


def test_both_schema_files_exist():
    assert ROOT_SCHEMA.is_file()
    assert SUPABASE_SCHEMA.is_file()


def test_schema_files_declare_identical_tables():
    """The two DDL copies are a mirror, never two sources of truth."""
    root_tables = _tables(ROOT_SCHEMA)
    supabase_tables = _tables(SUPABASE_SCHEMA)
    assert root_tables == supabase_tables, (
        "schema drift: "
        f"only in schema.sql -> {sorted(root_tables - supabase_tables)}; "
        f"only in supabase/schema.sql -> {sorted(supabase_tables - root_tables)}"
    )


def test_schema_files_cover_every_expected_table():
    for path in (ROOT_SCHEMA, SUPABASE_SCHEMA):
        missing = EXPECTED_TABLES - _tables(path)
        assert not missing, f"{path.name} does not create: {sorted(missing)}"


def test_schema_files_cover_every_table_the_runtime_calls():
    """Catches the exact drift class that broke scan_runs and the Yahoo cache."""
    called = _runtime_tables()
    assert called, "no Supabase calls detected in db.py; parser needs updating"
    for path in (ROOT_SCHEMA, SUPABASE_SCHEMA):
        undeclared = called - _tables(path)
        assert not undeclared, (
            f"db.py writes to tables that {path.name} never creates: {sorted(undeclared)}"
        )


def test_runtime_tables_match_expected_inventory():
    """If this fails, either a table was added or removed; update EXPECTED_TABLES."""
    assert _runtime_tables() == EXPECTED_TABLES