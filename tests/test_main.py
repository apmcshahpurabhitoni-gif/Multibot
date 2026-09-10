import main

def test_registry_is_strategy_driven():
    main.ensure_runtime(); assert set(main.REGISTRY.ids())=={"adaptive_trend","sweep_v2"}

def test_ping_contract_exists():
    assert callable(main.web_server) and callable(main.run_strategy_cycle)
