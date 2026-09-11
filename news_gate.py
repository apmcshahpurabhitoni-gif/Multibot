"""Asset-aware optional economic-news gate."""
from __future__ import annotations
import pandas as pd

ASSET_CURRENCIES = {
    "BTC-USD": {"USD"},
    "ETH-USD": {"USD"},
    "GOLD": {"USD"},
}
DEFAULT_MARKET_CURRENCIES = {
    "NSE": {"INR"},
    "CRYPTO": {"USD"},
    "COMMODITY": {"USD"},
}

class NewsGate:
    def __init__(self, news_service, enabled=False, window_minutes=30):
        self.news_service = news_service
        self.enabled = enabled
        self.window_minutes = int(window_minutes)

    def currencies_for(self, asset):
        return ASSET_CURRENCIES.get(
            asset.symbol,
            DEFAULT_MARKET_CURRENCIES.get(getattr(asset, "market", ""), set()),
        )

    def check(self, asset, now):
        if not self.enabled:
            return None
        current = pd.Timestamp(now)
        payload = self.news_service.get(
            target_date=current.date().isoformat(), impacts={"High"}
        )
        currencies = self.currencies_for(asset)
        for event in payload.get("items", []):
            if currencies and str(event.get("currency", "")).upper() not in currencies:
                continue
            when = pd.Timestamp(event["datetime"])
            if when.tzinfo is None:
                when = when.tz_localize(current.tz)
            if abs((current - when.tz_convert(current.tz)).total_seconds()) <= self.window_minutes * 60:
                return {"status": "PAUSED_BY_NEWS", "event": event}
        return None
