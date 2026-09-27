from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "dashboard.html").read_text(encoding="utf-8")
CSS = (ROOT / "appearance-overrides.css").read_text(encoding="utf-8")
APP = (ROOT / "app.js").read_text(encoding="utf-8")
APPEARANCE = (ROOT / "appearance.js").read_text(encoding="utf-8")
STYLES = (ROOT / "styles.css").read_text(encoding="utf-8")


def test_appearance_has_separate_theme_and_interface_style_controls():
    assert 'id="themeToggle"' in HTML
    assert 'data-style-choice="modern"' in HTML
    assert 'data-style-choice="neo"' in HTML
    assert 'data-theme="light"' in HTML
    assert 'data-style="modern"' in HTML
    assert 'html[data-style="neo"]' in STYLES
    assert 'mavis-theme' in APPEARANCE
    assert 'mavis-style' in APPEARANCE


def test_appearance_bridge_is_loaded_after_app():
    assert '<script src="app.js" defer></script>' in HTML
    assert '<script src="appearance.js" defer></script>' in HTML
    assert HTML.index('app.js') < HTML.index('appearance.js')
    assert 'applyStyle' in APPEARANCE


def test_appearance_controls_are_compact_without_redesigning_shell():
    foundation = (ROOT / "foundation.css").read_text(encoding="utf-8")
    # The topbar utility buttons are ExpandableControl siblings: one size and one
    # radius from the foundation contract, and no per-viewport geometry override.
    assert '--ui-collapse-size:40px' in foundation
    assert '--ui-collapse-radius:10px' in foundation
    assert '--ui-control-h:var(--ui-collapse-size)' in CSS
    assert '--ui-control-r:var(--ui-collapse-radius)' in CSS
    assert '.topbar .icon-button{padding:0!important;border:2px solid var(--line)!important' in CSS
    assert '.topbar .icon-button{width' not in CSS
    # Neo supplies the flat ink treatment only; it must not resize the control.
    assert 'html.neo-mode .topbar .icon-button{\n  padding:0!important;' in CSS
    assert '.topbar .header-meta{display:flex;align-items:center;flex-wrap:nowrap' in CSS
    assert '@media(max-width:560px)' in CSS
    assert '.appearance-style-grid{display:grid' in CSS


def test_neo_brutalism_covers_interactive_surface():
    for selector in (
        'html[data-style="neo"] .primary-button',
        'html[data-style="neo"] .secondary-button',
        'html[data-style="neo"] .icon-button',
        'html[data-style="neo"] .text-button',
        'html[data-style="neo"] .nav-button',
        'html[data-style="neo"] .filter-button',
        'html[data-style="neo"] .settings-toggle',
        'html[data-style="neo"] input',
        'html[data-style="neo"] select',
    ):
        assert selector in CSS
    assert ':hover' in CSS
    assert ':active' in CSS
