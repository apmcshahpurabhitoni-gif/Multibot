"""Optional asset-aware news gate; never pauses unrelated assets globally."""
from __future__ import annotations
import pandas as pd
class NewsGate:
    def __init__(self,news_service,enabled=False,window_minutes=30):
        self.news_service=news_service; self.enabled=enabled; self.window_minutes=window_minutes
    def check(self,asset,now):
        if not self.enabled:return None
        payload=self.news_service.get(target_date=pd.Timestamp(now).date().isoformat(),impacts={"High"})
        for event in payload.get("items",[]):
            when=pd.Timestamp(event["datetime"])
            if abs((pd.Timestamp(now)-when).total_seconds())<=self.window_minutes*60:
                return {"status":"PAUSED_BY_NEWS","event":event}
        return None
