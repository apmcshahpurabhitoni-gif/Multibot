"""Central, locked configuration for MULTIBOT2."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final


APP_VERSION = "3.2.0"

WHAT_IS_NEW: Final[tuple[str, ...]] = (
    "🧩 Plug-and-play strategy architecture with automatic discovery.",
    "🧠 Adaptive Trend Momentum is the BTC-USD + Gold strategy on 1D candles.",
    "🔎 Sweep V2 is preserved behind the same strategy contract and canonical schedules.",
    "📊 Strategy Lab backtesting now reports 11 metrics plus a transparent 0–100 rating.",
    "⭐ Strategy results are versioned with parameter snapshots for reproducibility.",
    "🛡️ Core freshness, duplicate, risk, account-limit, paper-mode and Yahoo-only rules remain locked.",
    "💱 Asset currency is canonical and USD instruments are converted to INR for risk, P&L and reporting.",
    "📚 Added AI rebuild specification and strategy developer template for future plug-ins.",
    "🧹 Final audit unified completed-candle handling and canonical Sweep asset ownership.",
)

IST_TIMEZONE: Final = "Asia/Kolkata"
DEFAULT_TIMEFRAME: Final = "1h"
SIGNAL_FRESHNESS_HOURS: Final = 1

NSE_MARKET_OPEN: Final = "09:15"
NSE_MARKET_CLOSE: Final = "15:30"

MARKET_DATA_PROVIDER: Final = "yahoo"


# ---------------------------------------------------------------------------
# LIVE UNIVERSE
# ---------------------------------------------------------------------------

NSE_15_SYMBOLS: Final[tuple[str, ...]] = (
    "RELIANCE",
    "BHARTIARTL",
    "HDFCBANK",
    "ICICIBANK",
    "SBIN",
    "TCS",
    "BAJFINANCE",
    "LT",
    "LICI",
    "SUNPHARMA",
    "HINDUNILVR",
    "INFY",
    "TITAN",
    "MARUTI",
    "KOTAKBANK",
)

NIFTY_SYMBOLS: Final[tuple[str, ...]] = (
    "^NSEI",
    "^NSEBANK",
)

GOLD_SYMBOL: Final[str] = "GC=F"
BITCOIN_SYMBOL: Final[str] = "BTC-USD"


@dataclass(frozen=True)
class AssetConfig:
    symbol: str
    label: str
    yahoo_symbol: str
    market: str
    asset_type: str
    group: str = "NSE Stocks"
    currency: str = "INR"

    sweep_timeframe: str = "4H"


def _equity(symbol: str) -> AssetConfig:
    return AssetConfig(
        symbol=symbol,
        label=symbol,
        yahoo_symbol=f"{symbol}.NS",
        market="NSE",
        asset_type="equity",
        group="NSE Stocks",
        currency="INR",
        sweep_timeframe="4H",
    )


LIVE_ASSETS: tuple[AssetConfig, ...] = tuple(
    _equity(symbol) for symbol in NSE_15_SYMBOLS
) + (
    AssetConfig(
        symbol="^NSEI",
        label="NIFTY 50",
        yahoo_symbol="^NSEI",
        market="NSE",
        asset_type="index",
        group="NSE Indices",
        currency="INR",
        sweep_timeframe="1H",
    ),
    AssetConfig(
        symbol="^NSEBANK",
        label="BANK NIFTY",
        yahoo_symbol="^NSEBANK",
        market="NSE",
        asset_type="index",
        group="NSE Indices",
        sweep_timeframe="1H",
    ),
    AssetConfig(
        symbol="GC=F",
        label="Gold (XAU/USD)",
        yahoo_symbol="GC=F",
        market="Gold",
        asset_type="commodity",
        group="Global Markets",
        currency="USD",
        sweep_timeframe="4H",
    ),
    AssetConfig(
        symbol="BTC-USD",
        label="Bitcoin (BTC)",
        yahoo_symbol="BTC-USD",
        market="Crypto",
        asset_type="crypto",
        group="Global Markets",
        currency="USD",
        sweep_timeframe="4H",
    ),
)


LIVE_ASSET_MAP: Final[dict[str, AssetConfig]] = {
    asset.symbol: asset for asset in LIVE_ASSETS
}


LIVE_SYMBOLS: Final[tuple[str, ...]] = tuple(
    asset.symbol for asset in LIVE_ASSETS
)


# ---------------------------------------------------------------------------
# SWEEP SCHEDULES
# ---------------------------------------------------------------------------

BTC_SWEEP_HOURS_IST: Final[tuple[int, ...]] = (
    1, 5, 9, 13, 17, 21
)

GOLD_SWEEP_HOURS_IST: Final[tuple[int, ...]] = (
    2, 6, 10, 14, 18, 22
)

NSE_INDEX_SWEEP_HOURS_IST: Final[tuple[int, ...]] = (
    9, 10, 11, 12, 13, 14
)

SWEEP_MINUTE_NSE: Final[int] = 15
SWEEP_MINUTE_GLOBAL: Final[int] = 30



# ---------------------------------------------------------------------------
# ACCOUNT / RISK
# ---------------------------------------------------------------------------

ACCOUNT_SIZE_INR = 100_000
RISK_PER_TRADE_INR = 2_000
# Locked paper-trading conversion used when an instrument price is quoted in USD.
# All account risk, P&L and limits remain INR.
USD_TO_INR = float(os.getenv("USD_TO_INR", "83.0"))

ACCOUNT_TRADE_LIMITS = {
    "macro": 20,
    "nifty": 5,
    "ny_session": 3,
    "sweep_4h": 3,
}

ACCOUNT_NAMES = (
    "macro",
    "nifty",
    "ny_session",
    "sweep_4h",
)

LEVERAGE = 1.0


# ---------------------------------------------------------------------------
# BACKTEST UNIVERSE
# ---------------------------------------------------------------------------

BACKTEST_ASSETS = {
    asset.symbol: {
        "label": asset.label,
        "ticker": asset.yahoo_symbol,
        "market": asset.market,
        "asset_type": asset.asset_type,
        "group": asset.group,
        "currency": asset.currency,
        "sweep_timeframe": asset.sweep_timeframe,
    }
    for asset in LIVE_ASSETS
}


@dataclass(frozen=True)
class Settings:
    timezone: str = IST_TIMEZONE
    timeframe: str = DEFAULT_TIMEFRAME
    freshness_hours: int = SIGNAL_FRESHNESS_HOURS
    market_data_provider: str = MARKET_DATA_PROVIDER

    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    dashboard_api_url: str = "/api/dashboard"
    db_path: str = "multibot2_state.db"

    scan_interval_seconds: int = 300
    monitor_interval_seconds: int = 20

    @classmethod
    def from_env(cls) -> "Settings":
        timezone = os.getenv("TIMEZONE", IST_TIMEZONE)
        timeframe = os.getenv("TIMEFRAME", DEFAULT_TIMEFRAME).strip().lower()
        provider = os.getenv(
            "MARKET_DATA_PROVIDER",
            MARKET_DATA_PROVIDER,
        ).strip().lower()

        if timezone != IST_TIMEZONE:
            raise ValueError("TIMEZONE must be Asia/Kolkata")

        if provider != MARKET_DATA_PROVIDER:
            raise ValueError(
                "MARKET_DATA_PROVIDER must be yahoo"
            )

        return cls(
            timezone=timezone,
            timeframe=timeframe,
            freshness_hours=SIGNAL_FRESHNESS_HOURS,
            market_data_provider=provider,
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
            dashboard_api_url=os.getenv(
                "DASHBOARD_API_URL",
                "/api/dashboard",
            ),
            db_path=os.getenv(
                "BOT_STATE_DB_PATH",
                "multibot2_state.db",
            ),
            scan_interval_seconds=int(
                os.getenv("SCAN_INTERVAL_SECONDS", "300")
            ),
            monitor_interval_seconds=int(
                os.getenv("MONITOR_INTERVAL_SECONDS", "20")
            ),
        )


settings = Settings.from_env()


def get_asset(symbol: str) -> AssetConfig:
    normalized = symbol.strip().upper()

    try:
        return LIVE_ASSET_MAP[normalized]
    except KeyError as exc:
        raise ValueError(
            f"Unknown MULTIBOT2 live asset: {normalized}"
        ) from exc


def validate_configuration() -> None:
    if len(NSE_15_SYMBOLS) != 15:
        raise ValueError("NSE stock universe must contain 15 assets")

    if len(LIVE_ASSETS) != 19:
        raise ValueError(
            f"Live universe must contain exactly 19 assets; "
            f"found {len(LIVE_ASSETS)}"
        )

    if len(set(LIVE_SYMBOLS)) != 19:
        raise ValueError(
            "Live universe contains duplicate symbols"
        )

    if set(NIFTY_SYMBOLS) != {
        "^NSEI",
        "^NSEBANK",
    }:
        raise ValueError("NIFTY index configuration is invalid")

    if GOLD_SYMBOL not in LIVE_ASSET_MAP:
        raise ValueError("Gold is missing from live universe")

    if BITCOIN_SYMBOL not in LIVE_ASSET_MAP:
        raise ValueError("Bitcoin is missing from live universe")

    if set(LIVE_ASSET_MAP) != set(LIVE_SYMBOLS):
        raise ValueError("Live asset metadata must cover all live assets")

    for symbol in NSE_15_SYMBOLS:
        if LIVE_ASSET_MAP[symbol].sweep_timeframe != "4H":
            raise ValueError(f"{symbol} Sweep must be 4H")

    if LIVE_ASSET_MAP["^NSEI"].sweep_timeframe != "1H" or LIVE_ASSET_MAP["^NSEBANK"].sweep_timeframe != "1H":
        raise ValueError("NIFTY indexes Sweep must be 1H")

    if LIVE_ASSET_MAP[GOLD_SYMBOL].sweep_timeframe != "4H" or LIVE_ASSET_MAP[BITCOIN_SYMBOL].sweep_timeframe != "4H":
        raise ValueError("Global Sweep must be 4H")

    if LIVE_ASSET_MAP["^NSEI"].sweep_timeframe != "1H":
        raise ValueError("NIFTY 50 Sweep must be 1H")

    if LIVE_ASSET_MAP["^NSEBANK"].sweep_timeframe != "1H":
        raise ValueError("BANK NIFTY Sweep must be 1H")


    if ACCOUNT_SIZE_INR != 100_000:
        raise ValueError("Account size was changed")

    if RISK_PER_TRADE_INR != 2_000:
        raise ValueError("Risk per trade was changed")

    if USD_TO_INR <= 0:
        raise ValueError("USD_TO_INR must be positive")

    if LEVERAGE != 1.0:
        raise ValueError("Leverage must remain 1x")

    if settings.freshness_hours != 1:
        raise ValueError(
            "Signal freshness must remain 1 hour"
        )

    if set(ACCOUNT_TRADE_LIMITS) != set(ACCOUNT_NAMES):
        raise ValueError("Account configuration mismatch")

    if tuple(ACCOUNT_TRADE_LIMITS.values()) != (
        20,
        5,
        3,
        3,
    ):
        raise ValueError("Account limits were changed")


validate_configuration()
