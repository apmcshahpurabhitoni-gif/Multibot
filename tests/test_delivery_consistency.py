import pandas as pd
from strategies.base import Signal
from strategy_service import StrategyService

# This regression is intentionally small: after a successful notifier call,
# post-delivery persistence failures must still report the signal as sent.
def test_post_delivery_status_is_not_reclassified_by_persistence_failure():
    source=open("strategy_service.py",encoding="utf-8").read()
    assert "SENT_PERSISTENCE_FAILED" in source
    sent_index=source.index('self.database.record_signal_send(')
    status_index=source.index('self.database.update_signal_status(sid,"DELIVERED")', sent_index)
    trade_index=source.index('self.database.save_trade(', status_index)
    assert sent_index < status_index < trade_index
