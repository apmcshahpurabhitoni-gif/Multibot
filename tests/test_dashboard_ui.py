from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "dashboard.html").read_text(encoding="utf-8")
CSS = (ROOT / "styles.css").read_text(encoding="utf-8")
APP = (ROOT / "app.js").read_text(encoding="utf-8")


def test_dashboard_keeps_approved_theme_and_mobile_contract():
    assert 'data-theme="light"' in HTML
    assert 'data-style="modern"' in HTML
    assert 'html[data-theme="dark"]' in CSS
    assert 'html[data-style="neo"]' in CSS
    assert 'prefers-reduced-motion: reduce' in CSS
    assert 'position: fixed' in CSS or 'position:fixed' in CSS
    assert 'bottom: 7px' in CSS or 'bottom:7px' in CSS


def test_dashboard_keeps_trading_presentation_layers_separate():
    assert '/api/dashboard' in HTML or '/api/dashboard' in APP
    assert 'signal-card' in CSS
    assert 'trade-card' in CSS
    assert 'news-item' in CSS
    assert 'backtest-chart' in CSS
    assert 'No FVG' not in HTML


def test_dashboard_has_clear_visual_hierarchy_tokens():
    for token in (
        '--surface',
        '--surface-2',
        '--accent',
        '--positive',
        '--negative',
        '--warning',
        '--shadow',
        '--radius',
    ):
        assert token in CSS

    for selector in (
        '.topbar',
        '.desktop-nav',
        '.page-heading',
        '.hero',
        '.box',
        '.signal-card',
        '.trade-card',
        '.news-item',
    ):
        assert selector in CSS


def test_dashboard_does_not_recalculate_execution_risk_or_freshness():
    assert 'Math.abs(Number(plan.entry)' not in APP
    assert 'riskPerUnit*qty' not in APP
    assert 'Date.now()-new Date(value)' not in APP
    assert 'freshnessMs' not in APP
    assert 'function ageLabel' not in APP


def test_dashboard_uses_canonical_calendar_and_history_placement():
    assert 'data-page="calendar"' in HTML
    assert 'page-calendar' in HTML
    assert 'page-news' not in HTML
    assert 'calendarRefreshButton' in HTML
    assert 'newsRefreshButton' not in HTML
    assert 'SCAN ACTIVITY' not in HTML
    assert 'data-page="trades"' not in HTML
    assert 'page-trades' not in HTML
    assert 'state.activePage==="calendar"' in APP

def test_dashboard_resolves_friendly_names_and_canonical_signal_presentation():
    assert 'function assetLabel' in APP
    assert 'function strategyLabel' in APP
    assert 'function canonicalSignals' in APP
    assert 'supportedBacktestAssets' in APP
    assert 'signal.timeframe||strategyInfo(signal.strategy)?.timeframes?.[0]' in APP


def test_dashboard_does_not_show_global_scan_panel():
    assert '<section class="panel"><div class="section-head"><div><h2>Scan History</h2>' not in HTML


def test_dashboard_contract_uses_date_grouped_signals_without_filters():
    assert 'data-signal-filter=' not in HTML
    assert 'data-signal-direction=' not in HTML
    assert 'renderSignalDateGroups' in APP
    assert 'canonicalSignals' in APP

def test_dashboard_contract_exposes_directional_signal_summary():
    source=(ROOT / "dashboard.py").read_text(encoding="utf-8")
    assert 'signal_summary' in source
    assert 'stale_directional' in source
    assert 'fresh_directional' in source


def test_dashboard_runtime_keeps_core_functions_after_ui_cleanup():
    required = ["function loadDashboard", "function bindEvents", "function bindEvent", "function renderHistory", "function renderCalendar", "function renderTools", "function applyAppearanceControls", "$$(\'[data-page]\')"]
    for token in required:
        assert token in APP
    assert APP.index("function bindEvents") < APP.index("loadDashboard();")



def test_dashboard_selector_helpers_and_bootstrap_cannot_block_runtime():
    assert "function bootstrapDashboard()" in APP
    assert "initAppearance();bindEvents();" in APP
    assert "loadDashboard();" in APP
    assert "$$('[data-page]')" in APP
    assert "$$('[data-theme-choice]')" in APP
    assert "$$('[data-style-choice]')" in APP
    assert "const $=id=>document.getElementById(id)" in APP
    assert "$('[data-page]')" in APP
    assert "$('[data-theme-choice]')" in APP


def test_dashboard_has_exactly_five_navigation_slots():
    for page in ('overview','signals','history','calendar','tools'):
        assert f'data-page="{page}"' in HTML
    assert 'grid-template-columns:repeat(5,1fr)' in CSS or 'grid-template-columns:repeat(5,minmax(0,1fr))' in CSS


def test_tools_workspace_uses_rebuilt_sections_and_simple_backtest_asset_names():
    for token in ('tools-layout', 'tool-backtest', 'tool-universe', 'tool-accounts', 'tool-rules', 'tool-runtime'):
        assert token in HTML
    assert '${escapeHtml(asset.label)} · ${escapeHtml(asset.ticker)}' not in APP
    assert '<option value="${escapeHtml(asset.key||asset.ticker)}">${escapeHtml(asset.label)}</option>' in APP


def test_dashboard_uses_equity_curves_for_primary_performance():
    assert 'id="equityCurveChart"' in HTML
    assert 'Equity curve' in HTML
    assert 'function renderEquityLine' in APP
    assert 'id="styleToggle"' not in HTML
    assert 'id="themeToggle"' in HTML
    assert 'equity_curve' in (ROOT / "main.py").read_text(encoding="utf-8")


def test_dashboard_keeps_backtest_primary_chart_as_equity_curve():
    assert 'Backtest equity curve' in APP
    assert 'Paper account value after each completed backtest trade' in APP
    assert 'Signals by day' not in APP[APP.index('function renderBacktest'):APP.index('async function runBacktest')]


def test_dashboard_mobile_navigation_is_compact():
    assert 'min-height:48px' in CSS
    assert 'grid-template-columns:repeat(5' in CSS


def test_dashboard_backtest_metrics_and_trades_are_bounded_and_separated():
    source=(ROOT / "app.js").read_text(encoding="utf-8")
    assert "formatBacktestMetric" in source
    assert "Completed trades" in source
    assert "backtest-trade-row" in source
    assert "Number.isFinite(n)" in source


def test_backtest_ratio_metrics_are_bounded():
    source=(ROOT / "backtest.py").read_text(encoding="utf-8")
    assert "def _bounded_ratio" in source
    assert "return 10.0 if mean>0 else 0.0" in source
    assert "risk_adjusted_performance" in source\n

def test_dashboard_consistency_pass_keeps_sections_contained_and_trade_lists_scrollable():
    for token in (
        '--section-gap',
        '--card-pad',
        '.signals-workspace',
        '.history-workspace',
        '.calendar-workspace',
        '.tool-card',
        '.backtest-section',
        '.backtest-trades',
        '.backtest-signal-list',
        'max-height:560px',
        'overflow-y:auto',
        'min-width:0',
        'overflow-wrap:anywhere',
    ):
        assert token in CSS
