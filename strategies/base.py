"""Stable plug-in contract for MULTIBOT2 strategies."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
import re
import pandas as pd

@dataclass(frozen=True)
class Signal:
    strategy: str
    version: str
    symbol: str
    direction: str
    timestamp: pd.Timestamp
    timeframe: str
    reason: str = ""
    entry: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_directional(self) -> bool:
        return self.direction in {"BUY", "SELL"}

@dataclass(frozen=True)
class StrategyManifest:
    id: str
    name: str
    version: str
    description: str
    assets: tuple[str, ...]
    timeframes: tuple[str, ...]
    schedule: str
    parameters: dict[str, Any]
    capabilities: tuple[str, ...] = ()
    account: str = "nifty"

_TIMEFRAME_UNIT = {"m": "minutes", "h": "hours", "d": "days"}

def _timeframe_interval(timeframe: str) -> pd.Timedelta | None:
    """Parse a manifest timeframe (1m/15m/1h/4h/1d) into a bar duration."""
    match = re.match(r"^(\d+)([mhd])$", str(timeframe or "").strip().lower())
    if not match:
        return None
    return pd.Timedelta(**{_TIMEFRAME_UNIT[match.group(2)]: int(match.group(1))})

class Strategy(ABC):
    manifest: StrategyManifest

    @abstractmethod
    def generate_signal(self, symbol: str, candles: pd.DataFrame, *, now: pd.Timestamp) -> Signal:
        raise NotImplementedError

    def data_request(self, symbol: str, *, period: str = "30d") -> tuple[str, str]:
        """Return Yahoo interval and lookback required by this strategy."""
        return self.manifest.timeframes[0].lower(), period

    def prepare_candles(self, symbol: str, candles: pd.DataFrame, *, now: pd.Timestamp) -> pd.DataFrame:
        """The single ownership point for completed-candle validation (rule 11).

        Every path that reaches ``generate_signal`` enters here first — live
        scans via ``StrategyEngine.evaluate`` and backtests via
        ``backtest_signal`` — so completion is decided exactly once, in
        preparation, never inside ``generate_signal``.

        The default implementation drops the trailing candle unless it is
        provably complete for the manifest timeframe, so a strategy that does
        not override this still cannot signal from an incomplete candle. A
        strategy whose bars use a different labelling convention (session-dated
        daily bars, schedule-aligned sweep sessions) overrides this and owns
        its rule.
        """
        data = candles.sort_index()
        if data.empty or not isinstance(data.index, pd.DatetimeIndex) or data.index.tz is None:
            return data
        interval = _timeframe_interval(self.manifest.timeframes[0] if self.manifest.timeframes else "")
        if interval is None:
            return data
        current = pd.Timestamp(now)
        if current.tzinfo is None:
            raise ValueError("Runtime timestamp must be timezone-aware")
        if data.index[-1] + interval > current:
            return data.iloc[:-1]
        return data

    def build_trade_plan(self, signal: Signal, *, entry: float | None = None) -> tuple[float, float, float] | None:
        if not signal.is_directional:
            return None
        resolved_entry = entry if entry is not None else signal.entry
        if resolved_entry is None or signal.stop_loss is None or signal.take_profit is None:
            raise ValueError(
                f"{self.manifest.id} returned a directional signal without entry/SL/TP"
            )
        return (
            float(resolved_entry),
            float(signal.stop_loss),
            float(signal.take_profit),
        )

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        merged = {k: v.get("default") if isinstance(v, dict) else v for k, v in self.manifest.parameters.items()}
        merged.update(config or {})
        return merged

    def trailing_policy(self, config: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"enabled": False}

    def backtest_signal(self, symbol: str, candles: pd.DataFrame, *, now: pd.Timestamp) -> Signal:
        """Backtests must use the same candle-preparation contract as live scans."""
        prepared = self.prepare_candles(symbol, candles, now=now)
        return self.generate_signal(symbol, prepared, now=now)
