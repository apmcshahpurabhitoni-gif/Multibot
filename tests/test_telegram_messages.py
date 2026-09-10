import pandas as pd
from strategies import Signal
from telegram import render_signal_message

def test_generic_buy_message_uses_strategy_name():
    s=Signal("Adaptive Trend Momentum","1.0.0","BTC-USD","BUY",pd.Timestamp("2026-09-01 00:00",tz="Asia/Kolkata"),"1D","TEST",100,95,110)
    m=render_signal_message(s,symbol="BTC-USD",asset="Bitcoin (BTC)",market="Crypto",timeframe="1D",entry=100,stop_loss=95,take_profit=110,quantity=1,risk=2000,account="macro",freshness="FRESH",age_str="10 min ago")
    assert "Adaptive Trend Momentum" in m.text and "1D" in m.text
