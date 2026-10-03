"""Accounts, assets and routing must be editable from the dashboard without
becoming corruptable.

Each of these decides what the bot trades and whose book it hits, so the Tools
screen writes them server-side. These tests pin both halves of that bargain:
the compiled-in configuration still validates, and anything the screen can send
is either applied whole or refused whole.

Defaults are preserved by construction, so most assertions here are about the
*shape* of what is accepted and refused rather than about specific numbers.
"""
from __future__ import annotations

import json
import os

import pandas as pd
import pytest

import bot_settings
import config
from bot_settings import default_settings, normalize, reset, save


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Point persistence at a temp file and restore the built-in state after."""
    monkeypatch.setenv("BOT_SETTINGS_PATH", str(tmp_path / "bot_settings.json"))
    path = tmp_path / "bot_settings.json"
    yield path
    bot_settings.apply(default_settings())


def document(**changes):
    doc = default_settings()
    doc.update(changes)
    return doc


def add_account(doc, name="scalp", **overrides):
    """Add a reachable account: a sweep slice nothing else claims."""
    account = {"name": name, "starting_balance": 250_000,
               "daily_trade_limit": 40, "risk_per_trade": 500}
    account.update(overrides)
    doc["accounts"].append(account)
    rule = {"account": name, "strategies": ["sweep_v2"],
            "asset_groups": ["NSE Indices"], "in_ny_session": None}
    # Before the sweep_4h catch-all, or that rule swallows every sweep signal
    # and the new account is rejected as unreachable.
    doc["rules"].insert(len(doc["rules"]) - 1, rule)
    return doc


def add_asset(doc, symbol="TATAMOTORS", **overrides):
    asset = {"symbol": symbol, "label": "Tata Motors", "yahoo_symbol": "TATAMOTORS.NS",
             "market": "NSE", "asset_type": "equity", "group": "NSE Stocks",
             "currency": "INR", "strategies": ["engulfing_66_sma"]}
    asset.update(overrides)
    doc["assets"].append(asset)
    return doc


# --------------------------------------------------------------------------
# The shipped configuration is still a valid configuration
# --------------------------------------------------------------------------

def test_built_in_document_passes_its_own_validator():
    assert normalize(default_settings()) == default_settings()


def test_built_in_routing_matches_the_specified_table():
    state = normalize(default_settings())
    routed = {}
    for strategy_id, group in bot_settings.live_strategy_groups():
        for ny_session in (False, True):
            routed[(strategy_id, group, ny_session)] = bot_settings._resolve(
                state, strategy_id, group, ny_session)
    assert routed[("engulfing_66_sma", "NSE Stocks", False)] == "nifty"
    assert routed[("engulfing_66_sma", "NSE Indices", True)] == "nifty"
    assert routed[("adaptive_trend", "Global Markets", False)] == "macro"
    assert routed[("adaptive_trend", "Global Markets", True)] == "ny_session"
    assert routed[("sweep_v2", "Global Markets", False)] == "sweep_4h"
    assert routed[("sweep_v2", "Global Markets", True)] == "ny_session"


def test_built_in_account_values_are_preserved():
    assert default_settings()["accounts"] == [
        {"name": "macro", "starting_balance": 100_000, "daily_trade_limit": 20, "risk_per_trade": 2_000},
        {"name": "nifty", "starting_balance": 100_000, "daily_trade_limit": 5, "risk_per_trade": 2_000},
        {"name": "ny_session", "starting_balance": 100_000, "daily_trade_limit": 3, "risk_per_trade": 2_000},
        {"name": "sweep_4h", "starting_balance": 100_000, "daily_trade_limit": 3, "risk_per_trade": 2_000},
    ]


def test_defaults_are_not_written_to_disk(isolated_settings):
    reset()
    assert not isolated_settings.exists()


# --------------------------------------------------------------------------
# Adding an account
# --------------------------------------------------------------------------

def test_an_added_account_is_applied_with_its_own_values():
    save(add_account(default_settings()))

    assert config.account_names()[-1] == "scalp"
    assert config.ACCOUNT_SIZES["scalp"] == 250_000
    assert config.ACCOUNT_TRADE_LIMITS["scalp"] == 40
    assert config.ACCOUNT_RISK_PER_TRADE["scalp"] == 500


def test_adding_an_account_leaves_the_built_in_books_alone():
    save(add_account(default_settings()))

    assert config.ACCOUNT_SIZES["macro"] == 100_000
    assert config.ACCOUNT_TRADE_LIMITS["macro"] == 20
    assert config.ACCOUNT_RISK_PER_TRADE["macro"] == 2_000


def test_an_added_account_actually_receives_signals():
    save(add_account(default_settings()))
    at = pd.Timestamp("2026-01-05 12:00", tz="Asia/Kolkata")
    assert config.resolve_account("sweep_v2", config.LIVE_ASSET_MAP["^NSEI"], at, "x") == "scalp"


def test_a_shadowed_account_is_refused():
    # Placed after the sweep_4h catch-all, so nothing can ever reach it.
    doc = default_settings()
    doc["accounts"].append({"name": "scalp", "starting_balance": 250_000,
                            "daily_trade_limit": 40, "risk_per_trade": 500})
    doc["rules"].append({"account": "scalp", "strategies": ["sweep_v2"],
                         "asset_groups": ["NSE Indices"], "in_ny_session": None})
    with pytest.raises(ValueError, match="No signal can ever route to: scalp"):
        normalize(doc)


def test_removing_an_added_account_removes_it_from_the_running_config():
    save(add_account(default_settings()))
    doc = default_settings()
    save(doc)
    assert config.account_names() == config.BUILTIN_ACCOUNT_NAMES


@pytest.mark.parametrize("overrides,expected", [
    ({"starting_balance": 0}, "between"),
    ({"starting_balance": 10**9}, "between"),
    ({"daily_trade_limit": 0}, "between"),
    ({"daily_trade_limit": 100_000}, "between"),
    ({"risk_per_trade": 1}, "between"),
    ({"starting_balance": 1_000, "risk_per_trade": 5_000}, "cannot exceed"),
    ({"starting_balance": 10_000, "daily_trade_limit": 40, "risk_per_trade": 5_000},
     "more than its"),
])
def test_unfundable_accounts_are_refused(overrides, expected):
    with pytest.raises(ValueError) as caught:
        normalize(add_account(default_settings(), **overrides))
    assert expected in str(caught.value)


@pytest.mark.parametrize("name", ["Scalp", "1scalp", "a", "with space", "with-dash", ""])
def test_bad_account_names_are_refused(name):
    doc = default_settings()
    doc["accounts"].append({"name": name, "starting_balance": 250_000,
                            "daily_trade_limit": 40, "risk_per_trade": 500})
    with pytest.raises(ValueError, match="Account names must be"):
        normalize(doc)


def test_duplicate_accounts_are_refused():
    doc = default_settings()
    doc["accounts"].append(dict(doc["accounts"][0]))
    with pytest.raises(ValueError, match="listed twice"):
        normalize(doc)


def test_a_built_in_account_cannot_be_removed():
    doc = default_settings()
    doc["accounts"] = [a for a in doc["accounts"] if a["name"] != "macro"]
    with pytest.raises(ValueError, match="Built-in accounts cannot be removed: macro"):
        normalize(doc)


def test_a_rule_without_a_matching_account_is_refused():
    doc = add_account(default_settings())
    doc["accounts"].pop()          # keep the rule, drop the account
    with pytest.raises(ValueError, match="one rule per account"):
        normalize(doc)


# --------------------------------------------------------------------------
# Adding an asset
# --------------------------------------------------------------------------

def test_an_added_asset_joins_the_live_universe():
    save(add_asset(default_settings()))

    assert len(config.live_assets()) == 26
    assert config.LIVE_ASSET_MAP["TATAMOTORS"].label == "Tata Motors"


def test_an_added_asset_plugs_into_an_existing_account():
    save(add_asset(default_settings()))
    at = pd.Timestamp("2026-01-05 12:00", tz="Asia/Kolkata")
    # NSE Stocks is the nifty book, so a new NSE equity lands there without
    # anyone creating an account for it.
    assert config.resolve_account("engulfing_66_sma", config.LIVE_ASSET_MAP["TATAMOTORS"], at, "x") == "nifty"


def test_the_shipped_universe_is_untouched_by_an_added_asset():
    save(add_asset(default_settings()))

    assert len(config.BUILTIN_SYMBOLS) == 25
    assert config.BUILTIN_SYMBOLS == config.LIVE_SYMBOLS[:25]


def test_an_added_asset_records_which_strategies_scan_it():
    save(add_asset(default_settings()))

    assert config.EXTRA_ASSET_STRATEGIES["TATAMOTORS"] == ("engulfing_66_sma",)
    scanned = {a.symbol for a in config.assets_for_strategy("engulfing_66_sma")}
    assert "TATAMOTORS" in scanned
    assert "BTC-USD" in scanned, "the manifest's own assets must still be scanned"


@pytest.mark.parametrize("overrides,expected", [
    ({"group": "Crypto"}, "group must be one of"),
    ({"yahoo_symbol": ""}, "yahoo symbol is required"),
    ({"label": "  "}, "label is required"),
    ({"strategies": ["nope"]}, "unknown name"),
])
def test_unpluggable_assets_are_refused(overrides, expected):
    with pytest.raises(ValueError) as caught:
        normalize(add_asset(default_settings(), **overrides))
    assert expected in str(caught.value)


@pytest.mark.parametrize("group,timeframe", [
    ("NSE Stocks", "4H"), ("NSE Indices", "1H"), ("Global Markets", "4H"),
])
def test_sweep_timeframe_is_derived_from_the_group_not_trusted(group, timeframe):
    # The client cannot file a 1H index as a 4H asset: the timeframe follows
    # the group because the sweep engine needs a closed candle at that
    # resolution or it silently trades on a partial one.
    state = normalize(add_asset(default_settings(), group=group, sweep_timeframe="1m"))
    assert state["assets"][0]["sweep_timeframe"] == timeframe


def test_currency_is_derived_from_the_group_not_trusted():
    state = normalize(add_asset(default_settings(), currency="EUR"))
    assert state["assets"][0]["currency"] == "INR"


def test_a_duplicate_asset_symbol_is_refused():
    doc = add_asset(default_settings())
    doc["assets"].append(dict(doc["assets"][0]))
    with pytest.raises(ValueError, match="listed twice"):
        normalize(doc)


def test_a_shipped_asset_cannot_be_re_added():
    doc = default_settings()
    doc["assets"].append({"symbol": "RELIANCE", "label": "Reliance",
                          "yahoo_symbol": "RELIANCE.NS", "market": "NSE",
                          "asset_type": "equity", "group": "NSE Stocks",
                          "currency": "INR", "strategies": ["engulfing_66_sma"]})
    with pytest.raises(ValueError, match="already in the shipped universe"):
        normalize(doc)


# --------------------------------------------------------------------------
# Session hours and routing
# --------------------------------------------------------------------------

def test_session_hours_are_persisted_and_applied():
    doc = document(session={"start_hour": 7, "end_hour": 16})
    save(doc)
    bot_settings.load()

    assert config.NY_SESSION_START_HOUR == 7
    assert config.NY_SESSION_END_HOUR == 16
    # 15:30 IST is 06:00 New York in July, 18:30 IST is 09:00, 04:00 IST the
    # next day is 18:30 New York, so both sides of the window are probed.
    for stamp, inside in [("2026-07-17 15:30", False), ("2026-07-17 16:30", True),
                          ("2026-07-17 18:30", True), ("2026-07-18 04:00", False)]:
        assert config.in_new_york_session(pd.Timestamp(stamp, tz="Asia/Kolkata")) is inside, stamp


def test_reset_restores_the_compiled_in_configuration():
    save(add_account(add_asset(default_settings())))
    assert config.account_names()[-1] == "scalp"
    assert len(config.live_assets()) == 26

    reset()

    assert config.account_names() == config.BUILTIN_ACCOUNT_NAMES
    assert len(config.live_assets()) == 25
    assert not os.environ["BOT_SETTINGS_PATH"] or not os.path.exists(os.environ["BOT_SETTINGS_PATH"])


def test_a_saved_document_survives_a_reload():
    save(add_account(add_asset(default_settings())))
    reloaded = bot_settings.load()

    assert reloaded["accounts"][-1]["name"] == "scalp"
    assert reloaded["assets"][0]["symbol"] == "TATAMOTORS"
    assert config.ACCOUNT_NAMES == tuple(a["name"] for a in reloaded["accounts"])


def test_written_file_is_readable_json_in_the_canonical_shape(isolated_settings):
    save(add_asset(default_settings()))
    written = json.loads(isolated_settings.read_text())

    assert written["session"]["timezone"] == config.NY_SESSION_TZ
    assert len(written["accounts"]) == len(config.BUILTIN_ACCOUNT_NAMES)
    assert normalize(written) == written


# --------------------------------------------------------------------------
# Refusals leave the running configuration untouched
# --------------------------------------------------------------------------

@pytest.mark.parametrize("payload,expected", [
    (document(session={"start_hour": 17, "end_hour": 8}), "earlier"),
    (document(session={"start_hour": 24, "end_hour": 8}), "between 0 and 23"),
    (document(session={"start_hour": "08", "end_hour": 17}), "whole hour"),
    ({k: v for k, v in document().items() if k != "session"}, "session window"),
    ("not-an-object", "must be an object"),
    (document(accounts=[]), "At least one account"),
    ({k: v for k, v in document().items() if k != "accounts"}, "account list"),
])
def test_bad_documents_are_refused_with_a_readable_reason(payload, expected):
    with pytest.raises(ValueError) as caught:
        normalize(payload)
    assert expected in str(caught.value)


def test_an_unknown_routing_account_is_refused():
    doc = default_settings()
    doc["rules"][0]["account"] = "not_an_account"
    with pytest.raises(ValueError, match="unknown account"):
        normalize(doc)


def test_an_uncovered_asset_group_is_refused():
    every = config.known_asset_groups()
    for group in every:
        doc = default_settings()
        for rule in doc["rules"]:
            rule["asset_groups"] = [g for g in every if g != group]
        with pytest.raises(ValueError, match=f"No routing rule covers asset group: {group}"):
            normalize(doc)


def test_a_refused_save_leaves_the_running_configuration_untouched():
    before = (config.ACCOUNT_NAMES, config.ACCOUNT_SIZES["macro"], len(config.live_assets()))
    with pytest.raises(ValueError):
        save(add_account(default_settings(), risk_per_trade=10 ** 9))

    assert (config.ACCOUNT_NAMES, config.ACCOUNT_SIZES["macro"],
            len(config.live_assets())) == before
    assert not os.path.exists(os.environ["BOT_SETTINGS_PATH"])


# --------------------------------------------------------------------------
# A bad file on disk degrades to defaults instead of stopping the bot
# --------------------------------------------------------------------------

@pytest.mark.parametrize("content", ["{ not json", "null",
                                      '{"session": {"start_hour": 30}, "accounts": [], "rules": []}'])
def test_unusable_file_falls_back_to_defaults(isolated_settings, content):
    isolated_settings.write_text(content)

    assert bot_settings.load() == default_settings()
    assert config.account_names() == config.BUILTIN_ACCOUNT_NAMES
    assert len(config.live_assets()) == 25


# --------------------------------------------------------------------------
# Per-account risk actually reaches position sizing
# --------------------------------------------------------------------------

def test_position_size_follows_the_account_risk_budget():
    from trading import AccountState, quantity_for_risk, register_trade, TradingRuleError

    save(add_account(default_settings()))
    scalp = AccountState("scalp", 250_000.0, 250_000.0, 0.0, 0)
    macro = AccountState("macro", 100_000.0, 100_000.0, 0.0, 0)

    assert quantity_for_risk(100.0, 99.0, account=scalp) == 500.0
    assert quantity_for_risk(100.0, 99.0, account=macro) == 2_000.0

    with pytest.raises(TradingRuleError, match="scalp's ₹500 budget"):
        register_trade(scalp, planned_risk=900)


def test_a_rule_catching_every_group_counts_as_claiming_all_of_them(monkeypatch):
    """Regression: `None` groups means every group, not no groups."""
    monkeypatch.setattr(config, "ACCOUNT_ROUTING", (
        config.RoutingRule("nifty", None, None, None),
        config.RoutingRule("macro", None, ("Global Markets",), False),
        config.RoutingRule("ny_session", None, ("Global Markets",), True),
        config.RoutingRule("sweep_4h", ("sweep_v2",), None),
    ))
    config.validate_configuration()