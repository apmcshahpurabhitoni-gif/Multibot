"""Universal paper-trade monitor for every strategy."""
from __future__ import annotations
import logging
import pandas as pd
from config import ACCOUNT_NAMES,ACCOUNT_SIZE_INR,LIVE_ASSET_MAP
from db import DatabaseManager
from trading import AccountState,PaperTrade,TradePlan,close_trade,settle_account
from notification_service import NotificationService
from telegram import trade_closed_message

logger=logging.getLogger("multibot2.trade_monitor")

class TradeMonitor:
    def __init__(self,*,database:DatabaseManager,price_lookup,accounts:dict,notifier=None):
        self.database=database; self.price_lookup=price_lookup; self.accounts=accounts; self.notifier=notifier or NotificationService(database)

    def _hit(self,row,price):
        side=row.get("type","BUY")
        if side=="BUY":
            if price<=float(row["sl"]): return "STOP_LOSS"
            if price>=float(row["tp"]): return "TAKE_PROFIT"
        else:
            if price>=float(row["sl"]): return "STOP_LOSS"
            if price<=float(row["tp"]): return "TAKE_PROFIT"
        return None

    def _trade(self,row):
        ts=pd.Timestamp(row["signal_ts"])
        plan=TradePlan(row.get("strategy",""),row["type"],ts,float(row["entry"]),float(row["sl"]),float(row["tp"]),timeframe=row.get("timeframe",""),strategy_version=row.get("strategy_version",""),metadata=row.get("metadata"),trailing_policy=row.get("trailing_policy"),fx_rate=float(row.get("fx_rate",1.0)))
        return PaperTrade(plan=plan,account=row["account"],quantity=float(row["qty"]))

    def monitor_once(self,*,now=None):
        current=pd.Timestamp.now(tz="Asia/Kolkata") if now is None else pd.Timestamp(now)
        if current.tzinfo is None: raise ValueError("now must be timezone-aware")
        closed=[]; errors=[]
        for row in self.database.load_trades("OPEN"):
            symbol=row.get("symbol")
            try:
                price=self.price_lookup(symbol)
                if price is None: errors.append({"id":row.get("id"),"symbol":symbol,"reason":"PRICE_UNAVAILABLE"}); continue
                reason=self._hit(row,float(price))
                if not reason: continue
                trade=self._trade(row)
                closed_trade=close_trade(trade,exit_price=float(price),exit_timestamp=current,exit_reason=reason)
                account=self.accounts.get(row["account"])
                if account is None:
                    today=current.tz_convert("Asia/Kolkata").date().isoformat()
                    rows=self.database.load_accounts(ACCOUNT_NAMES,ACCOUNT_SIZE_INR,today)
                    account=AccountState(row["account"],float(rows[row["account"]]["starting_balance"]),float(rows[row["account"]]["balance"]),float(rows[row["account"]]["planned_risk_used"]),int(rows[row["account"]]["trades_today"]))
                updated,pnl=settle_account(account,trade=trade,exit_price=float(price)); self.accounts[row["account"]]=updated
                payload=dict(row); payload.update({"status":"CLOSED","exit_price":float(price),"exit_reason":reason,"closed_at":current.isoformat(),"pnl":pnl,"result":"WIN" if pnl>=0 else "LOSS"})
                self.database.save_trade(row["id"],"CLOSED",payload,current.isoformat())
                self.database.save_account(updated.name,balance=updated.balance,trades_today=updated.trades_today,planned_risk_used=updated.planned_risk_used,reset_date=current.tz_convert("Asia/Kolkata").date().isoformat())
                signal_id=str(row.get("signal_id") or row["id"])
                message=trade_closed_message(closed_trade,float(price),pnl,updated.balance,trade.plan.side=="BUY",reason=="TAKE_PROFIT")
                self.notifier.deliver(signal_id=signal_id,message=message,kind="TRADE_CLOSED",metadata={"trade_id":row["id"],"reason":reason,"pnl":pnl})
                closed.append(payload)
            except Exception as exc:
                logger.exception("Trade monitor failed for %s",row.get("id")); errors.append({"id":row.get("id"),"symbol":symbol,"reason":str(exc)})
        return {"status":"OK" if not errors else "PARTIAL","closed":closed,"errors":errors,"active_trades":len(self.database.load_trades("OPEN")),"timestamp":current.isoformat()}
