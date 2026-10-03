"""Central, locked configuration for MULTIBOT2."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

from release_notes import APP_VERSION, RELEASE_HIGHLIGHTS

# Backwards-compatible exports. The canonical source is release_notes.py.
WHAT_IS_NEW: Final[tuple[str, ...]] = RELEASE_HIGHLIGHTS

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

# Approved Forex universe.
FOREX_SYMBOLS: Final[tuple[str, ...]] = (
    "EURUSD=X",
    "GBPUSD=X",
    "AUDUSD=X",
    "USDJPY=X",
    "NZDUSD=X",
    "EURJPY=X",
)


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
    AssetConfig(
        symbol="EURUSD=X",
        label="EUR/USD",
        yahoo_symbol="EURUSD=X",
        market="Forex",
        asset_type="forex",
        group="Global Markets",
        currency="USD",
        sweep_timeframe="4H",
    ),
    AssetConfig(
        symbol="GBPUSD=X",
        label="GBP/USD",
        yahoo_symbol="GBPUSD=X",
        market="Forex",
        asset_type="forex",
        group="Global Markets",
        currency="USD",
        sweep_timeframe="4H",
    ),
    AssetConfig(
        symbol="AUDUSD=X",
        label="AUD/USD",
        yahoo_symbol="AUDUSD=X",
        market="Forex",
        asset_type="forex",
        group="Global Markets",
        currency="USD",
        sweep_timeframe="4H",
    ),
    AssetConfig(
        symbol="USDJPY=X",
        label="USD/JPY",
        yahoo_symbol="USDJPY=X",
        market="Forex",
        asset_type="forex",
        group="Global Markets",
        currency="JPY",
        sweep_timeframe="4H",
    ),
    AssetConfig(
        symbol="NZDUSD=X",
        label="NZD/USD",
        yahoo_symbol="NZDUSD=X",
        market="Forex",
        asset_type="forex",
        group="Global Markets",
        currency="USD",
        sweep_timeframe="4H",
    ),
    AssetConfig(
        symbol="EURJPY=X",
        label="EUR/JPY",
        yahoo_symbol="EURJPY=X",
        market="Forex",
        asset_type="forex",
        group="Global Markets",
        currency="JPY",
        sweep_timeframe="4H",
    ),
)


LIVE_ASSET_MAP: Final[dict[str, AssetConfig]] = {
    asset.symbol: asset for asset in LIVE_ASSETS
}

#: The shipped symbol list, frozen. `LIVE_SYMBOLS` is re-pointed at the live
#: universe when an operator adds an asset, so the startup checks that mean
#: "the 25 built-in assets are intact" have to read this instead.
BUILTIN_SYMBOLS: Final[tuple[str, ...]] = tuple(
    a.symbol for a in LIVE_ASSETS
)
BUILTIN_ASSET_SYMBOLS: Final[frozenset[str]] = frozenset(BUILTIN_SYMBOLS)

LIVE_SYMBOLS: Final[tuple[str, ...]] = tuple(
    asset.symbol for asset in LIVE_ASSETS
)


# ---------------------------------------------------------------------------
# SWEEP SCHEDULES
# ---------------------------------------------------------------------------

BTC_SWEEP_HOURS_IST: Final[tuple[int, ...]] = (1, 5, 9, 13, 17, 21)

GOLD_SWEEP_HOURS_IST: Final[tuple[int, ...]] = (2, 6, 10, 14, 18, 22)

FOREX_SWEEP_HOURS_IST: Final[tuple[int, ...]] = GOLD_SWEEP_HOURS_IST

NSE_INDEX_SWEEP_HOURS_IST: Final[tuple[int, ...]] = (9, 10, 11, 12, 13, 14)

SWEEP_MINUTE_NSE: Final[int] = 15
SWEEP_MINUTE_GLOBAL: Final[int] = 30


# ---------------------------------------------------------------------------
# ACCOUNT / RISK
# ---------------------------------------------------------------------------

# These are the *defaults* for a new account and the shipped values for the
# four built-in books. They are never rewritten, so "reset to defaults" always
# has something to go back to.
DEFAULT_ACCOUNT_SIZE_INR: Final = 100_000
DEFAULT_RISK_PER_TRADE_INR: Final = 2_000
DEFAULT_ACCOUNT_TRADE_LIMITS: Final[dict[str, int]] = {
    "macro": 20,
    "nifty": 5,
    "ny_session": 3,
    "sweep_4h": 3,
}

# Live, operator-editable values. bot_settings.py rewrites these maps *in
# place* on save, so every module that did `from config import
# ACCOUNT_TRADE_LIMITS` keeps seeing the current numbers instead of a snapshot
# taken at import time.
ACCOUNT_SIZES: dict[str, float] = {name: float(DEFAULT_ACCOUNT_SIZE_INR)
                                   for name in DEFAULT_ACCOUNT_TRADE_LIMITS}
ACCOUNT_RISK_PER_TRADE: dict[str, float] = {name: float(DEFAULT_RISK_PER_TRADE_INR)
                                            for name in DEFAULT_ACCOUNT_TRADE_LIMITS}
ACCOUNT_TRADE_LIMITS: dict[str, int] = dict(DEFAULT_ACCOUNT_TRADE_LIMITS)

#: Bounds every account must satisfy. Editable is not the same as unbounded:
#: an account still has to be fundable, capped and internally consistent.
ACCOUNT_MIN_SIZE_INR: Final = 1_000
ACCOUNT_MAX_SIZE_INR: Final = 100_000_000
ACCOUNT_MIN_TRADE_LIMIT: Final = 1
ACCOUNT_MAX_TRADE_LIMIT: Final = 500
ACCOUNT_MIN_RISK_INR: Final = 100
ACCOUNT_MAX_RISK_INR: Final = 500_000
# Locked paper-trading conversion used when an instrument price is quoted in USD.
# All account risk, P&L and limits remain INR.
USD_TO_INR = float(os.getenv("USD_TO_INR", "83.0"))

#: Kept as the plain scalar other modules import for a default-sized account.
ACCOUNT_SIZE_INR: float = float(DEFAULT_ACCOUNT_SIZE_INR)
RISK_PER_TRADE_INR: float = float(DEFAULT_RISK_PER_TRADE_INR)


# ---------------------------------------------------------------------------
# ACCOUNT ROUTING
# ---------------------------------------------------------------------------
# `account` used to be a static field on each strategy manifest, which meant a
# strategy could only ever feed one account no matter which asset it scanned.
# Routing is now resolved from (strategy, asset, time) instead, so the same
# strategy can feed different accounts depending on what it is looking at and
# when.
#
# Rules are evaluated top to bottom and the first match wins. The order is
# load-bearing: `nifty` and `macro` are the same two strategies pointed at
# different asset groups, and `ny_session` deliberately claims the global
# assets during the New York session that `macro` is excluded from, so those
# two can never double-fill the same signal.

NY_SESSION_TZ: Final = "America/New_York"
DEFAULT_NY_SESSION_START_HOUR: Final = 8
DEFAULT_NY_SESSION_END_HOUR: Final = 17
# 08:00-17:00 New York time. IST has no daylight saving and the US does, so this
# is expressed in New York time on purpose: it resolves to 17:30-02:30 IST
# while US daylight time is in force and 18:30-03:30 IST outside it, without
# either annual switchover ever having to be maintained by hand.
#
# The session hours and ACCOUNT_ROUTING below are deliberately not `Final`:
# bot_settings.py may replace them at runtime when the operator saves a
# change from the Tools screen, and every caller reads them through
# routing_state()/resolve_account() so the swap is picked up without a restart.
# The DEFAULT_* values are what "reset to defaults" restores, and they stay
# pristine no matter what has been saved.
NY_SESSION_START_HOUR: int = DEFAULT_NY_SESSION_START_HOUR
NY_SESSION_END_HOUR: int = DEFAULT_NY_SESSION_END_HOUR

GLOBAL_MARKET_GROUP: Final = "Global Markets"
NSE_ASSET_GROUPS: Final[tuple[str, ...]] = ("NSE Stocks", "NSE Indices")


@dataclass(frozen=True)
class RoutingRule:
    """One row of the routing table.

    A `None` field matches anything. `in_ny_session` restricts the rule to one
    side of the New York session boundary rather than ignoring the clock.
    """

    account: str
    strategies: tuple[str, ...] | None = None
    asset_groups: tuple[str, ...] | None = None
    in_ny_session: bool | None = None

    def matches(self, strategy_id: str, group: str, ny_session: bool) -> bool:
        if self.strategies is not None and strategy_id not in self.strategies:
            return False
        if self.asset_groups is not None and group not in self.asset_groups:
            return False
        if self.in_ny_session is not None and ny_session is not self.in_ny_session:
            return False
        return True


ACCOUNT_ROUTING: tuple[RoutingRule, ...] = (
    # India book: the trend strategies on the NSE universe, any time.
    RoutingRule("nifty", ("adaptive_trend", "engulfing_66_sma"), NSE_ASSET_GROUPS),
    # Global book outside the New York session.
    RoutingRule("macro", ("adaptive_trend", "engulfing_66_sma"),
                (GLOBAL_MARKET_GROUP,), False),
    # The same global assets during the New York session, for every strategy.
    RoutingRule("ny_session", None, (GLOBAL_MARKET_GROUP,), True),
    # The sweep strategy covers the whole universe at all times.
    RoutingRule("sweep_4h", ("sweep_v2",)),
)

#: The shipped table, never overwritten, so "reset to defaults" can always go
#: back to the contract in this file rather than to whatever was last saved.
DEFAULT_ACCOUNT_ROUTING: Final[tuple[RoutingRule, ...]] = ACCOUNT_ROUTING


def in_new_york_session(now) -> bool:
    """True when `now` falls inside the New York trading session."""
    from zoneinfo import ZoneInfo

    local = now.astimezone(ZoneInfo(NY_SESSION_TZ))
    return NY_SESSION_START_HOUR <= local.hour < NY_SESSION_END_HOUR


def resolve_account(strategy_id: str, asset: "AssetConfig", now, fallback: str) -> str:
    """Route one (strategy, asset, time) to the account that should trade it.

    `fallback` is the strategy's manifest account, used when no rule matches so
    a newly added strategy keeps trading somewhere rather than silently
    disappearing.
    """
    ny_session = in_new_york_session(now)
    for rule in ACCOUNT_ROUTING:
        if rule.matches(strategy_id, asset.group, ny_session):
            return rule.account
    return fallback


def known_asset_groups() -> tuple[str, ...]:
    """Asset groups present in the live universe, first-seen order.

    An operator-added asset may only join one of these, never create a new one.
    """
    return tuple(dict.fromkeys(asset.group for asset in live_assets()))


def known_strategy_ids() -> tuple[str, ...]:
    """Strategy ids discovered from the plug-in tree.

    Imported lazily: strategies imports config, so importing it at module load
    would close a cycle.
    """
    from strategies.registry import discover_strategies

    return discover_strategies().ids()


def routing_state() -> dict:
    """The routing table and session window as plain data.

    Dashboard callers must read this rather than binding ACCOUNT_ROUTING or the
    session hours at import time, otherwise a change saved from the Tools
    screen would keep showing the values the process started with.
    """
    return {
        "session": {
            "timezone": NY_SESSION_TZ,
            "start_hour": NY_SESSION_START_HOUR,
            "end_hour": NY_SESSION_END_HOUR,
        },
        "rules": [
            {
                "account": rule.account,
                "strategies": list(rule.strategies) if rule.strategies else None,
                "asset_groups": list(rule.asset_groups) if rule.asset_groups else None,
                "in_ny_session": rule.in_ny_session,
            }
            for rule in ACCOUNT_ROUTING
        ],
        "accounts": list(ACCOUNT_NAMES),
        "asset_groups": list(known_asset_groups()),
    }


#: The built-in books. An operator may add more, but these four are the
#: shipped contract: routing ships with one rule for each and the dashboard has
#: always shown them.
BUILTIN_ACCOUNT_NAMES: Final[tuple[str, ...]] = (
    "macro",
    "nifty",
    "ny_session",
    "sweep_4h",
)

#: Live account list. A tuple cannot be mutated in place, so unlike the value
#: maps above this one is replaced on save and read through account_names().
ACCOUNT_NAMES: tuple[str, ...] = BUILTIN_ACCOUNT_NAMES


def account_names() -> tuple[str, ...]:
    """Every account that currently exists, built-in plus operator-added."""
    return ACCOUNT_NAMES


def account_size(name: str) -> float:
    try:
        return ACCOUNT_SIZES[name.lower()]
    except KeyError as exc:
        raise ValueError(f"Unknown trading account: {name}") from exc


def account_risk_per_trade(name: str) -> float:
    try:
        return ACCOUNT_RISK_PER_TRADE[name.lower()]
    except KeyError as exc:
        raise ValueError(f"Unknown trading account: {name}") from exc


def accounts_state() -> list[dict]:
    """Every account with its size, limit and risk, for the dashboard."""
    return [
        {
            "name": name,
            "starting_balance": ACCOUNT_SIZES[name],
            "daily_trade_limit": ACCOUNT_TRADE_LIMITS[name],
            "risk_per_trade": ACCOUNT_RISK_PER_TRADE[name],
        }
        for name in ACCOUNT_NAMES
    ]


LEVERAGE = 1.0


# ---------------------------------------------------------------------------
# OPERATOR-ADDED ASSETS
# ---------------------------------------------------------------------------
# Assets added from the dashboard land here rather than in LIVE_ASSETS, so the
# shipped 25-asset universe stays a testable constant while the live universe
# can grow. An added asset plugs into an existing account group and account; it
# never creates a group of its own.
#
# `LIVE_ASSET_MAP` and both maps below are rewritten in place so that modules
# which imported them keep resolving the current universe.
EXTRA_ASSETS: dict[str, AssetConfig] = {}
EXTRA_ASSET_STRATEGIES: dict[str, tuple[str, ...]] = {}

#: The one place a new asset's market must agree with its group, so an equity
#: cannot be filed under Global Markets and priced in rupees.
GROUP_MARKET: Final[dict[str, str]] = {
    "NSE Stocks": "NSE",
    "NSE Indices": "NSE",
    "Global Markets": "",
}
#: Sweep needs a closed candle at this resolution; indices are 1H, the rest 4H.
GROUP_SWEEP_TIMEFRAME: Final[dict[str, str]] = {
    "NSE Stocks": "4H",
    "NSE Indices": "1H",
    "Global Markets": "4H",
}


def live_assets() -> tuple[AssetConfig, ...]:
    """Shipped universe plus anything the operator added."""
    return LIVE_ASSETS + tuple(EXTRA_ASSETS.values())


def assets_for_strategy(strategy_id: str) -> tuple[AssetConfig, ...]:
    """Every asset a strategy scans: its manifest plus anything added for it.

    A strategy manifest is code, so an asset dropped in from the dashboard
    cannot appear in it. It is unioned in here instead, which is what makes an
    added asset actually trade rather than just sit in the universe.
    """
    from strategies.registry import discover_strategies

    try:
        manifest = set(discover_strategies().get(strategy_id).manifest.assets)
    except KeyError as exc:
        raise ValueError(f"Unknown strategy: {strategy_id}") from exc
    return tuple(
        asset for asset in live_assets()
        if asset.symbol in manifest or strategy_id in EXTRA_ASSET_STRATEGIES.get(asset.symbol, ())
    )


def live_symbols() -> tuple[str, ...]:
    return LIVE_SYMBOLS + tuple(EXTRA_ASSETS)


def rebuild_asset_map() -> None:
    """Re-point LIVE_ASSET_MAP and LIVE_SYMBOLS at the current universe.

    Mutated in place rather than rebound: `from config import LIVE_ASSET_MAP`
    is used across the bot and a rebind would leave every importer holding a
    map frozen at import time.
    """
    global LIVE_SYMBOLS
    assets = live_assets()
    LIVE_ASSET_MAP.clear()
    LIVE_ASSET_MAP.update({a.symbol: a for a in assets})
    LIVE_SYMBOLS = tuple(a.symbol for a in assets)


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
            raise ValueError("MARKET_DATA_PROVIDER must be yahoo")

        return cls(
            timezone=timezone,
            timeframe=timeframe,
            freshness_hours=SIGNAL_FRESHNESS_HOURS,
            market_data_provider=provider,
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
            dashboard_api_url=os.getenv("DASHBOARD_API_URL", "/api/dashboard"),
            db_path=os.getenv("BOT_STATE_DB_PATH", "multibot2_state.db"),
            scan_interval_seconds=int(os.getenv("SCAN_INTERVAL_SECONDS", "300")),
            monitor_interval_seconds=int(os.getenv("MONITOR_INTERVAL_SECONDS", "20")),
        )


settings = Settings.from_env()


def get_asset(symbol: str) -> AssetConfig:
    normalized = symbol.strip().upper()
    try:
        return LIVE_ASSET_MAP[normalized]
    except KeyError as exc:
        raise ValueError(f"Unknown MULTIBOT2 live asset: {normalized}") from exc


def _validate_extra_assets() -> None:
    """Operator-added assets must be pluggable, not a new universe.

    An added asset joins an existing group (so it routes into the accounts that
    already trade that group) and must be claimed by at least one strategy,
    otherwise it would sit in the universe and never be scanned.
    """
    groups = known_asset_groups()
    strategies = known_strategy_ids()
    for symbol, asset in EXTRA_ASSETS.items():
        if symbol != symbol.strip().upper() or not symbol:
            raise ValueError(f"Asset symbol must be upper case: {symbol!r}")
        # Checked against the shipped tuple, not LIVE_ASSET_MAP: an added asset is in
        # the map by the time this runs, because rebuild_asset_map() ran first.
        if asset.symbol in BUILTIN_ASSET_SYMBOLS:
            raise ValueError(f"Asset is already in the shipped universe: {symbol}")
        if not asset.yahoo_symbol.strip():
            raise ValueError(f"{symbol}: a Yahoo symbol is required")
        if not asset.label.strip():
            raise ValueError(f"{symbol}: a label is required")
        if asset.group not in groups:
            raise ValueError(
                f"{symbol}: group must be one of {', '.join(groups)}; "
                "an added asset plugs into an existing account group"
            )
        if asset.currency not in {"INR", "USD"}:
            raise ValueError(f"{symbol}: currency must be INR or USD")
        expected = GROUP_SWEEP_TIMEFRAME[asset.group]
        if asset.sweep_timeframe != expected:
            raise ValueError(f"{symbol}: {asset.group} assets sweep on {expected}")
        wanted = GROUP_MARKET[asset.group]
        if wanted and asset.market != wanted:
            raise ValueError(f"{symbol}: {asset.group} assets are on the {wanted} market")
        scanned = EXTRA_ASSET_STRATEGIES.get(symbol, ())
        if not scanned:
            raise ValueError(f"{symbol}: choose at least one strategy to scan it")
        unknown = set(scanned) - set(strategies)
        if unknown:
            raise ValueError(f"{symbol}: unknown strategy: {sorted(unknown)[0]}")


def validate_configuration() -> None:
    if len(NSE_15_SYMBOLS) != 15:
        raise ValueError("NSE stock universe must contain 15 assets")

    if len(LIVE_ASSETS) != 25:
        raise ValueError(
            f"Live universe must contain exactly 25 assets; found {len(LIVE_ASSETS)}"
        )

    if len(set(BUILTIN_SYMBOLS)) != 25:
        raise ValueError("Live universe contains duplicate symbols")

    if set(NIFTY_SYMBOLS) != {"^NSEI", "^NSEBANK"}:
        raise ValueError("NIFTY index configuration is invalid")

    if GOLD_SYMBOL not in LIVE_ASSET_MAP:
        raise ValueError("Gold is missing from live universe")

    if BITCOIN_SYMBOL not in LIVE_ASSET_MAP:
        raise ValueError("Bitcoin is missing from live universe")

    if set(FOREX_SYMBOLS) - set(LIVE_ASSET_MAP):
        raise ValueError("Approved Forex universe is missing an asset")

    if set(LIVE_ASSET_MAP) != set(LIVE_SYMBOLS):
        raise ValueError("Live asset metadata must cover all live assets")

    for symbol in NSE_15_SYMBOLS:
        if LIVE_ASSET_MAP[symbol].sweep_timeframe != "4H":
            raise ValueError(f"{symbol} Sweep must be 4H")

    if LIVE_ASSET_MAP["^NSEI"].sweep_timeframe != "1H" or LIVE_ASSET_MAP["^NSEBANK"].sweep_timeframe != "1H":
        raise ValueError("NIFTY indexes Sweep must be 1H")

    if LIVE_ASSET_MAP[GOLD_SYMBOL].sweep_timeframe != "4H" or LIVE_ASSET_MAP[BITCOIN_SYMBOL].sweep_timeframe != "4H":
        raise ValueError("Global Sweep must be 4H")

    for symbol in FOREX_SYMBOLS:
        asset = LIVE_ASSET_MAP[symbol]
        if asset.market != "Forex" or asset.asset_type != "forex" or asset.sweep_timeframe != "4H":
            raise ValueError(f"{symbol} Forex configuration is invalid")

    if USD_TO_INR <= 0:
        raise ValueError("USD_TO_INR must be positive")

    if LEVERAGE != 1.0:
        raise ValueError("Leverage must remain 1x")

    if settings.freshness_hours != 1:
        raise ValueError("Signal freshness must remain 1 hour")

    if set(ACCOUNT_TRADE_LIMITS) != set(ACCOUNT_NAMES):
        raise ValueError("Account configuration mismatch")

    if set(ACCOUNT_SIZES) != set(ACCOUNT_NAMES) or set(ACCOUNT_RISK_PER_TRADE) != set(ACCOUNT_NAMES):
        raise ValueError("Account value configuration mismatch")

    # Account values are operator-editable, so these check the *bounds* an
    # account has to stay inside rather than pinning one number. A book that
    # cannot fund its own risk budget is worse than a missing account: it would
    # size positions it cannot pay for.
    for name in ACCOUNT_NAMES:
        size = ACCOUNT_SIZES[name]
        limit = ACCOUNT_TRADE_LIMITS[name]
        risk = ACCOUNT_RISK_PER_TRADE[name]
        if not ACCOUNT_MIN_SIZE_INR <= size <= ACCOUNT_MAX_SIZE_INR:
            raise ValueError(f"{name}: starting balance must be within the allowed range")
        if not ACCOUNT_MIN_TRADE_LIMIT <= limit <= ACCOUNT_MAX_TRADE_LIMIT:
            raise ValueError(f"{name}: daily trade limit must be within the allowed range")
        if not ACCOUNT_MIN_RISK_INR <= risk <= ACCOUNT_MAX_RISK_INR:
            raise ValueError(f"{name}: risk per trade must be within the allowed range")
        if risk > size:
            raise ValueError(f"{name}: risk per trade cannot exceed its starting balance")
        if risk * limit > size:
            raise ValueError(f"{name}: daily risk budget exceeds its starting balance")

    _validate_extra_assets()

    # Every rule must name an account that exists, so a typo in the routing
    # table fails at startup instead of routing trades to a non-existent book.
    for rule in ACCOUNT_ROUTING:
        if rule.account not in ACCOUNT_NAMES:
            raise ValueError(f"Routing rule names unknown account: {rule.account}")

    # Every asset group in the universe must be claimed by at least one rule.
    # An unclaimed group would silently fall through to the manifest fallback,
    # which is how the original static routing problem comes back.
    claimed: set[str] = set()
    for rule in ACCOUNT_ROUTING:
        # `None` means every group, so such a rule claims all of them.
        claimed.update(rule.asset_groups if rule.asset_groups is not None
                       else known_asset_groups())
    for asset in LIVE_ASSETS:
        if asset.group not in claimed:
            raise ValueError(f"No routing rule covers asset group: {asset.group}")


validate_configuration()
