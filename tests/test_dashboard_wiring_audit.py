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


def test_signal_history_restore_covers_signal_events_and_deliveries():
    source = (ROOT / "db.py").read_text(encoding="utf-8")
    assert '_restore_signal_events_if_needed()' in source
    assert '_restore_deliveries_if_needed()' in source
    assert 'signal_deliveries' in source
    assert 'if any(c.execute(f"SELECT 1 FROM {t} LIMIT 1")' not in source


def test_appearance_bridge_does_not_double_bind_existing_runtime_controls():
    source = (ROOT / "appearance.js").read_text(encoding="utf-8")
    assert 'themeToggle' not in source
    assert 'compactModeToggle' not in source
    assert 'reduceMotionToggle' not in source
    assert 'data-style-choice' in source
    assert 'appearanceBound' in source
