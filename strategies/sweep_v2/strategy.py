"""Sweep V2 strategy.

sweep_engine owns schedule-aligned completed-candle construction.
This strategy consumes the prepared candles and owns only signal classification.
"""
from __future__ import annotations

import pandas as pd

from config import LIVE_ASSET_MAP, LIVE_SYMBOLS
from strategies.base import Signal, Strategy, StrategyManifest
from sweep_engine import build_closed_candles


class SweepV2Strategy(Strategy):
    manifest = StrategyManifest(
        id="sweep_v2",
        name="Sweep V2",
        version="2.0.1",
        description="Strict two-sided sweep followed by final-close classification.",
        assets=LIVE_SYMBOLS,
        timeframes=("1h", "4h"),
        schedule="canonical_sweep_schedule",
        account="sweep_4h",
        capabilities=(
            "signal",
            "strategy_sl",
            "risk_reward_tp",
            "scheduled_scan",
            "backtest",
        ),
        parameters={
            "timeframe": {"type": "strategy", "default": "asset_schedule"},
            "risk_reward": {
                "type": "number",
                "default": 2.0,
                "min": 1.0,
                "max": 10.0,
                "editable": False,
            },
        },
    )

    def data_request(self, symbol: str, *, period: str = "30d") -> tuple[str, str]:
        asset = LIVE_ASSET_MAP[symbol]
        return ("1h" if asset.market == "NSE" else "30m"), period

    def prepare_candles(
        self,
        symbol: str,
        candles: pd.DataFrame,
        *,
        now: pd.Timestamp,
    ) -> pd.DataFrame:
        closed, _, _ = build_closed_candles(
            candles,
            symbol,
            now=now,
            lookback_days=7,
        )
        return closed

    def generate_signal(
        self,
        symbol: str,
        candles: pd.DataFrame,
        *,
        now: pd.Timestamp,
    ) -> Signal:
        asset = LIVE_ASSET_MAP[symbol]
        timeframe = asset.sweep_timeframe
        timestamp = candles.index[-1] if len(candles) else pd.Timestamp(now)

        if len(candles) < 2:
            return Signal(
                self.manifest.name,
                self.manifest.version,
                symbol,
                "NO_SIGNAL",
                timestamp,
                timeframe,
                "NO_SWEEP",
            )

        previous = candles.iloc[-2]
        current = candles.iloc[-1]
        high_swept = float(current["high"]) > float(previous["high"])
        low_swept = float(current["low"]) < float(previous["low"])

        if not (high_swept and low_swept):
            return Signal(
                self.manifest.name,
                self.manifest.version,
                symbol,
                "NO_SIGNAL",
                timestamp,
                timeframe,
                "NO_SWEEP",
            )

        entry = float(current["close"])
        if entry > float(previous["high"]):
            direction = "BUY"
            reason = "BULLISH"
            stop_loss = float(current["low"])
            take_profit = entry + 2 * (entry - stop_loss)
        elif entry < float(previous["low"]):
            direction = "SELL"
            reason = "BEARISH"
            stop_loss = float(current["high"])
            take_profit = entry - 2 * (stop_loss - entry)
        else:
            direction = "NEUTRAL"
            reason = "NEUTRAL"
            stop_loss = None
            take_profit = None

        return Signal(
            self.manifest.name,
            self.manifest.version,
            symbol,
            direction,
            timestamp,
            timeframe,
            reason,
            entry,
            stop_loss,
            take_profit,
            {
                "candle_start": pd.Timestamp(timestamp).isoformat(),
                "previous": {
                    key: float(previous[key])
                    for key in ("open", "high", "low", "close")
                },
                "current": {
                    key: float(current[key])
                    for key in ("open", "high", "low", "close")
                },
            },
        )


def create_strategy() -> SweepV2Strategy:
    return SweepV2Strategy()
