"""Account routing: (strategy, asset, time) -> account.

The routing table replaced a single static `account` field on each strategy
manifest, which meant one strategy could only ever feed one account regardless
of what it scanned. These tests pin the table, the New York session boundary it
depends on, and the two guarantees that are easy to break by reordering it:
nothing double-fills, and nothing falls through to the manifest by accident.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import config
from config import (
    ACCOUNT_NAMES,
    ACCOUNT_ROUTING,
    LIVE_ASSETS,
    in_new_york_session,
    resolve_account,
)

IST = ZoneInfo("Asia/Kolkata")
NY = ZoneInfo("America/New_York")

TREND_STRATEGIES = ("adaptive_trend", "engulfing_66_sma")

NSE_GROUPS = ("NSE Stocks", "NSE Indices")
GLOBAL_GROUP = "Global Markets"


def _asset(group: str):
    return next(a for a in LIVE_ASSETS if a.group == group)


# Outside the New York session: 12:00 IST is 02:30 in New York.
OUTSIDE_NY = datetime(2026, 10, 3, 12, 0, tzinfo=IST)
# Inside it: 20:00 IST is 10:30 in New York during US daylight time.
INSIDE_NY = datetime(2026, 10, 3, 20, 0, tzinfo=IST)


def _matrix(now):
    return {
        (strategy, group): resolve_account(strategy, _asset(group), now, "FALLBACK")
        for strategy in ("adaptive_trend", "engulfing_66_sma", "sweep_v2")
        for group in (*NSE_GROUPS, GLOBAL_GROUP)
    }


def test_nifty_account_trades_the_trend_strategies_on_the_nse_universe():
    matrix = _matrix(OUTSIDE_NY)
    for strategy in TREND_STRATEGIES:
        for group in NSE_GROUPS:
            assert matrix[(strategy, group)] == "nifty", (
                f"{strategy} on {group} should route to nifty"
            )


def test_macro_trades_the_global_assets_outside_the_new_york_session():
    matrix = _matrix(OUTSIDE_NY)
    for strategy in TREND_STRATEGIES:
        assert matrix[(strategy, GLOBAL_GROUP)] == "macro"


def test_sweep_account_trades_the_sweep_strategy_on_every_asset():
    matrix = _matrix(OUTSIDE_NY)
    for group in (*NSE_GROUPS, GLOBAL_GROUP):
        assert matrix[("sweep_v2", group)] == "sweep_4h"


def test_global_assets_move_to_ny_session_inside_the_session():
    matrix = _matrix(INSIDE_NY)
    for strategy in (*TREND_STRATEGIES, "sweep_v2"):
        assert matrix[(strategy, GLOBAL_GROUP)] == "ny_session", (
            "every strategy takes the global assets during the New York session"
        )


def test_the_nse_universe_never_moves_to_the_new_york_session():
    inside = _matrix(INSIDE_NY)
    outside = _matrix(OUTSIDE_NY)
    for strategy in (*TREND_STRATEGIES, "sweep_v2"):
        for group in NSE_GROUPS:
            assert inside[(strategy, group)] == outside[(strategy, group)], (
                f"{strategy} on {group} must not depend on the clock"
            )


def test_macro_and_ny_session_can_never_double_fill_the_same_signal():
    """The guarantee that motivated splitting macro by time rather than by group.

    Both books cover the global assets. They must be disjoint at every instant,
    or one signal would open two positions totalling twice the planned risk.
    """
    global_assets = [a for a in LIVE_ASSETS if a.group == GLOBAL_GROUP]
    assert global_assets
    base = datetime(2026, 10, 3, 0, 0, tzinfo=IST)
    for hour in range(24):
        now = base + timedelta(hours=hour)
        for asset in global_assets:
            for strategy in TREND_STRATEGIES:
                account = resolve_account(strategy, asset, now, "FALLBACK")
                expected = "ny_session" if in_new_york_session(now) else "macro"
                assert account == expected, (
                    f"at IST {now:%H:%M} {strategy}/{asset.symbol} routed to "
                    f"{account}, expected {expected}"
                )


def test_each_strategy_and_asset_resolves_to_exactly_one_account_at_any_instant():
    """Routing is a function: one instant, one account, never a tie.

    A (strategy, asset) pair may legitimately change account across the day --
    the sweep book covers the global assets outside the session and hands them
    to ny_session inside it -- but at any single instant there is exactly one.
    """
    base = datetime(2026, 10, 3, 0, 0, tzinfo=IST)
    for hour in range(24):
        now = base + timedelta(hours=hour)
        for strategy in (*TREND_STRATEGIES, "sweep_v2"):
            for asset in LIVE_ASSETS:
                first = resolve_account(strategy, asset, now, "FALLBACK")
                second = resolve_account(strategy, asset, now, "FALLBACK")
                assert first == second, (
                    f"{strategy}/{asset.symbol} is not deterministic at {now:%H:%M}"
                )
                assert first in ACCOUNT_NAMES


@pytest.mark.parametrize("ist_hour,expected", [
    (12, False), (17, False), (18, True), (20, True), (23, True),
    (0, True), (1, True), (2, True), (6, False),
])
def test_new_york_session_boundaries_in_ist(ist_hour, expected):
    now = datetime(2026, 10, 3, ist_hour, 0, tzinfo=IST)
    assert in_new_york_session(now) is expected


def test_session_is_expressed_in_new_york_time_so_dst_is_handled():
    """The window follows US daylight time instead of drifting by an hour.

    08:00 New York is 17:30 IST while US daylight time is in force and 18:30 IST
    outside it. The same IST time therefore lands on opposite sides of the
    boundary depending on the season, which is exactly what a hardcoded IST
    window would get wrong twice a year.
    """
    # 17:30 IST is the session start in July and still before it in December.
    assert in_new_york_session(datetime(2026, 7, 1, 17, 30, tzinfo=IST)) is True
    assert in_new_york_session(datetime(2026, 12, 1, 17, 30, tzinfo=IST)) is False
    # ...and 19:00 IST is inside the session in both.
    assert in_new_york_session(datetime(2026, 7, 1, 19, 0, tzinfo=IST)) is True
    assert in_new_york_session(datetime(2026, 12, 1, 19, 0, tzinfo=IST)) is True
    # The window is 08:00-17:00 New York in both seasons.
    assert datetime(2026, 7, 1, 18, 0, tzinfo=IST).astimezone(NY).hour == 8
    assert datetime(2026, 12, 1, 19, 0, tzinfo=IST).astimezone(NY).hour == 8


def test_every_live_asset_routes_to_a_real_account():
    now = OUTSIDE_NY
    for asset in LIVE_ASSETS:
        for strategy in (*TREND_STRATEGIES, "sweep_v2"):
            account = resolve_account(strategy, asset, now, "FALLBACK")
            assert account in ACCOUNT_NAMES, (
                f"{strategy}/{asset.symbol} routed to unknown account {account}"
            )


def test_unknown_strategy_falls_back_to_its_manifest_account():
    """A newly added strategy keeps trading somewhere instead of vanishing."""
    asset = _asset(NSE_GROUPS[0])
    assert resolve_account("brand_new_strategy", asset, OUTSIDE_NY, "macro") == "macro"


def test_every_routing_rule_names_a_real_account():
    for rule in ACCOUNT_ROUTING:
        assert rule.account in ACCOUNT_NAMES


def test_trade_limits_are_untouched_by_routing():
    """Routing changed who trades what, not how much anyone may trade."""
    from config import ACCOUNT_TRADE_LIMITS, DEFAULT_ACCOUNT_TRADE_LIMITS

    assert DEFAULT_ACCOUNT_TRADE_LIMITS == {
        "macro": 20, "nifty": 5, "ny_session": 3, "sweep_4h": 3,
    }
    assert all(ACCOUNT_TRADE_LIMITS[name] == limit
               for name, limit in DEFAULT_ACCOUNT_TRADE_LIMITS.items())