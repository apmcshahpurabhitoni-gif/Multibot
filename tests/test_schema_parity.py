"""Guard the single database schema used by local SQLite and remote Turso."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DB_MODULE = ROOT / "db.py"

EXPECTED_TABLES = {
    "accounts",
    "trades",
    "signals",
    "signal_events",
    "deliveries",
    "scan_runs",
    "scan_error_alerts",
    "market_data_cache",
    "forex_calendar_week_cache",
    "forex_calendar_attempts",
    "multibot_migrations",
    "app_config",
    "runtime_leases",
}


def test_runtime_schema_declares_every_persistent_table():
    source = DB_MODULE.read_text(encoding="utf-8")
    declared = set(re.findall(
        r"CREATE TABLE IF NOT EXISTS ([a-z_][a-z0-9_]*)",
        source,
        re.IGNORECASE,
    ))
    assert declared == EXPECTED_TABLES


def test_runtime_has_no_supabase_rest_dependency():
    source = DB_MODULE.read_text(encoding="utf-8")
    assert "SUPABASE_URL" not in source
    assert "SUPABASE_KEY" not in source
    assert "_supabase_request" not in source


def test_turso_uses_the_same_sqlite_compatible_database_layer():
    source = DB_MODULE.read_text(encoding="utf-8")
    assert "import libsql" in source
    assert "libsql.connect(TURSO_DATABASE_URL,auth_token=TURSO_AUTH_TOKEN)" in source
    assert "sqlite3.connect(self.path,timeout=30)" in source
