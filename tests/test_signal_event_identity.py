from datetime import datetime, timezone
from types import SimpleNamespace

from db import DatabaseManager


def _signal():
    return SimpleNamespace(
        strategy="Sweep V2",
        version="1.0",
        symbol="BTC-USD",
        direction="BUY",
        timestamp=datetime(2026, 9, 11, 12, tzinfo=timezone.utc),
        timeframe="4H",
        reason="TEST",
        metadata={},
    )


def test_signal_event_is_one_row_per_canonical_key(tmp_path):
    db = DatabaseManager(str(tmp_path / "state.db"))
    signal = _signal()
    first = db.record_signal_event("first", "canonical-key", signal, pipeline_status="GENERATED")
    second = db.record_signal_event("second", "canonical-key", signal, pipeline_status="READY")
    rows = db.load_signal_history()
    assert first == second
    assert len(rows) == 1
    assert rows[0]["signal_id"] == first
    assert rows[0]["pipeline_status"] == "READY"
