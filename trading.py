"""Canonical paper-trading, sizing, and account-risk rules."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
import pandas as pd
from config import (
    ACCOUNT_MAX_RISK_INR,
    ACCOUNT_MAX_SIZE_INR,
    ACCOUNT_MAX_TRADE_LIMIT,
    ACCOUNT_MIN_RISK_INR,
    ACCOUNT_MIN_SIZE_INR,
    ACCOUNT_MIN_TRADE_LIMIT,
    ACCOUNT_RISK_PER_TRADE,
    ACCOUNT_SIZE_INR,
    ACCOUNT_SIZES,
    ACCOUNT_TRADE_LIMITS,
    LEVERAGE,
    RISK_PER_TRADE_INR,
    SIGNAL_FRESHNESS_HOURS,
    account_names,
)
from signal_gate import normalize_timestamp, is_fresh_age

TradeSide = Literal["BUY", "SELL"]
TradeStatus = Literal["OPEN", "CLOSED"]

class TradingRuleError(ValueError):
    pass

@dataclass(frozen=True)
class TradePlan:
    strategy: str
    side: TradeSide
    signal_timestamp: pd.Timestamp
    entry: float
    stop_loss: float
    take_profit: float
    timeframe: str = ""
    strategy_version: str = ""
    metadata: dict | None = None
    trailing_policy: dict | None = None
    fx_rate: float = 1.0

    @property
    def risk_per_unit(self):
        return abs(self.entry - self.stop_loss)

    @property
    def risk_per_unit_inr(self):
        return self.risk_per_unit * self.fx_rate

    @property
    def reward_per_unit(self):
        return abs(self.take_profit - self.entry)

    @property
    def reward_per_unit_inr(self):
        return self.reward_per_unit * self.fx_rate

@dataclass(frozen=True)
class PaperTrade:
    plan: TradePlan
    account: str = "nifty"
    quantity: float = 0.0
    status: TradeStatus = "OPEN"
    exit_price: float | None = None
    exit_timestamp: pd.Timestamp | None = None
    exit_reason: str | None = None

    @property
    def planned_risk(self):
        return self.plan.risk_per_unit_inr * self.quantity

@dataclass(frozen=True)
class AccountState:
    name: str
    starting_balance: float = ACCOUNT_SIZE_INR
    balance: float = ACCOUNT_SIZE_INR
    planned_risk_used: float = 0.0
    trades_today: int = 0

    @property
    def daily_trade_limit(self):
        try:
            return int(ACCOUNT_TRADE_LIMITS[self.name.lower()])
        except KeyError as exc:
            raise TradingRuleError(f"Unknown trading account: {self.name}") from exc

    @property
    def risk_per_trade(self):
        """Risk budget for a single trade in this account, not a global."""
        try:
            return float(ACCOUNT_RISK_PER_TRADE[self.name.lower()])
        except KeyError as exc:
            raise TradingRuleError(f"Unknown trading account: {self.name}") from exc

    @property
    def max_daily_planned_risk(self):
        return self.risk_per_trade * self.daily_trade_limit

    @property
    def remaining_trades(self):
        return max(0, self.daily_trade_limit - self.trades_today)

    @property
    def remaining_planned_risk(self):
        return max(0.0, self.max_daily_planned_risk - self.planned_risk_used)

def validate_risk_configuration():
    """Check that every account is fundable, not that it matches one number.

    Account values are operator-editable from the dashboard, so the invariant
    that matters is internal consistency: an account whose daily risk budget
    cannot fit inside its own starting balance would size positions it cannot
    pay for.
    """
    if LEVERAGE != 1.0:
        raise TradingRuleError("MULTIBOT2 uses 1x leverage")
    if set(ACCOUNT_TRADE_LIMITS) != set(account_names()):
        raise TradingRuleError("Account configuration mismatch")
    for name in account_names():
        size = ACCOUNT_SIZES[name]
        limit = ACCOUNT_TRADE_LIMITS[name]
        risk = ACCOUNT_RISK_PER_TRADE[name]
        if not ACCOUNT_MIN_SIZE_INR <= size <= ACCOUNT_MAX_SIZE_INR:
            raise TradingRuleError(f"{name}: starting balance out of range")
        if not ACCOUNT_MIN_TRADE_LIMIT <= limit <= ACCOUNT_MAX_TRADE_LIMIT:
            raise TradingRuleError(f"{name}: daily trade limit out of range")
        if not ACCOUNT_MIN_RISK_INR <= risk <= ACCOUNT_MAX_RISK_INR:
            raise TradingRuleError(f"{name}: risk per trade out of range")
        if risk > size or risk * limit > size:
            raise TradingRuleError(f"{name}: daily risk budget exceeds its starting balance")

def signal_freshness(signal_timestamp, now, *, freshness_hours=SIGNAL_FRESHNESS_HOURS):
    """Compatibility wrapper over the canonical signal_gate freshness rule."""
    if freshness_hours != SIGNAL_FRESHNESS_HOURS:
        raise TradingRuleError("Freshness is locked at one hour")
    timestamp = normalize_timestamp(signal_timestamp)
    current = normalize_timestamp(now)
    age_hours = (current - timestamp).total_seconds() / 3600
    if age_hours < 0:
        raise TradingRuleError("Signal timestamp cannot be in the future")
    return "FRESH" if is_fresh_age(age_hours) else "STALE"

def can_open_trade(account):
    validate_risk_configuration()
    return (
        account.trades_today < account.daily_trade_limit
        and account.planned_risk_used + account.risk_per_trade <= account.max_daily_planned_risk
    )

def register_trade(account, *, planned_risk=None):
    if planned_risk is None:
        planned_risk = account.risk_per_trade
    if not can_open_trade(account):
        raise TradingRuleError(f"Daily trading limit reached for {account.name}")
    if planned_risk <= 0 or planned_risk > account.risk_per_trade + 1e-9:
        raise TradingRuleError(
            f"Trade planned risk exceeds {account.name}'s ₹{account.risk_per_trade:,.0f} budget"
        )
    return AccountState(
        account.name, account.starting_balance, account.balance,
        account.planned_risk_used + planned_risk, account.trades_today + 1,
    )

def quantity_for_risk(entry, stop_loss, *, risk_inr=None, account=None, fx_rate=1.0):
    """Size a position for a risk budget.

    `risk_inr` wins when given; otherwise the budget comes from `account` so a
    smaller book does not get positions sized off the global ₹2,000 default.
    """
    if risk_inr is None:
        risk_inr = account.risk_per_trade if account is not None else RISK_PER_TRADE_INR
    ceiling = account.risk_per_trade if account is not None else float(
        max(ACCOUNT_RISK_PER_TRADE.values(), default=RISK_PER_TRADE_INR))
    e, s, risk, rate = float(entry), float(stop_loss), float(risk_inr), float(fx_rate)
    distance = abs(e - s)
    if e <= 0 or s <= 0 or distance <= 0:
        raise TradingRuleError("Entry and stop-loss must be positive and different")
    if risk <= 0 or risk > ceiling + 1e-9:
        raise TradingRuleError(f"Risk must be positive and no greater than ₹{ceiling:,.0f}")
    if rate <= 0:
        raise TradingRuleError("FX rate must be positive")
    return risk / (distance * rate)

def realized_pnl(trade, *, exit_price):
    price=float(exit_price)
    if trade.plan.side=="BUY": return (price-trade.plan.entry)*trade.quantity*trade.plan.fx_rate
    return (trade.plan.entry-price)*trade.quantity*trade.plan.fx_rate

def settle_account(account, *, trade, exit_price):
    pnl=realized_pnl(trade,exit_price=exit_price)
    return AccountState(account.name,account.starting_balance,account.balance+pnl,max(0.0,account.planned_risk_used-trade.planned_risk),account.trades_today),pnl

def close_trade(trade, *, exit_price, exit_timestamp, exit_reason):
    if trade.status == "CLOSED":
        raise TradingRuleError("Trade is already closed")
    ts = pd.Timestamp(exit_timestamp)
    if ts.tzinfo is None:
        raise TradingRuleError("Exit timestamp must be timezone-aware")
    price = float(exit_price)
    if price <= 0 or not exit_reason.strip():
        raise TradingRuleError("Invalid trade close")
    return PaperTrade(
        trade.plan, trade.account, trade.quantity, "CLOSED", price,
        ts.tz_convert("Asia/Kolkata"), exit_reason.strip(),
    )

__all__ = [
    "AccountState", "PaperTrade", "TradePlan", "TradingRuleError",
    "can_open_trade", "close_trade", "quantity_for_risk", "register_trade",
    "signal_freshness", "validate_risk_configuration", "realized_pnl", "settle_account",
]