import pandas as pd
import pytest

from config import RISK_PER_TRADE_INR, USD_TO_INR
from signal_gate import SignalGate, build_signal_identity
from strategies.base import Signal, Strategy, StrategyManifest
from trading import TradePlan, quantity_for_risk

IST = "Asia/Kolkata"

def _ts():
    return pd.Timestamp("2026-09-10T10:00:00", tz=IST)

def test_usd_quantity_converts_inr_risk():
    entry, stop = 100_000.0, 99_000.0
    qty = quantity_for_risk(entry, stop, fx_rate=USD_TO_INR)
    assert qty * abs(entry - stop) * USD_TO_INR == pytest.approx(RISK_PER_TRADE_INR)

def test_inr_quantity_preserves_locked_behavior():
    qty = quantity_for_risk(1000.0, 900.0, fx_rate=1.0)
    assert qty == pytest.approx(RISK_PER_TRADE_INR / 100.0)

def test_trade_planned_risk_is_inr():
    plan = TradePlan("x", "BUY", _ts(), 100.0, 90.0, 120.0, fx_rate=USD_TO_INR)
    assert plan.risk_per_unit_inr == pytest.approx(10.0 * USD_TO_INR)

def test_neutral_is_not_dispatchable():
    signal = Signal("Sweep V2", "1", "BTC-USD", "NEUTRAL", _ts(), "4H")
    assert not SignalGate().can_send(signal, now=_ts())

def test_signal_identity_is_canonical():
    signal = Signal("x", "1", "BTC-USD", "BUY", _ts(), "1D")
    assert build_signal_identity(signal) == SignalGate.signal_key(signal)

class _Strategy(Strategy):
    manifest = StrategyManifest("test", "Test", "1", "x", ("BTC-USD",), ("1D",), "x", {})
    def generate_signal(self, symbol, candles, *, now):
        return Signal("Test", "1", symbol, "BUY", now, "1D", entry=None, stop_loss=1, take_profit=2)

def test_directional_trade_plan_requires_entry():
    with pytest.raises(ValueError):
        _Strategy().build_trade_plan(_Strategy().generate_signal("BTC-USD", pd.DataFrame(), now=_ts()))
