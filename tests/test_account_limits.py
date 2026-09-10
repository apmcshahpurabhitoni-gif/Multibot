import pytest

from config import ACCOUNT_TRADE_LIMITS
from trading import AccountState, TradingRuleError, can_open_trade, register_trade


def test_original_account_limits_are_restored():
    assert ACCOUNT_TRADE_LIMITS == {
        "macro": 20,
        "nifty": 5,
        "ny_session": 3,
        "sweep_4h": 3,
    }


@pytest.mark.parametrize(
    ("account", "limit"),
    [
        ("macro", 20),
        ("nifty", 5),
        ("ny_session", 3),
        ("sweep_4h", 3),
    ],
)
def test_each_account_enforces_its_own_limit(account, limit):
    state = AccountState(name=account)

    for _ in range(limit):
        assert can_open_trade(state)
        state = register_trade(state)

    assert state.trades_today == limit
    assert not can_open_trade(state)

    with pytest.raises(TradingRuleError, match="Daily trading limit reached"):
        register_trade(state)


def test_account_limits_are_independent():
    nifty = AccountState(name="nifty", trades_today=5, planned_risk_used=10_000)
    macro = AccountState(name="macro", trades_today=0, planned_risk_used=0)

    assert not can_open_trade(nifty)
    assert can_open_trade(macro)


def test_unknown_account_is_rejected():
    with pytest.raises(TradingRuleError, match="Unknown trading account"):
        can_open_trade(AccountState(name="unknown"))
