from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "dashboard.html").read_text(encoding="utf-8")
CSS = (ROOT / "appearance-overrides.css").read_text(encoding="utf-8")
APP = (ROOT / "app.js").read_text(encoding="utf-8")
APPEARANCE = (ROOT / "appearance.js").read_text(encoding="utf-8")


def test_appearance_has_theme_and_interface_style_controls():
    assert 'id="themeToggle"' in HTML
    assert 'data-style-choice="modern"' in HTML
    assert 'data-style-choice="neo"' in HTML
    assert 'data-theme="light"' in HTML
    assert 'data-style="modern"' in HTML
    assert 'html[data-style="neo"]' in CSS
    assert 'setStyle' in APPEARANCE
    assert 'setTheme' in APPEARANCE


def test_appearance_bridge_is_loaded_after_app():
    assert '<script src="app.js" defer></script>' in HTML
    assert '<script src="appearance.js" defer></script>' in HTML
    assert HTML.index('app.js') < HTML.index('appearance.js')
    assert 'applyStyle' in APPEARANCE


def test_appearance_controls_are_compact_without_redesigning_shell():
    assert '.topbar .icon-button{width:34px;height:34px;min-width:34px' in CSS
    assert '.topbar .header-meta{display:flex;align-items:center;flex-wrap:nowrap' in CSS
    assert '@media(max-width:560px)' in CSS
    assert '.appearance-style-grid{display:grid' in CSS


def test_neo_brutalism_covers_primary_interactive_controls():
    assert 'html[data-style="neo"] .primary-button' in CSS
    assert 'html[data-style="neo"] .secondary-button' in CSS
    assert 'html[data-style="neo"] .icon-button' in CSS
    assert 'html[data-style="neo"] .nav-button' in CSS
    assert 'html[data-style="neo"] .settings-toggle' in CSS
    assert ':active' in CSS
