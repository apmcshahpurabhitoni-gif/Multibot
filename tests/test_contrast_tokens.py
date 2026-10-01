"""WCAG AA contrast guard for the dashboard appearance tokens.

Browserless on purpose: it reads the real stylesheet, replays the token
cascade for every style x accent x theme combination and checks the
foreground/background pairs the UI actually renders. A headless browser
check caught 142 failures that the string-matching tests could not see;
this keeps CI able to see the same class of bug.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "styles.css").read_text(encoding="utf-8")

STYLES = ("modern", "material3", "neo")
ACCENTS = ("emerald", "indigo", "amber", "rose", "cyan")
THEMES = ("light", "dark")

# WCAG 2.1 AA. Large text is >=24px, or >=18.66px when bold.
AA_TEXT = 4.5
AA_LARGE = 3.0

# Every pair the UI paints: (foreground token, background token, min ratio).
# The background is composited over the surface first, because every wash
# token in the file is semi-transparent.
CONTRACTS = (
    ("--positive", "--positive-soft", "--surface", AA_TEXT),   # .fresh, .status-badge
    ("--warning", "--warning-soft", "--surface", AA_TEXT),    # .stale, .impact-pill.medium
    ("--negative", "--negative-soft", "--surface", AA_TEXT),   # .negative
    ("--text", None, "--surface", AA_TEXT),                    # body copy
    ("--muted", None, "--surface", AA_TEXT),                   # secondary copy
    ("--accent-strong", None, "--bg", AA_TEXT),                # .eyebrow
    ("--accent-strong", None, "--surface", AA_TEXT),           # .text-button
    ("--on-accent", "--accent-fill", None, AA_TEXT),           # .primary-button, .chip-option.active
)

RULE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.S)
CUSTOM_PROP = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+);")
ATTR = re.compile(r'\[data-([a-z-]+)="([a-z0-9]+)"\]')


def _parse_colour(value: str):
    value = value.strip()
    if value.startswith("#"):
        h = value[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) != 6:
            return None
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 1.0
    m = re.match(r"rgba?\(([^)]+)\)", value)
    if not m:
        return None
    parts = [p.strip() for p in m.group(1).split(",")]
    if len(parts) < 3:
        return None
    rgb = tuple(float(parts[i]) for i in range(3))
    alpha = float(parts[3]) if len(parts) > 3 else 1.0
    return rgb[0], rgb[1], rgb[2], alpha


def _over(fg, bg):
    a = fg[3]
    return (fg[0] * a + bg[0] * (1 - a), fg[1] * a + bg[1] * (1 - a), fg[2] * a + bg[2] * (1 - a), 1.0)


def _luminance(c):
    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = c[:3]
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _ratio(a, b):
    l1, l2 = _luminance(a), _luminance(b)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def _blocks():
    """Yield (conditions, props) for every rule that declares custom properties."""
    for selector, body in RULE.findall(CSS):
        if "--" not in body:
            continue
        props = {k: v.strip() for k, v in CUSTOM_PROP.findall(body + ";")}
        if not props:
            continue
        yield dict(ATTR.findall(selector)), props


BLOCKS = list(_blocks())

VAR = re.compile(r"^var\(\s*(--[a-z0-9-]+)\s*\)$")


def _expand(value: str, resolved: dict, depth: int = 5) -> str:
    """Follow var() indirection so material3's aliases resolve to real colours."""
    match = VAR.match(value.strip())
    if not match or depth <= 0:
        return value.strip()
    target = match.group(1)
    if target not in resolved:
        return value.strip()
    return _expand(resolved[target], resolved, depth - 1)


def tokens(style: str, accent: str, theme: str) -> dict:
    """Replay the cascade: a block applies when every attribute it gates on matches."""
    # ATTR strips the "data-" prefix, so the active map must use short keys too.
    active = {"style": style, "accent": accent, "theme": theme}
    resolved: dict = {}
    for conditions, props in BLOCKS:
        if all(active.get(key) == value for key, value in conditions.items()):
            resolved.update(props)
    return {name: _expand(value, resolved) for name, value in resolved.items()}


def test_stylesheet_declares_tokens_for_every_combination():
    for style in STYLES:
        for accent in ACCENTS:
            for theme in THEMES:
                found = tokens(style, accent, theme)
                missing = [
                    name
                    for pair in CONTRACTS
                    for name in pair[:2]
                    if name and name not in found
                ]
                assert not missing, f"{style}/{accent}/{theme} missing {sorted(set(missing))}"


def test_every_appearance_combination_meets_wcag_aa():
    failures = []
    for style in STYLES:
        for accent in ACCENTS:
            for theme in THEMES:
                combo = f"{style}/{accent}/{theme}"
                t = tokens(style, accent, theme)
                for fg_name, wash_name, base_name, minimum in CONTRACTS:
                    fg_raw = t.get(fg_name)
                    if not fg_raw:
                        continue
                    fg = _parse_colour(fg_raw)
                    base_raw = t.get(base_name) if base_name else t.get("--accent-fill")
                    if not fg or not base_raw:
                        continue
                    base = _parse_colour(base_raw)
                    if wash_name:
                        wash = _parse_colour(t[wash_name])
                        if wash is None:
                            continue
                        background = _over(wash, base)
                    else:
                        background = base
                    if fg[3] < 1:
                        fg = _over(fg, background)
                    measured = _ratio(fg, background)
                    if measured < minimum:
                        failures.append(
                            f"{combo}: {fg_name}={fg_raw} on "
                            f"{wash_name or base_name}={base_raw} -> {measured:.2f} (needs {minimum})"
                        )
    assert not failures, "WCAG AA failures:\n" + "\n".join(failures)
