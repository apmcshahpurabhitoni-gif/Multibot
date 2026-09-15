from config import ACCOUNT_NAMES,ACCOUNT_SIZE_INR,ACCOUNT_TRADE_LIMITS,DEFAULT_TIMEFRAME,FOREX_SYMBOLS,FOREX_SWEEP_HOURS_IST,IST_TIMEZONE,LEVERAGE,LIVE_ASSETS,LIVE_ASSET_MAP,MARKET_DATA_PROVIDER,NSE_15_SYMBOLS,RISK_PER_TRADE_INR,SIGNAL_FRESHNESS_HOURS,settings,validate_configuration

def test_nse_universe_contains_exactly_15_symbols():assert len(NSE_15_SYMBOLS)==15 and len(set(NSE_15_SYMBOLS))==15
def test_nse_universe_is_fixed_expected_list():assert NSE_15_SYMBOLS==("RELIANCE","BHARTIARTL","HDFCBANK","ICICIBANK","SBIN","TCS","BAJFINANCE","LT","LICI","SUNPHARMA","HINDUNILVR","INFY","TITAN","MARUTI","KOTAKBANK")
def test_forex_universe_uses_approved_pairs():assert FOREX_SYMBOLS==("EURUSD=X","GBPUSD=X") and all(symbol in LIVE_ASSET_MAP for symbol in FOREX_SYMBOLS)
def test_forex_assets_use_4h_and_global_schedule():assert all(LIVE_ASSET_MAP[symbol].market=="Forex" and LIVE_ASSET_MAP[symbol].asset_type=="forex" and LIVE_ASSET_MAP[symbol].sweep_timeframe=="4H" for symbol in FOREX_SYMBOLS);assert FOREX_SWEEP_HOURS_IST==(2,6,10,14,18,22)
def test_live_universe_contains_21_assets():assert len(LIVE_ASSETS)==21 and len(set(asset.symbol for asset in LIVE_ASSETS))==21
def test_account_size():assert ACCOUNT_SIZE_INR==100_000
def test_risk_per_trade():assert RISK_PER_TRADE_INR==2_000
def test_independent_account_limits():assert ACCOUNT_TRADE_LIMITS=={"macro":20,"nifty":5,"ny_session":3,"sweep_4h":3}
def test_leverage_is_one_x():assert LEVERAGE==1.0
def test_four_accounts_are_configured():assert ACCOUNT_NAMES==("macro","nifty","ny_session","sweep_4h")
def test_timezone_is_ist():assert IST_TIMEZONE=="Asia/Kolkata"
def test_primary_timeframe_is_one_hour():assert DEFAULT_TIMEFRAME=="1h"
def test_signal_freshness_is_one_hour():assert SIGNAL_FRESHNESS_HOURS==1
def test_market_data_provider_is_yahoo():assert MARKET_DATA_PROVIDER=="yahoo" and settings.market_data_provider=="yahoo"
def test_complete_configuration_is_valid():validate_configuration()
