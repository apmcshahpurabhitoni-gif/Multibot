import pandas as pd

from strategies.base import Signal, Strategy, StrategyManifest
from strategy_engine import StrategyEngine


class PreparedStrategy(Strategy):
    manifest = StrategyManifest(
        id="prepared",
        name="Prepared",
        version="1",
        description="test",
        assets=("X",),
        timeframes=("1D",),
        schedule="test",
        parameters={},
    )

    def prepare_candles(self, symbol, candles, *, now):
        return candles.iloc[:-1]

    def generate_signal(self, symbol, candles, *, now):
        return Signal(
            self.manifest.name,
            self.manifest.version,
            symbol,
            "NO_SIGNAL",
            candles.index[-1],
            "1D",
            str(len(candles)),
        )


def test_backtest_uses_prepare_candles():
    index = pd.date_range("2026-01-01", periods=3, freq="D", tz="Asia/Kolkata")
    frame = pd.DataFrame(
        {"open":[1,2,3], "high":[1,2,3], "low":[1,2,3], "close":[1,2,3]},
        index=index,
    )
    signal = PreparedStrategy().backtest_signal("X", frame, now=index[-1])
    assert signal.reason == "2"


class DefaultGateStrategy(Strategy):
    """A strategy that only implements generate_signal — no prepare override."""
    manifest = StrategyManifest(
        id="default_gate",
        name="Default Gate",
        version="1",
        description="test",
        assets=("X",),
        timeframes=("1h",),
        schedule="test",
        parameters={},
    )
    seen: pd.DataFrame | None = None

    def generate_signal(self, symbol, candles, *, now):
        DefaultGateStrategy.seen = candles
        return Signal(
            self.manifest.name, self.manifest.version, symbol,
            "NO_SIGNAL", candles.index[-1], self.manifest.timeframes[0],
            str(len(candles)),
        )


def _hourly_frame(last_label: pd.Timestamp, *, periods: int = 5) -> pd.DataFrame:
    index = pd.date_range(end=last_label, periods=periods, freq="h", tz="Asia/Kolkata")
    return pd.DataFrame(
        {"open": range(periods), "high": range(periods),
         "low": range(periods), "close": range(periods)},
        index=index,
    )


def test_default_prepare_drops_an_in_progress_candle():
    """Rule 11: a strategy with no prepare override still never sees the
    candle that is still forming."""
    now = pd.Timestamp("2026-01-01 12:30", tz="Asia/Kolkata")
    frame = _hourly_frame(pd.Timestamp("2026-01-01 12:00", tz="Asia/Kolkata"))
    prepared = DefaultGateStrategy().prepare_candles("X", frame, now=now)
    assert len(prepared) == len(frame) - 1
    assert prepared.index[-1] < frame.index[-1]


def test_default_prepare_keeps_a_completed_candle():
    now = pd.Timestamp("2026-01-01 12:30", tz="Asia/Kolkata")
    # Last bar closed two hours before now: provably complete.
    frame = _hourly_frame(pd.Timestamp("2026-01-01 10:00", tz="Asia/Kolkata"))
    prepared = DefaultGateStrategy().prepare_candles("X", frame, now=now)
    assert len(prepared) == len(frame)


def test_default_prepare_drops_todays_daily_bar():
    strategy = DefaultGateStrategy()
    object.__setattr__(strategy, "manifest", StrategyManifest(
        id="default_gate_daily", name="Default Gate Daily", version="1",
        description="test", assets=("X",), timeframes=("1D",),
        schedule="test", parameters={},
    ))
    now = pd.Timestamp("2026-01-02 12:00", tz="Asia/Kolkata")
    index = pd.date_range("2025-12-28", periods=6, freq="D", tz="Asia/Kolkata")
    frame = pd.DataFrame(
        {"open": range(6), "high": range(6), "low": range(6), "close": range(6)},
        index=index,
    )
    prepared = strategy.prepare_candles("X", frame, now=now)
    # index[-1] is 2026-01-02 (today): incomplete; 2026-01-01 is the last kept bar.
    assert prepared.index[-1].date().isoformat() == "2026-01-01"


def test_engine_evaluate_never_passes_an_incomplete_candle_to_generate_signal():
    """End-to-end: the engine path enters through prepare_candles."""
    DefaultGateStrategy.seen = None
    now = pd.Timestamp("2026-01-01 12:30", tz="Asia/Kolkata")
    frame = _hourly_frame(pd.Timestamp("2026-01-01 12:00", tz="Asia/Kolkata"))
    engine = StrategyEngine(provider=object())
    engine.evaluate(DefaultGateStrategy(), "X", now=now, candles=frame)
    seen = DefaultGateStrategy.seen
    assert seen is not None
    assert seen.index[-1] + pd.Timedelta(hours=1) <= now
