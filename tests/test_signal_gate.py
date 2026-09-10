import pandas as pd
import pytest

from signal_gate import SignalGate, build_signal_identity, signal_status
from strategies.base import Signal


def make_signal(direction="BUY", timestamp="2026-08-31 10:15:00+05:30"):
    return Signal(
        "Adaptive Trend Momentum", "1.0.0", "BTC-USD", direction,
        pd.Timestamp(timestamp), "1D", "TEST", 100, 98, 104, {},
    )


def test_gate_is_stateless_and_directional_only():
    gate = SignalGate()
    now = pd.Timestamp("2026-08-31 11:00:00+05:30")
    assert gate.can_send(make_signal("BUY"), symbol="BTC-USD", now=now)
    assert not gate.can_send(make_signal("NEUTRAL"), symbol="BTC-USD", now=now)
    assert not gate.can_send(make_signal("NO_SIGNAL"), symbol="BTC-USD", now=now)


def test_identity_is_canonical():
    signal = make_signal()
    assert build_signal_identity(signal, symbol=" btc-usd ") == build_signal_identity(signal)


def test_status_and_future_timestamp_rules():
    signal = make_signal()
    assert signal_status(signal, now=pd.Timestamp("2026-08-31 11:00:00+05:30"))[0] == "FRESH"
    with pytest.raises(ValueError):
        signal_status(signal, now=pd.Timestamp("2026-08-31 10:00:00+05:30"))
