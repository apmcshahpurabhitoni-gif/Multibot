"""Engulfing Entries @ 66 SMA, ported from the supplied TradingView Pine logic."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from config import LIVE_SYMBOLS
from strategies.base import Signal, Strategy, StrategyManifest


class Engulfing66SMA(Strategy):
    """Closed-candle bullish/bearish engulfing setup around a 66 SMA.

    The implementation intentionally mirrors the supplied Pine v5 indicator:
    SMA/ATR proximity, body-size filters, optional full-range engulfing,
    directional SMA slope, closed-candle confirmation and bar cooldown.
    """

    manifest = StrategyManifest(
        id="engulfing_66_sma",
        name="Engulfing Entries @ 66 SMA",
        version="1.0.0",
        description="Bullish/bearish engulfing entries near a 66 SMA with ATR quality, slope and cooldown filters.",
        assets=LIVE_SYMBOLS,
        timeframes=("1h",),
        schedule="completed_candle",
        account="macro",
        capabilities=("signal", "fixed_sl", "fixed_tp", "backtest"),
        parameters={
            "timeframe": {
                "type": "select",
                "options": ["15m", "30m", "1h", "4h", "1d"],
                "default": "1h",
                "editable": True,
            },
            "sma_length": {"type": "integer", "min": 2, "max": 500, "default": 66},
            "atr_length": {"type": "integer", "min": 1, "max": 200, "default": 14},
            "zone_atr": {"type": "number", "min": 0.0, "max": 10.0, "default": 0.35},
            "min_body_atr": {"type": "number", "min": 0.0, "max": 10.0, "default": 0.45},
            "max_body_atr": {"type": "number", "min": 0.5, "max": 20.0, "default": 3.5},
            "strict_engulf": {"type": "boolean", "default": False},
            "min_slope_atr": {"type": "number", "min": 0.0, "max": 10.0, "default": 0.15},
            "slope_length": {"type": "integer", "min": 1, "max": 200, "default": 10},
            "cooldown": {"type": "integer", "min": 0, "max": 500, "default": 12},
            "confirm_only": {"type": "boolean", "default": True},
            "stop_atr": {"type": "number", "min": 0.1, "max": 20.0, "default": 1.2},
            "target_atr": {"type": "number", "min": 0.1, "max": 20.0, "default": 2.0},
        },
    )

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        merged = super().validate_config(config)
        if merged["max_body_atr"] < merged["min_body_atr"]:
            raise ValueError("max_body_atr must be greater than or equal to min_body_atr")
        return merged

    def data_request(self, symbol: str, *, period: str = "30d") -> tuple[str, str]:
        # Yahoo supports these intervals for the bot's supported chart choices.
        # Lookback is deliberately large enough for the 66-SMA + slope warmup.
        timeframe = self.validate_config({}).get("timeframe", "1h")
        if timeframe == "1d":
            return "1d", "400d"
        if timeframe == "4h":
            return "4h", "180d"
        if timeframe == "30m":
            return "30m", "60d"
        if timeframe == "15m":
            return "15m", "60d"
        return "1h", "60d"

    @staticmethod
    def _wilder_rma(values: pd.Series, length: int) -> pd.Series:
        """TradingView ta.rma equivalent (Wilder smoothing, alpha=1/length)."""
        values = pd.Series(values, dtype=float)
        result = pd.Series(np.nan, index=values.index, dtype=float)
        if length <= 0 or len(values) < length:
            return result
        seed = values.iloc[:length].mean()
        result.iloc[length - 1] = seed
        alpha = 1.0 / float(length)
        for i in range(length, len(values)):
            result.iloc[i] = alpha * values.iloc[i] + (1.0 - alpha) * result.iloc[i - 1]
        return result

    @classmethod
    def _atr(cls, frame: pd.DataFrame, length: int) -> pd.Series:
        previous_close = frame["close"].shift(1)
        true_range = pd.concat(
            [
                frame["high"] - frame["low"],
                (frame["high"] - previous_close).abs(),
                (frame["low"] - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        return cls._wilder_rma(true_range, length)

    @staticmethod
    def _completed_only(frame: pd.DataFrame, now: pd.Timestamp, timeframe: str) -> pd.DataFrame:
        if frame.empty:
            return frame
        current = pd.Timestamp(now)
        if current.tzinfo is None:
            raise ValueError("Runtime timestamp must be timezone-aware")
        current = current.tz_convert("Asia/Kolkata")
        data = frame.copy().sort_index()
        if not isinstance(data.index, pd.DatetimeIndex):
            raise ValueError("Engulfing 66 SMA candles require a DatetimeIndex")
        if data.index.tz is None:
            raise ValueError("Engulfing 66 SMA candle timestamps must be timezone-aware")
        # Yahoo timestamps are candle starts. Remove the last bar whenever its
        # expected close is still in the future. This is the bot equivalent of
        # Pine's confirmOnly/barstate.isconfirmed behavior.
        durations = {"15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}
        minutes = durations[timeframe]
        last = data.index[-1].tz_convert("Asia/Kolkata")
        if last + pd.Timedelta(minutes=minutes) > current:
            data = data.iloc[:-1]
        return data

    def prepare_candles(self, symbol: str, candles: pd.DataFrame, *, now: pd.Timestamp) -> pd.DataFrame:
        cfg = self.validate_config({})
        data = candles.copy().sort_index()
        if data.empty:
            return data
        required = {"open", "high", "low", "close"}
        missing = required.difference(data.columns)
        if missing:
            raise ValueError(f"Engulfing 66 SMA candles missing columns: {sorted(missing)}")
        return self._completed_only(data, now, cfg["timeframe"]) if cfg["confirm_only"] else data

    def _signal_at(self, frame: pd.DataFrame, index: int, *, cfg: dict[str, Any], last_signal_index: int) -> tuple[bool, str, dict[str, Any]]:
        row = frame.iloc[index]
        previous = frame.iloc[index - 1]
        sma = frame["close"].rolling(cfg["sma_length"]).mean().iloc[index]
        atr_series = self._atr(frame, cfg["atr_length"])
        atr = atr_series.iloc[index]
        slope_base_index = index - cfg["slope_length"]
        slope_base = frame["close"].rolling(cfg["sma_length"]).mean().iloc[slope_base_index] if slope_base_index >= 0 else np.nan
        if pd.isna(sma) or pd.isna(atr) or pd.isna(slope_base):
            return False, "INDICATOR_DATA_UNAVAILABLE", {}

        body = abs(float(row["close"]) - float(row["open"]))
        previous_body = abs(float(previous["close"]) - float(previous["open"]))
        bull_base = (
            float(previous["close"]) < float(previous["open"])
            and float(row["close"]) > float(row["open"])
            and float(row["open"]) <= float(previous["close"])
            and float(row["close"]) >= float(previous["open"])
        )
        bear_base = (
            float(previous["close"]) > float(previous["open"])
            and float(row["close"]) < float(row["open"])
            and float(row["open"]) >= float(previous["close"])
            and float(row["close"]) <= float(previous["open"])
        )
        bull_full = bull_base and float(row["close"]) > float(previous["high"]) and float(row["open"]) < float(previous["low"])
        bear_full = bear_base and float(row["close"]) < float(previous["low"]) and float(row["open"]) > float(previous["high"])
        bull_engulf = bull_full if cfg["strict_engulf"] else bull_base
        bear_engulf = bear_full if cfg["strict_engulf"] else bear_base
        size_ok = (
            body >= cfg["min_body_atr"] * float(atr)
            and body <= cfg["max_body_atr"] * float(atr)
            and body > previous_body
        )
        zone = cfg["zone_atr"] * float(atr)
        near_ma = float(row["low"]) <= float(sma) + zone and float(row["high"]) >= float(sma) - zone
        slope = float(sma) - float(slope_base)
        up_trend = slope >= cfg["min_slope_atr"] * float(atr)
        down_trend = slope <= -cfg["min_slope_atr"] * float(atr)
        long_raw = bull_engulf and size_ok and near_ma and float(row["close"]) > float(sma) and up_trend
        short_raw = bear_engulf and size_ok and near_ma and float(row["close"]) < float(sma) and down_trend
        cooldown_ok = index - last_signal_index >= cfg["cooldown"]
        diagnostics = {
            "sma": float(sma),
            "atr": float(atr),
            "body": body,
            "previous_body": previous_body,
            "slope": slope,
            "near_ma": bool(near_ma),
            "up_trend": bool(up_trend),
            "down_trend": bool(down_trend),
            "cooldown_ok": bool(cooldown_ok),
        }
        if not cooldown_ok:
            return False, "COOLDOWN", diagnostics
        if long_raw:
            return True, "BULLISH_ENGULFING_AT_66_SMA", diagnostics
        if short_raw:
            return True, "BEARISH_ENGULFING_AT_66_SMA", diagnostics
        return False, "NO_APPROVED_SETUP", diagnostics

    def generate_signal(self, symbol: str, candles: pd.DataFrame, *, now: pd.Timestamp) -> Signal:
        cfg = self.validate_config({})
        timeframe = cfg["timeframe"]
        frame = candles.copy().sort_index()
        timestamp = frame.index[-1] if len(frame) else pd.Timestamp(now)
        minimum = max(cfg["sma_length"] + cfg["slope_length"] + 2, cfg["atr_length"] + 2, 3)
        if len(frame) < minimum:
            return Signal(self.manifest.name, self.manifest.version, symbol, "NO_SIGNAL", timestamp, timeframe.upper(), "INSUFFICIENT_DATA", metadata={"candle_count": len(frame), "required": minimum})

        last_signal_index = -10**9
        final_direction = "NO_SIGNAL"
        final_reason = "NO_APPROVED_SETUP"
        final_metadata: dict[str, Any] = {}
        for index in range(1, len(frame)):
            approved, reason, diagnostics = self._signal_at(frame, index, cfg=cfg, last_signal_index=last_signal_index)
            if approved:
                last_signal_index = index
                if index == len(frame) - 1:
                    final_direction = "BUY" if reason.startswith("BULLISH") else "SELL"
                    final_reason = reason
                    final_metadata = diagnostics
            elif index == len(frame) - 1:
                final_reason = reason
                final_metadata = diagnostics

        if final_direction == "NO_SIGNAL":
            return Signal(self.manifest.name, self.manifest.version, symbol, "NO_SIGNAL", timestamp, timeframe.upper(), final_reason, metadata=final_metadata)

        entry = float(frame["close"].iloc[-1])
        atr = float(final_metadata["atr"])
        distance = cfg["stop_atr"] * atr
        if final_direction == "BUY":
            stop_loss = entry - distance
            take_profit = entry + cfg["target_atr"] * atr
        else:
            stop_loss = entry + distance
            take_profit = entry - cfg["target_atr"] * atr
        final_metadata.update({"entry": entry, "stop_loss": stop_loss, "take_profit": take_profit})
        return Signal(
            self.manifest.name,
            self.manifest.version,
            symbol,
            final_direction,
            timestamp,
            timeframe.upper(),
            final_reason,
            entry,
            stop_loss,
            take_profit,
            final_metadata,
        )


def create_strategy() -> Engulfing66SMA:
    return Engulfing66SMA()
