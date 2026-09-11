"""Manifest-aware due checks; strategies stay plug-and-play."""
from __future__ import annotations
import pandas as pd
class StrategyScheduler:
    def __init__(self): self._last={}
    def is_due(self,strategy,now):
        key=strategy.manifest.id; current=pd.Timestamp(now)
        last=self._last.get(key)
        schedule=str(strategy.manifest.schedule or "")
        if last is None: self._last[key]=current; return True
        interval=300
        if "sweep" in schedule.lower(): interval=60
        if "daily" in schedule.lower(): interval=86400
        if (current-last).total_seconds()>=interval:
            self._last[key]=current; return True
        return False
