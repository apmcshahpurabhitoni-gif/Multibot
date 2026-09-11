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
    assert 'SCAN ACTIVITY' in HTML
    assert 'id="scanHistory"' in HTML
    assert 'state.activePage==="calendar"' in APP


def test_dashboard_resolves_friendly_names_and_canonical_signal_presentation():
    assert 'function assetLabel' in APP
    assert 'function strategyLabel' in APP
    assert 'function canonicalSignals' in APP
    assert 'supportedBacktestAssets' in APP
    assert 'signal.timeframe||strategyInfo(signal.strategy)?.timeframes?.[0]' in APP


def test_dashboard_does_not_show_global_scan_panel():
    assert '<section class="panel"><div class="section-head"><div><h2>Scan History</h2>' not in HTML
