"""Canonical paper-trading, sizing, and account-risk rules."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
import pandas as pd
from config import ACCOUNT_SIZE_INR,ACCOUNT_TRADE_LIMITS,LEVERAGE,RISK_PER_TRADE_INR
TradeSide=Literal["BUY","SELL"];TradeStatus=Literal["OPEN","CLOSED"]
class TradingRuleError(ValueError):pass
@dataclass(frozen=True)
class TradePlan:
 strategy:str;side:TradeSide;signal_timestamp:pd.Timestamp;entry:float;stop_loss:float;take_profit:float;timeframe:str="";strategy_version:str="";metadata:dict|None=None;trailing_policy:dict|None=None;fx_rate:float=1.0
 @property
 def risk_per_unit(self):return abs(self.entry-self.stop_loss)
 @property
 def risk_per_unit_inr(self):return self.risk_per_unit*self.fx_rate
 @property
 def reward_per_unit(self):return abs(self.take_profit-self.entry)
 @property
 def reward_per_unit_inr(self):return self.reward_per_unit*self.fx_rate
@dataclass(frozen=True)
class PaperTrade:
 plan:TradePlan;account:str="nifty";quantity:float=0.0;status:TradeStatus="OPEN";exit_price:float|None=None;exit_timestamp:pd.Timestamp|None=None;exit_reason:str|None=None
 @property
 def planned_risk(self):return self.plan.risk_per_unit_inr*self.quantity
@dataclass(frozen=True)
class AccountState:
 name:str;starting_balance:float=ACCOUNT_SIZE_INR;balance:float=ACCOUNT_SIZE_INR;planned_risk_used:float=0.0;trades_today:int=0
 @property
 def daily_trade_limit(self):
  try:return int(ACCOUNT_TRADE_LIMITS[self.name.lower()])
  except KeyError as exc:raise TradingRuleError(f"Unknown trading account: {self.name}") from exc
 @property
 def max_daily_planned_risk(self):return RISK_PER_TRADE_INR*self.daily_trade_limit
 @property
 def remaining_trades(self):return max(0,self.daily_trade_limit-self.trades_today)
 @property
 def remaining_planned_risk(self):return max(0.0,self.max_daily_planned_risk-self.planned_risk_used)
def validate_risk_configuration():
 if ACCOUNT_SIZE_INR!=100_000 or RISK_PER_TRADE_INR!=2_000 or ACCOUNT_TRADE_LIMITS!={"macro":20,"nifty":5,"ny_session":3,"sweep_4h":3} or LEVERAGE!=1.0:raise TradingRuleError("Locked risk configuration is invalid")
def can_open_trade(account):
 validate_risk_configuration();return account.trades_today<account.daily_trade_limit and account.planned_risk_used+RISK_PER_TRADE_INR<=account.max_daily_planned_risk
def register_trade(account,*,planned_risk=RISK_PER_TRADE_INR):
 if not can_open_trade(account):raise TradingRuleError(f"Daily trading limit reached for {account.name}")
 if not 0<planned_risk<=RISK_PER_TRADE_INR+1e-9:raise TradingRuleError("Trade planned risk exceeds ₹2,000")
 return AccountState(account.name,account.starting_balance,account.balance,account.planned_risk_used+planned_risk,account.trades_today+1)
def quantity_for_risk(entry,stop_loss,*,risk_inr=RISK_PER_TRADE_INR,fx_rate=1.0):
 e,s,risk,rate=map(float,(entry,stop_loss,risk_inr,fx_rate));distance=abs(e-s)
 if e<=0 or s<=0 or distance<=0:raise TradingRuleError("Entry and stop-loss must be positive and different")
 if not 0<risk<=RISK_PER_TRADE_INR or rate<=0:raise TradingRuleError("Invalid risk or FX rate")
 return risk/(distance*rate)
def close_trade(trade,*,exit_price,exit_timestamp,exit_reason):
 if trade.status=="CLOSED":raise TradingRuleError("Trade is already closed")
 ts=pd.Timestamp(exit_timestamp);price=float(exit_price)
 if ts.tzinfo is None or price<=0 or not exit_reason.strip():raise TradingRuleError("Invalid trade close")
 return PaperTrade(trade.plan,trade.account,trade.quantity,"CLOSED",price,ts.tz_convert("Asia/Kolkata"),exit_reason.strip())
