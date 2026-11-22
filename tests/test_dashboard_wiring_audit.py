from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_history_has_live_trade_and_scan_surfaces():
    html = (ROOT / "dashboard.html").read_text(encoding="utf-8")
    bridge = (ROOT / "dashboard-live-wiring.js").read_text(encoding="utf-8")
    assert 'id="historyOpenTrades"' in html
    assert 'id="historyScanHistory"' in html
    assert 'dashboard-live-wiring.js' in html
    assert 'data.style' not in bridge
    assert '/api/dashboard' in bridge
    assert 'status||""' in bridge


def test_dashboard_trade_serializer_preserves_operational_fields():
    source = (ROOT / "dashboard.py").read_text(encoding="utf-8")
    for token in (
        '"symbol":getattr(t,"symbol",None)',
        '"account":getattr(t,"account",None)',
        '"qty":t.quantity',
        '"planned_risk":t.planned_risk',
        '"opened_at":',
        '"closed_at":',
        '"pnl":getattr(t,"pnl",None)',
        '"exit_reason":t.exit_reason',
    ):
        assert token in source


def test_signal_history_and_deliveries_use_the_durable_database():
    source = (ROOT / "db.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS signal_events" in source
    assert "CREATE TABLE IF NOT EXISTS deliveries" in source
    assert "def load_signal_history" in source
    assert "def delivery_status" in source
    assert "libsql.connect(TURSO_DATABASE_URL,auth_token=TURSO_AUTH_TOKEN)" in source
    assert "_supabase_request" not in source


def test_appearance_bridge_does_not_double_bind_existing_runtime_controls():
    source = (ROOT / "appearance.js").read_text(encoding="utf-8")
    assert 'themeToggle' not in source
    assert 'compactModeToggle' not in source
    assert 'reduceMotionToggle' not in source
    assert 'data-style-choice' in source
    assert 'appearanceBound' in source
