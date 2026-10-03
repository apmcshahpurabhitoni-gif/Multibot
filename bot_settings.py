"""Server-side, operator-editable configuration: accounts, assets and routing.

Everything here decides what the bot trades and whose book it hits, so none of
it can live in the browser. The Tools screen posts an edited document here, it
is validated against the same invariants `config.validate_configuration()`
enforces at startup, written to disk, and pushed into the running process.

Three things are editable and all three have compiled-in defaults that are
never overwritten, so "reset to defaults" always has something to return to:

* **accounts** — name, capital, daily trade limit, risk per trade.
* **assets** — an extra instrument plugged into an *existing* account group and
  routed to the accounts that already trade that group. It cannot invent a new
  group, a new account, or a market that group does not sit on.
* **routing** — which account takes which (strategy, asset group, session).

A change is applied whole or refused whole: a rejected edit leaves the running
configuration exactly as it was.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Iterable

import config
from config import AssetConfig, RoutingRule

logger = logging.getLogger("multibot2.bot_settings")

#: Persisted next to the project so a checkout carries its own configuration.
#: Overridable so tests (and a read-only deployment) can point elsewhere.
DEFAULT_SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "bot_settings.json"
)

ACCOUNT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,30}$")


def settings_path() -> str:
    return os.getenv("BOT_SETTINGS_PATH") or DEFAULT_SETTINGS_PATH


# ---------------------------------------------------------------------------
# Canonical shape
# ---------------------------------------------------------------------------

def default_settings() -> dict:
    """The compiled-in configuration in the persisted shape.

    Read from the immutable DEFAULT_* values, never from the live ones: this is
    what "reset to defaults" restores, so it must not drift to whatever was last
    saved.
    """
    return {
        "accounts": [
            {
                "name": name,
                "starting_balance": config.DEFAULT_ACCOUNT_SIZE_INR,
                "daily_trade_limit": config.DEFAULT_ACCOUNT_TRADE_LIMITS[name],
                "risk_per_trade": config.DEFAULT_RISK_PER_TRADE_INR,
            }
            for name in config.BUILTIN_ACCOUNT_NAMES
        ],
        "assets": [],
        "session": {
            "timezone": config.NY_SESSION_TZ,
            "start_hour": config.DEFAULT_NY_SESSION_START_HOUR,
            "end_hour": config.DEFAULT_NY_SESSION_END_HOUR,
        },
        "rules": [
            {
                "account": rule.account,
                "strategies": list(rule.strategies) if rule.strategies else None,
                "asset_groups": list(rule.asset_groups) if rule.asset_groups else None,
                "in_ny_session": rule.in_ny_session,
            }
            for rule in config.DEFAULT_ACCOUNT_ROUTING
        ],
    }


def known_strategy_ids() -> tuple[str, ...]:
    """Strategy ids a rule or an asset is allowed to name."""
    return config.known_strategy_ids()


def live_strategy_groups() -> tuple[tuple[str, str], ...]:
    """(strategy_id, asset_group) pairs that actually exist in the universe.

    Reachability is checked against this rather than the full cross product so a
    strategy that does not trade an asset group can never make an account look
    reachable when it is not.
    """
    pairs: dict[tuple[str, str], None] = {}
    for strategy in _strategies():
        by_group = {config.LIVE_ASSET_MAP[s].group for s in strategy.manifest.assets
                    if s in config.LIVE_ASSET_MAP}
        for group in by_group:
            pairs[(strategy.manifest.id, group)] = None
    for symbol, scanned in config.EXTRA_ASSET_STRATEGIES.items():
        group = config.LIVE_ASSET_MAP[symbol].group if symbol in config.LIVE_ASSET_MAP else None
        if group:
            for strategy_id in scanned:
                pairs[(strategy_id, group)] = None
    return tuple(pairs)


def _strategies():
    from strategies.registry import discover_strategies

    return discover_strategies().all()


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _clean_optional_id_list(value: Any, label: str, allowed: Iterable[str]) -> list[str] | None:
    """Normalise a nullable list of known ids, or raise."""
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list or null")
    allowed = set(allowed)
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{label} must contain only names")
        if item not in allowed:
            raise ValueError(f"{label} contains an unknown name: {item}")
        if item in out:
            raise ValueError(f"{label} repeats {item}")
        out.append(item)
    if not out:
        raise ValueError(f"{label} must select at least one name, or null for all")
    return out


def _clean_hour(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be a whole hour between 0 and 23")
    if not 0 <= value <= 23:
        raise ValueError(f"{label} must be between 0 and 23")
    return value


def _clean_number(value: Any, label: str, low: float, high: float, *, whole: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    if whole and not float(value).is_integer():
        raise ValueError(f"{label} must be a whole number")
    number = float(value)
    if not low <= number <= high:
        raise ValueError(f"{label} must be between {low:,.0f} and {high:,.0f}")
    return int(number) if whole else number


def _normalize_accounts(raw: Any) -> list[dict]:
    if not isinstance(raw, list):
        raise ValueError("Settings are missing the account list")
    if not raw:
        raise ValueError("At least one account is required")
    out: list[dict] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"Account {index + 1} must be an object")
        name = item.get("name")
        if not isinstance(name, str) or not ACCOUNT_NAME_PATTERN.match(name):
            raise ValueError(
                "Account names must be lower case letters, digits and underscores "
                f"(2-31 characters); got {name!r}"
            )
        if name in seen:
            raise ValueError(f"Account {name} is listed twice")
        seen.add(name)
        size = _clean_number(item.get("starting_balance"), f"{name} starting balance",
                             config.ACCOUNT_MIN_SIZE_INR, config.ACCOUNT_MAX_SIZE_INR)
        limit = _clean_number(item.get("daily_trade_limit"), f"{name} daily trade limit",
                              config.ACCOUNT_MIN_TRADE_LIMIT, config.ACCOUNT_MAX_TRADE_LIMIT, whole=True)
        risk = _clean_number(item.get("risk_per_trade"), f"{name} risk per trade",
                             config.ACCOUNT_MIN_RISK_INR, config.ACCOUNT_MAX_RISK_INR)
        # A book that cannot fund its own daily budget would size positions it
        # cannot pay for, so this is rejected rather than clamped.
        if risk > size:
            raise ValueError(f"{name}: risk per trade cannot exceed its starting balance")
        if risk * limit > size:
            raise ValueError(
                f"{name}: {limit} trades at {risk:,.0f} risk is "
                f"{risk * limit:,.0f}, more than its {size:,.0f} balance"
            )
        out.append({"name": name, "starting_balance": size,
                    "daily_trade_limit": limit, "risk_per_trade": risk})

    # The four shipped books are the contract the routing table and the docs are
    # written around, so they cannot be deleted from the dashboard.
    missing = [name for name in config.BUILTIN_ACCOUNT_NAMES if name not in seen]
    if missing:
        raise ValueError("Built-in accounts cannot be removed: " + ", ".join(missing))
    return out


def _normalize_assets(raw: Any) -> list[dict]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("Settings are missing the asset list")
    groups = config.known_asset_groups()
    strategies = known_strategy_ids()
    out: list[dict] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"Asset {index + 1} must be an object")
        symbol = item.get("symbol")
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError(f"Asset {index + 1} needs a symbol")
        symbol = symbol.strip().upper()
        if symbol in seen:
            raise ValueError(f"Asset {symbol} is listed twice")
        if symbol in config.LIVE_ASSET_MAP and symbol not in config.EXTRA_ASSETS:
            raise ValueError(f"{symbol} is already in the shipped universe")
        seen.add(symbol)
        label = item.get("label")
        yahoo_symbol = item.get("yahoo_symbol")
        for field, value in (("label", label), ("yahoo_symbol", yahoo_symbol)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{symbol}: {field.replace('_', ' ')} is required")
        group = item.get("group")
        if group not in groups:
            raise ValueError(
                f"{symbol}: group must be one of {', '.join(groups)}; an added asset "
                "plugs into an existing account group"
            )
        market = item.get("market") or config.GROUP_MARKET.get(group) or "Global"
        currency = item.get("currency") or "USD" if group == "Global Markets" else "INR"
        asset_type = item.get("asset_type") or _default_asset_type(group)
        out.append({
            "symbol": symbol,
            "label": label.strip(),
            "yahoo_symbol": yahoo_symbol.strip(),
            "market": market,
            "asset_type": asset_type,
            "group": group,
            "currency": currency,
            "sweep_timeframe": config.GROUP_SWEEP_TIMEFRAME[group],
            "strategies": _clean_optional_id_list(
                item.get("strategies"), f"{symbol} strategies", strategies) or strategies,
        })
    return out


def _default_asset_type(group: str) -> str:
    return {"NSE Stocks": "equity", "NSE Indices": "index"}.get(group, "commodity")


def _normalize_rules(raw: Any, accounts: list[str]) -> list[dict]:
    if not isinstance(raw, list):
        raise ValueError("Settings are missing the rule list")
    if len(raw) != len(accounts):
        raise ValueError(
            f"The routing table needs exactly one rule per account "
            f"({len(accounts)}), got {len(raw)}"
        )
    strategies = known_strategy_ids()
    groups = config.known_asset_groups()
    rules: list[dict] = []
    seen: set[str] = set()
    for index, raw_rule in enumerate(raw):
        if not isinstance(raw_rule, dict):
            raise ValueError(f"Rule {index + 1} must be an object")
        account = raw_rule.get("account")
        if account not in accounts:
            raise ValueError(f"Rule {index + 1} names an unknown account: {account}")
        if account in seen:
            raise ValueError(f"Account {account} has more than one rule")
        seen.add(account)
        window = raw_rule.get("in_ny_session")
        if window is not None and not isinstance(window, bool):
            raise ValueError(f"{account}: New York session must be any, inside or outside")
        rules.append({
            "account": account,
            "strategies": _clean_optional_id_list(raw_rule.get("strategies"), f"{account} strategies", strategies),
            "asset_groups": _clean_optional_id_list(raw_rule.get("asset_groups"), f"{account} asset groups", groups),
            "in_ny_session": window,
        })
    return rules


def _resolve(state: dict, strategy_id: str, group: str, ny_session: bool) -> str | None:
    for rule in state["rules"]:
        matcher = RoutingRule(
            rule["account"],
            tuple(rule["strategies"]) if rule["strategies"] else None,
            tuple(rule["asset_groups"]) if rule["asset_groups"] else None,
            rule["in_ny_session"],
        )
        if matcher.matches(strategy_id, group, ny_session):
            return rule["account"]
    return None


def _check_reachable(state: dict) -> None:
    """Every account must win at least one real (strategy, group, session).

    Without this an account can be narrowed away by a rule above it and still
    sit in the accounts list looking healthy while it never trades.
    """
    reached: set[str] = set()
    for strategy_id, group in live_strategy_groups():
        for ny_session in (False, True):
            account = _resolve(state, strategy_id, group, ny_session)
            if account is not None:
                reached.add(account)
    missing = [a for a in state["_accounts"] if a not in reached]
    if missing:
        raise ValueError("No signal can ever route to: " + ", ".join(missing))


def _check_group_coverage(rules: list[dict]) -> None:
    """Every live group must be claimed, or signals fall through to a fallback."""
    claimed: set[str] = set()
    for rule in rules:
        # `None` means every group, so such a rule claims all of them.
        claimed.update(rule["asset_groups"] if rule["asset_groups"] is not None
                       else config.known_asset_groups())
    for group in config.known_asset_groups():
        if group not in claimed:
            raise ValueError(f"No routing rule covers asset group: {group}")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def normalize(payload: Any) -> dict:
    """Validate an incoming document and return it in canonical shape.

    Raises ValueError with a message meant to be shown verbatim in the dashboard
    status line, so a bad edit never reaches the operator as a traceback.
    """
    if not isinstance(payload, dict):
        raise ValueError("Settings must be an object")

    accounts = _normalize_accounts(payload.get("accounts"))
    names = [a["name"] for a in accounts]
    assets = _normalize_assets(payload.get("assets"))

    raw_session = payload.get("session")
    if not isinstance(raw_session, dict):
        raise ValueError("Settings are missing the session window")
    start_hour = _clean_hour(raw_session.get("start_hour"), "Session start hour")
    end_hour = _clean_hour(raw_session.get("end_hour"), "Session end hour")
    if start_hour >= end_hour:
        raise ValueError("Session start hour must be earlier than the end hour")

    rules = _normalize_rules(payload.get("rules"), names)
    state = {
        "accounts": accounts,
        "assets": assets,
        "session": {"timezone": config.NY_SESSION_TZ, "start_hour": start_hour, "end_hour": end_hour},
        "rules": rules,
        # Private, used only by _check_reachable while validating.
        "_accounts": names,
    }
    _check_group_coverage(rules)
    _check_reachable(state)
    state.pop("_accounts")
    return state


# ---------------------------------------------------------------------------
# Persistence and application
# ---------------------------------------------------------------------------

def apply(state: dict) -> dict:
    """Install a validated document into the running process.

    The account value maps and the asset maps are rewritten *in place* so that
    modules which did `from config import ACCOUNT_TRADE_LIMITS` keep resolving
    the current values instead of a snapshot taken at import time.
    """
    sizes = {a["name"]: a["starting_balance"] for a in state["accounts"]}
    limits = {a["name"]: a["daily_trade_limit"] for a in state["accounts"]}
    risks = {a["name"]: a["risk_per_trade"] for a in state["accounts"]}

    config.ACCOUNT_SIZES.clear(); config.ACCOUNT_SIZES.update(sizes)
    config.ACCOUNT_TRADE_LIMITS.clear(); config.ACCOUNT_TRADE_LIMITS.update(limits)
    config.ACCOUNT_RISK_PER_TRADE.clear(); config.ACCOUNT_RISK_PER_TRADE.update(risks)
    config.ACCOUNT_NAMES = tuple(sizes)

    extras = {a["symbol"]: AssetConfig(
        symbol=a["symbol"], label=a["label"], yahoo_symbol=a["yahoo_symbol"],
        market=a["market"], asset_type=a["asset_type"], group=a["group"],
        currency=a["currency"], sweep_timeframe=a["sweep_timeframe"],
    ) for a in state["assets"]}
    scanned = {a["symbol"]: tuple(a["strategies"]) for a in state["assets"]}
    config.EXTRA_ASSETS.clear(); config.EXTRA_ASSETS.update(extras)
    config.EXTRA_ASSET_STRATEGIES.clear(); config.EXTRA_ASSET_STRATEGIES.update(scanned)
    config.rebuild_asset_map()

    config.ACCOUNT_ROUTING = tuple(
        RoutingRule(r["account"],
                    tuple(r["strategies"]) if r["strategies"] else None,
                    tuple(r["asset_groups"]) if r["asset_groups"] else None,
                    r["in_ny_session"])
        for r in state["rules"]
    )
    config.NY_SESSION_START_HOUR = state["session"]["start_hour"]
    config.NY_SESSION_END_HOUR = state["session"]["end_hour"]
    # Re-check the same invariants startup enforces, against the live values.
    config.validate_configuration()
    return state


def _write(path: str, state: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=False)
        handle.write("\n")
    os.replace(tmp, path)


def load() -> dict:
    """Return the saved document, falling back to the compiled-in defaults.

    A missing, unreadable or invalid file must never stop the bot from starting,
    so every failure degrades to the defaults with a warning.
    """
    path = settings_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except FileNotFoundError:
        return apply(default_settings())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Settings unreadable; using defaults | path=%s error=%s", path, exc)
        return apply(default_settings())

    try:
        return apply(normalize(raw))
    except ValueError as exc:
        logger.warning("Settings invalid; using defaults | path=%s error=%s", path, exc)
        return apply(default_settings())


def save(payload: Any) -> dict:
    """Validate, persist and apply an operator's edited document."""
    state = normalize(payload)
    path = settings_path()
    try:
        _write(path, state)
    except OSError as exc:
        raise ValueError(f"Could not write {path}: {exc}") from exc
    logger.info(
        "Settings updated | accounts=%d assets=%d session=%s-%s",
        len(state["accounts"]), len(state["assets"]),
        state["session"]["start_hour"], state["session"]["end_hour"],
    )
    return apply(state)


def reset() -> dict:
    """Drop the saved file and go back to the compiled-in configuration."""
    try:
        os.remove(settings_path())
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise ValueError(f"Could not remove {settings_path()}: {exc}") from exc
    return apply(default_settings())


def settings_state() -> dict:
    """The live document, for the dashboard.

    Read live rather than from the last saved copy so a value changed by any
    route is visible without a restart.
    """
    return {
        "accounts": config.accounts_state(),
        "assets": [
            {
                "symbol": asset.symbol, "label": asset.label,
                "yahoo_symbol": asset.yahoo_symbol, "market": asset.market,
                "asset_type": asset.asset_type, "group": asset.group,
                "currency": asset.currency, "sweep_timeframe": asset.sweep_timeframe,
                "strategies": list(config.EXTRA_ASSET_STRATEGIES.get(asset.symbol, ())),
            }
            for asset in config.live_assets() if asset.symbol in config.EXTRA_ASSETS
        ],
        "session": {
            "timezone": config.NY_SESSION_TZ,
            "start_hour": config.NY_SESSION_START_HOUR,
            "end_hour": config.NY_SESSION_END_HOUR,
        },
        "rules": config.routing_state()["rules"],
        "options": {
            "account_groups": list(config.known_asset_groups()),
            "strategies": list(known_strategy_ids()),
            "strategy_names": {s.manifest.id: s.manifest.name for s in _strategies()},
            "asset_types": ["equity", "index", "commodity", "crypto", "forex"],
            "currencies": ["INR", "USD"],
            "limits": {
                "min_size": config.ACCOUNT_MIN_SIZE_INR,
                "max_size": config.ACCOUNT_MAX_SIZE_INR,
                "min_trade_limit": config.ACCOUNT_MIN_TRADE_LIMIT,
                "max_trade_limit": config.ACCOUNT_MAX_TRADE_LIMIT,
                "min_risk": config.ACCOUNT_MIN_RISK_INR,
                "max_risk": config.ACCOUNT_MAX_RISK_INR,
            },
        },
    }