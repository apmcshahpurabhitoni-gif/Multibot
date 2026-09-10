from config import ACCOUNT_NAMES,ACCOUNT_SIZE_INR,ACCOUNT_TRADE_LIMITS,DEFAULT_TIMEFRAME,IST_TIMEZONE,LEVERAGE,MARKET_DATA_PROVIDER,NSE_15_SYMBOLS,RISK_PER_TRADE_INR,SIGNAL_FRESHNESS_HOURS,settings,validate_configuration

def test_nse_universe_contains_exactly_15_symbols():assert len(NSE_15_SYMBOLS)==15 and len(set(NSE_15_SYMBOLS))==15
def test_nse_universe_is_fixed_expected_list():assert NSE_15_SYMBOLS==("RELIANCE","BHARTIARTL","HDFCBANK","ICICIBANK","SBIN","TCS","BAJFINANCE","LT","LICI","SUNPHARMA","HINDUNILVR","INFY","TITAN","MARUTI","KOTAKBANK")
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
