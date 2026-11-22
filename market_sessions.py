"""Central market-session gate for live strategy scans.
Exchange sessions use their own IANA timezone so DST changes are handled.
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
NEW_YORK = ZoneInfo("America/New_York")

@dataclass(frozen=True)
class MarketSession:
    is_open: bool
    market: str
    reason: str

def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Market-session timestamp must be timezone-aware")
    return value

def _nse_holidays() -> set[date]:
    """Operator-maintained NSE holiday overrides: YYYY-MM-DD, comma-separated.
    Set NSE_MARKET_HOLIDAYS in AIC from the annual exchange holiday circular.
    Weekends and regular session hours are always enforced.
    """
    holidays: set[date] = set()
    for item in os.getenv("NSE_MARKET_HOLIDAYS", "").split(","):
        item = item.strip()
        if item:
            try:
                holidays.add(date.fromisoformat(item))
            except ValueError as exc:
                raise ValueError(f"Invalid NSE_MARKET_HOLIDAYS entry {item!r}; expected YYYY-MM-DD") from exc
    return holidays

def market_session_status(asset, now: datetime) -> MarketSession:
    """NSE weekdays 09:15-15:30 IST; COMEX Gold Sun 18:00-Fri 17:00 NY
    with daily 17:00-18:00 break; spot FX Sun 17:00-Fri 17:00 NY; crypto 24/7.
    Unknown markets fail closed.
    """
    current = _aware(now)
    if asset.market == "Crypto" or asset.asset_type == "crypto":
        return MarketSession(True, asset.market, "24/7 market")
    if asset.market == "NSE":
        local = current.astimezone(IST)
        if local.date() in _nse_holidays():
            return MarketSession(False, "NSE", "NSE exchange holiday")
        if local.weekday() >= 5:
            return MarketSession(False, "NSE", "NSE weekend")
        clock = local.timetz().replace(tzinfo=None)
        if clock < time(9, 15):
            return MarketSession(False, "NSE", "Before NSE session (09:15 IST)")
        if clock >= time(15, 30):
            return MarketSession(False, "NSE", "After NSE session (15:30 IST)")
        return MarketSession(True, "NSE", "NSE regular session")
    if asset.market in {"Gold", "Forex"}:
        local = current.astimezone(NEW_YORK)
        weekday = local.weekday()
        clock = local.timetz().replace(tzinfo=None)
        if asset.market == "Gold":
            if weekday == 5 or (weekday == 6 and clock < time(18, 0)):
                return MarketSession(False, "Gold", "COMEX weekend closure")
            if weekday == 4 and clock >= time(17, 0):
                return MarketSession(False, "Gold", "COMEX weekend closure")
            if time(17, 0) <= clock < time(18, 0):
                return MarketSession(False, "Gold", "COMEX daily maintenance break")
            return MarketSession(True, "Gold", "COMEX trading session")
        if weekday == 5 or (weekday == 6 and clock < time(17, 0)):
            return MarketSession(False, "Forex", "Forex weekend closure")
        if weekday == 4 and clock >= time(17, 0):
            return MarketSession(False, "Forex", "Forex weekend closure")
        return MarketSession(True, "Forex", "Forex trading week")
    return MarketSession(False, str(asset.market), "Unknown market schedule; scan blocked")
