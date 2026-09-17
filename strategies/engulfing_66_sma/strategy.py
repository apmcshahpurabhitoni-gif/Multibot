"""Engulfing Entries @ 66 SMA strategy.

The signal rules mirror the supplied TradingView "Engulfing Entries @ 66
SMA (Filtered)" logic. Runtime lifecycle, risk and notification behavior stay
owned by the core bot.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from config import LIVE_SYMBOLS
from strategies.base import Signal, Strategy, StrategyManifest


IST = "Asia/Kolkata"


class Engulfing66SMA(Strategy):
    """Closed-candle engulfing entries around a 66-period SMA."""

    manifest = StrategyManifest(
        id="engulfing_66_sma",
        name="Engulfing Entries @ 66 SMA",
        version="1.0.1",
        description=(
            "Bullish/bearish engulfing entries near a 66 SMA with ATR body, "
            "slope, confirmation and cooldown filters."
        ),
        assets=LIVE_SYMBOLS,
        timeframes=("1h",),
        schedule="completed_candle",
        account="macro",
        capabilities=("signal", "fixed_sl", "fixed_tp", "backtest"),
        parameters={
            "timeframe": {
                "type": "select",
                "options": ["1h"],
                "default": "1h",
                "editable": False,
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
        """Return the canonical 1H request and enough history for warm-up.

        The strategy is registered at 1H because the core provider contract
        does not pass arbitrary strategy configuration into ``data_request``.
        Keeping the timeframe fixed prevents the UI from advertising choices
        that cannot actually be applied to the market-data request.
        """
        return "1h", "60d"

    @staticmethod
    def _wilder_rma(values: pd.Series, length: int) -> pd.Series:
        """TradingView ta.rma equivalent using Wilder's alpha=1/length."""
        values = pd.Series(values, dtype=float)
        result = pd.Series(np.nan, index=values.index, dtype=float)
        if length <= 0 or len(values) < length:
            return result
        result.iloc[length - 1] = values.iloc[:length].mean()
        alpha = 1.0 / float(length)
        for i in range(length, len(values)):
            result.iloc[i] = (
                alpha * values.iloc[i]
                + (1.0 - alpha) * result.iloc[i - 1]
            )
        return result

    @classmethod
    def _indicators(cls, frame: pd.DataFrame, cfg: dict[str, Any]) -> tuple[pd.Series, pd.Series]:
        """Calculate SMA and Wilder ATR once for the whole frame."""
        close = frame["close"].astype(float)
        sma = close.rolling(cfg["sma_length"]).mean()
        previous_close = close.shift(1)
        true_range = pd.concat(
            [
                frame["high"].astype(float) - frame["low"].astype(float),
                (frame["high"].astype(float) - previous_close).abs(),
                (frame["low"].astype(float) - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = cls._wilder_rma(true_range, cfg["atr_length"])
        return sma, atr

    @staticmethod
    def _completed_only(frame: pd.DataFrame, now: pd.Timestamp, timeframe: str) -> pd.DataFrame:
        if frame.empty or timeframe != "1h":
            return frame
        current = pd.Timestamp(now)
        if current.tzinfo is None:
            raise ValueError("Runtime timestamp must be timezone-aware")
        current = current.tz_convert(IST)

        data = frame.copy().sort_index()
        if not isinstance(data.index, pd.DatetimeIndex):
            raise ValueError("Engulfing 66 SMA candles require a DatetimeIndex")
        if data.index.tz is None:
            raise ValueError("Engulfing 66 SMA candle timestamps must be timezone-aware")

        # Yahoo labels hourly candles by their start. Do not use the final
        # candle until its one-hour interval has closed.
        last = data.index[-1].tz_convert(IST)
        if last + pd.Timedelta(hours=1) > current:
            return data.iloc[:-1]
        return data

    def prepare_candles(
        self,
        symbol: str,
        candles: pd.DataFrame,
        *,
        now: pd.Timestamp,
    ) -> pd.DataFrame:
        cfg = self.validate_config({})
        data = candles.copy().sort_index()
        if data.empty:
            return data
        required = {"open", "high", "low", "close"}
        missing = required.difference(data.columns)
        if missing:
            raise ValueError(
                f"Engulfing 66 SMA candles missing columns: {sorted(missing)}"
            )
        if not cfg["confirm_only"]:
            return data
        return self._completed_only(data, now, cfg["timeframe"])

    @staticmethod
    def _signal_at(
        frame: pd.DataFrame,
        index: int,
        *,
        cfg: dict[str, Any],
        sma: pd.Series,
        atr: pd.Series,
        last_signal_index: int,
    ) -> tuple[bool, str, dict[str, Any]]:
        row = frame.iloc[index]
        previous = frame.iloc[index - 1]
        current_sma = sma.iloc[index]
        current_atr = atr.iloc[index]
        slope_index = index - cfg["slope_length"]
        slope_base = sma.iloc[slope_index] if slope_index >= 0 else np.nan

        if pd.isna(current_sma) or pd.isna(current_atr) or pd.isna(slope_base):
            return False, "INDICATOR_DATA_UNAVAILABLE", {}

        o, h, l, c = map(float, (row["open"], row["high"], row["low"], row["close"]))
        po, ph, pl, pc = map(float, (previous["open"], previous["high"], previous["low"], previous["close"]))
        body = abs(c - o)
        previous_body = abs(pc - po)

        bullish = (
            pc < po
            and c > o
            and o <= pc
            and c >= po
        )
        bearish = (
            pc > po
            and c < o
            and o >= pc
            and c <= po
        )

        if cfg["strict_engulf"]:
            bullish = bullish and c > ph and o < pl
            bearish = bearish and c < pl and o > ph

        atr_value = float(current_atr)
        size_ok = (
            body >= cfg["min_body_atr"] * atr_value
            and body <= cfg["max_body_atr"] * atr_value
            and body > previous_body
        )
        zone = cfg["zone_atr"] * atr_value
        near_ma = l <= float(current_sma) + zone and h >= float(current_sma) - zone
        slope = float(current_sma) - float(slope_base)
        up_trend = slope >= cfg["min_slope_atr"] * atr_value
        down_trend = slope <= -cfg["min_slope_atr"] * atr_value

        long_raw = bullish and size_ok and near_ma and c > float(current_sma) and up_trend
        short_raw = bearish and size_ok and near_ma and c < float(current_sma) and down_trend
        cooldown_ok = index - last_signal_index >= cfg["cooldown"]

        diagnostics = {
            "sma": float(current_sma),
            "atr": atr_value,
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

    def generate_signal(
        self,
        symbol: str,
        candles: pd.DataFrame,
        *,
        now: pd.Timestamp,
    ) -> Signal:
        cfg = self.validate_config({})
        frame = candles.copy().sort_index()
        timestamp = frame.index[-1] if len(frame) else pd.Timestamp(now)
        minimum = max(
            cfg["sma_length"] + cfg["slope_length"] + 2,
            cfg["atr_length"] + 2,
            3,
        )
        if len(frame) < minimum:
            return Signal(
                self.manifest.name,
                self.manifest.version,
                symbol,
                "NO_SIGNAL",
                timestamp,
                "1H",
                "INSUFFICIENT_DATA",
                metadata={"candle_count": len(frame), "required": minimum},
            )

        sma, atr = self._indicators(frame, cfg)
        last_signal_index = -10**9
        final_direction = "NO_SIGNAL"
        final_reason = "NO_APPROVED_SETUP"
        final_metadata: dict[str, Any] = {}

        # Pine's var lastSig state is reproduced by walking candles in order.
        for index in range(1, len(frame)):
            approved, reason, diagnostics = self._signal_at(
                frame,
                index,
                cfg=cfg,
                sma=sma,
                atr=atr,
                last_signal_index=last_signal_index,
            )
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
            return Signal(
                self.manifest.name,
                self.manifest.version,
                symbol,
                "NO_SIGNAL",
                timestamp,
                "1H",
                final_reason,
                metadata=final_metadata,
            )

        entry = float(frame["close"].iloc[-1])
        atr_value = float(final_metadata["atr"])
        if final_direction == "BUY":
            stop_loss = entry - cfg["stop_atr"] * atr_value
            take_profit = entry + cfg["target_atr"] * atr_value
        else:
            stop_loss = entry + cfg["stop_atr"] * atr_value
            take_profit = entry - cfg["target_atr"] * atr_value

        final_metadata.update(
            {"entry": entry, "stop_loss": stop_loss, "take_profit": take_profit}
        )
        return Signal(
            self.manifest.name,
            self.manifest.version,
            symbol,
            final_direction,
            timestamp,
            "1H",
            final_reason,
            entry,
            stop_loss,
            take_profit,
            final_metadata,
        )


def create_strategy() -> Engulfing66SMA:
    return Engulfing66SMA()
