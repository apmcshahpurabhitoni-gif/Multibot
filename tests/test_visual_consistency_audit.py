"""Guards for the visual-consistency re-audit (2026-10-03).

Every defect here was visible on screen, and every fix removed a *superseded*
rule rather than adding a new one. The tests therefore assert both halves: the
replacement is present **and** the rule that used to win by accident is gone.

A bare substring check would be useless for most of these. Asserting that
``#page-tools .tool-settings .chip-option`` appears somewhere is satisfied by
the very selector whose absence caused the bug, so the chip test below compares
the *set of properties* each card's selector declares and requires them to
match. Asserting ``padding:8px 10px`` is present would pin the defect, so the
compact test pins the absence of the old value alongside the new one.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "dashboard.html").read_text(encoding="utf-8")
APP = (ROOT / "app.js").read_text(encoding="utf-8")
SHEETS = {
    "foundation.css": (ROOT / "foundation.css").read_text(encoding="utf-8"),
    "styles.css": (ROOT / "styles.css").read_text(encoding="utf-8"),
    "appearance-overrides.css": (ROOT / "appearance-overrides.css").read_text(encoding="utf-8"),
}
ALL_CSS = "\n".join(SHEETS.values())

# Properties that make up the chip box: size, spacing, type and colour. These
# are what made the two Tools cards render the same control two different ways.
CHIP_BOX_PROPERTIES = frozenset(
    {
        "min-height", "height", "padding", "padding-inline", "border-radius",
        "font-size", "line-height", "font-weight", "box-sizing",
        "color", "background", "border-color", "-webkit-text-fill-color",
    }
)


def _iter_rules(css, media="none"):
    """Yield ``(prelude, body, media)`` for every rule, with at-rule context.

    Without the context a responsive override looks like a duplicate of the
    base rule it legitimately replaces, which is the mistake these guards are
    meant to catch in the other direction.
    """
    prelude = ""
    index, length = 0, len(css)
    while index < length:
        char = css[index]
        if char == "{":
            depth, cursor = 1, index + 1
            while cursor < length and depth:
                if css[cursor] == "{":
                    depth += 1
                elif css[cursor] == "}":
                    depth -= 1
                cursor += 1
            body = css[index + 1 : cursor - 1]
            head = " ".join(prelude.split())
            if head.startswith("@"):
                match = re.match(r"@media\(([^)]*)\)", head)
                yield from _iter_rules(body, match.group(1) if match else head)
            else:
                yield head, body, media
            prelude = ""
            index = cursor
            continue
        if char != "}":
            prelude += char
        else:
            prelude = ""
        index += 1


def _declarations(body):
    """Map property -> value for one rule body, ignoring nested at-rules."""
    out = {}
    depth, current = 0, ""
    chunks = []
    for char in body:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        if char == ";" and depth == 0:
            chunks.append(current)
            current = ""
        else:
            current += char
    chunks.append(current)
    for chunk in chunks:
        if ":" not in chunk:
            continue
        prop, value = chunk.split(":", 1)
        prop = prop.strip().lower()
        if prop and not prop.startswith("--"):
            out[prop] = " ".join(value.split()).lower()
    return out


def _selectors(prelude):
    # A prelude accumulates any comment that precedes the rule, so strip them
    # before comparing or `/* note */ .selector` never equals `.selector`.
    prelude = re.sub(r"/\*.*?\*/", " ", prelude, flags=re.S)
    return [s.strip() for s in prelude.split(",") if s.strip()]


def _properties_for_selector(sheet, selector):
    """Every property declared for an exact selector token in one sheet."""
    found = set()
    for prelude, body, _media in _iter_rules(SHEETS[sheet]):
        if selector not in _selectors(prelude):
            continue
        found |= set(_declarations(body))
    return found


def _declarations_for_selector(sheet, selector, prop):
    """Every value `prop` is given to an exact selector token in one sheet."""
    values = []
    for prelude, body, _media in _iter_rules(SHEETS[sheet]):
        if selector not in _selectors(prelude):
            continue
        value = _declarations(body).get(prop)
        if value is not None:
            values.append(value)
    return values


def test_tools_cards_declare_the_same_chip_contract():
    """The settings card must declare exactly the chip box the appearance card does.

    Measured defect: on the Tools page, "Workspace settings" chips rendered at
    9.5px / 5px 9px while "Accounts, assets and routing" -- the card added with
    the plug-and-play settings -- rendered at 11px / 7px 12px, because the new
    card was never enrolled in the small-text and chip-geometry contracts that
    the appearance card's selectors belong to. Comparing the declared property
    sets (rather than searching for one selector) means the new card cannot be
    added to only some of those rules and drift again.
    """
    appearance = _properties_for_selector(
        "appearance-overrides.css", "#page-tools .tools-appearance .chip-option"
    )
    settings = _properties_for_selector(
        "appearance-overrides.css", "#page-tools .tool-settings .chip-option"
    )

    assert appearance, "the appearance card no longer declares any chip geometry"
    box = appearance & CHIP_BOX_PROPERTIES
    assert box, "no chip box properties found on the appearance card selector"

    missing = box - settings
    assert not missing, (
        "the settings card's chip selector is missing properties that the "
        f"appearance card declares: {sorted(missing)}. Both cards must declare "
        "the same chip box or they render the same control two different ways."
    )


def test_tools_card_label_and_hint_share_the_small_text_step():
    """Group labels inside the settings card must use the same 9.5px step.

    The 9.5px small-text contract is a single grouped rule; the settings card
    was missing from it, so its "Accounts" / "Assets" / "New York session" labels
    rendered at 12px beside 9.5px labels in every other Tools card.
    """
    grouped = [
        prelude
        for prelude, body, _media in _iter_rules(SHEETS["appearance-overrides.css"])
        if _declarations(body).get("font-size") == "9.5px!important"
    ]
    # The contract is the widest of the 9.5px rules; a narrower one that shares
    # the value is a page refinement, not the grouped contract.
    widest = max(grouped, key=lambda p: len(_selectors(p)), default=None)
    assert widest, "the 9.5px small-text contract rule was not found"
    selectors = set(_selectors(widest))
    assert len(selectors) > 5, (
        "the 9.5px small-text contract should be one grouped rule covering every "
        f"small label on the dashboard, found only {len(selectors)} selectors"
    )
    for required in (
        "html #page-tools .tool-settings .settings-label",
        "html #page-tools .tool-settings .chip-option",
    ):
        assert required in selectors, (
            f"{required} is not enrolled in the 9.5px small-text contract; a new "
            "Tools card that skips it renders larger labels than its neighbours"
        )


def test_home_metric_tiles_reserve_one_height():
    """Every Home metric tile is the same height, so the grid rows cannot step.

    Measured defect: the Home grid had a 40px row and a 32px row. Below 560px
    the label is allowed to wrap rather than be ellipsised, and a wide value
    ("Rs 4,00,000") narrowed the label column until "ACCOUNT VALUE" wrapped,
    making that tile 8px taller than its three row-mates. Reserving the wrapped
    height on every tile is what keeps the rows aligned.
    """
    values = _declarations_for_selector("foundation.css", "#page-overview .metric-card", "min-height")
    assert "40px" in values, (
        "the Home metric card must reserve min-height:40px, found "
        f"{values!r}; without it a wrapped label makes one grid row taller "
        "than the next and the tile grid reads as ragged"
    )


def test_metric_label_is_not_capped_by_a_dead_flex_era_width():
    """The base label rule must not reintroduce a width cap.

    `.metric-card` is a two-column grid. The old `max-width:55%` was a flex-era
    cap that no longer constrained anything -- Home overrides it with 100% (and
    `none` under 560px) and Calendar pins its own -- so it only risked squeezing
    a label for no reason.
    """
    for prelude, body, _media in _iter_rules(SHEETS["styles.css"]):
        if ".metric-card span" not in _selectors(prelude):
            continue
        properties = _declarations(body)
        assert "max-width" not in properties, (
            f"`{prelude}` re-declares max-width on the metric label; the cap is "
            "dead and can only squeeze a label out of its column"
        )


def _compact_rules():
    """(sheet, prelude, properties) for every compact-mode rule."""
    for sheet, css in SHEETS.items():
        for prelude, body, _media in _iter_rules(css):
            if 'data-compact="true"' in prelude:
                yield sheet, prelude, _declarations(body)


def test_compact_mode_never_enlarges_a_surface():
    """Compact must shrink, never grow, and must not resurrect the dead rules.

    Measured defect: the toggle made Home 8px taller and History 14px taller
    and left Calendar and Tools byte-identical, because (a) a compact
    `.metric-card` padding of 8px exceeded the 7px normal value, (b) a 90px
    compact `.empty-state` floor exceeded the 76px natural height, (c) an
    `.section-block`/`.tool-card` rule in the override layer outranked and
    duplicated the real one, and (d) every Tools target lost to an id-scoped
    rule. Each of those is now pinned in both directions.
    """
    compact = list(_compact_rules())

    metric = [
        properties for _sheet, prelude, properties in compact
        if 'html[data-compact="true"] .metric-card' in _selectors(prelude)
    ]
    assert len(metric) == 1, "expected exactly one compact .metric-card rule"
    assert metric[0].get("padding") == "6px 9px!important", (
        "compact .metric-card padding must be smaller than the 7px normal "
        f"value, found {metric[0].get('padding')!r}"
    )

    empty = [
        properties for _sheet, prelude, properties in compact
        if 'html[data-compact="true"] .empty-state' in _selectors(prelude)
    ]
    assert len(empty) == 1, "expected exactly one compact .empty-state rule"
    assert empty[0].get("min-height") == "56px!important", (
        "an empty state is 76px tall; a 90px compact floor made every one of "
        f"them 14px taller than normal, found {empty[0].get('min-height')!r}"
    )

    for _sheet, prelude, _properties in compact:
        for selector in _selectors(prelude):
            target = re.split(r"[\s>+~:]", selector.lstrip("*#."))
            assert not any(part == "tool-card" for part in target), (
                f"`{selector}` re-adds a compact .tool-card padding. The Tools "
                "card is a 0-padding shell whose .tool-body carries the padding, "
                "so this can only make the page taller"
            )


def test_compact_rules_that_target_the_tools_page_carry_its_id():
    """A compact selector must out-specify the id-scoped rule it competes with.

    This is the root cause of the Tools page ignoring Compact entirely:
    `html[data-compact="true"] X` can never beat `#page-tools Y` (an id outranks
    an attribute plus a class), so those rules were silently dead. Whichever
    compact rule targets a class that the Tools page also styles by id must
    therefore repeat the `#page-tools` scope.
    """
    tools_scoped = set()
    for sheet, css in SHEETS.items():
        for prelude, _body, _media in _iter_rules(css):
            for selector in _selectors(prelude):
                if selector.startswith("#page-tools "):
                    tools_scoped.add(selector)

    def _last(selector):
        """The final simple selector of a (possibly compound) selector."""
        parts = re.split(r"[\s>+~]", selector.strip())
        return parts[-1] if parts else ""

    def _tail(selector):
        """The part of a compact selector that has to survive id scoping."""
        return re.sub(r"^html(\[[^\]]*\])+", "", selector).strip()


    # Targets a `#page-tools`-scoped compact rule already covers. Those are
    # fine: the unscoped rule still serves the other four pages, and the scoped
    # one is what actually reaches the Tools page.
    covered = {
        _last(selector)
        for _sheet, prelude, _properties in _compact_rules()
        if "#page-tools" in prelude
        for selector in _selectors(prelude)
    }

    offenders = []
    for sheet, prelude, _properties in _compact_rules():
        for selector in _selectors(prelude):
            if "#page-tools" in selector or _last(selector) in covered:
                continue
            tail = _tail(selector)
            if tail and any(sel.startswith(f"#page-tools {tail}") for sel in tools_scoped):
                offenders.append(
                    f"{sheet}: `{selector}` loses to `#page-tools {tail}`, which "
                    "an id always outranks, and no `#page-tools` compact rule "
                    "covers it; repeat the id scope so Compact reaches Tools"
                )
    assert not offenders, (
        "compact rules that can never win against an id-scoped rule:\n  "
        + "\n  ".join(offenders)
    )


def test_settings_toggle_is_only_a_chip_variant_not_a_second_component():
    """`.settings-toggle` must not carry its own base component definition.

    Measured defect: the class named two different components. One was a 56px
    settings switch row with a `span`/`b`/`small`/`i` knob and no markup
    anywhere in the app; the other was a chip. Eleven properties fought between
    them and the chip won only because the later sheet happened to load last.
    """
    assert ".settings-toggle-list" not in ALL_CSS, (
        "`.settings-toggle-list` styled a settings switch list that no markup "
        "in dashboard.html or app.js has ever produced"
    )

    # Exactly one base definition, and it must be the chip. `:hover`, `:active`
    # and `.active` variants are legitimate hooks and are not counted.
    base = [
        (sheet, prelude, _declarations(body))
        for sheet, css in SHEETS.items()
        for prelude, body, _media in _iter_rules(css)
        if ".settings-toggle" in _selectors(prelude)
    ]
    assert len(base) == 1, (
        "`.settings-toggle` must have exactly one base definition, found "
        f"{len(base)}: {[p for _s, p, _d in base]}. Two base definitions is "
        "what let a 56px switch row and a chip fight over eleven properties."
    )
    sheet, prelude, properties = base[0]
    chip = [
        _declarations(body)
        for p, body, _media in _iter_rules(SHEETS["styles.css"])
        if ".chip-option" in _selectors(p)
    ]
    assert chip, "the base `.chip-option` rule was not found"
    box = CHIP_BOX_PROPERTIES & set(properties)
    assert box, f"{sheet} `{prelude.strip()}` declares no chip box properties"
    mismatch = {
        prop: (properties.get(prop), expected.get(prop))
        for prop, expected in ((p, chip[0]) for p in box)
        if prop != "color" and properties.get(prop) != expected.get(prop)
    }
    assert not mismatch, (
        f"{sheet} `{prelude.strip()}` must declare `.settings-toggle` exactly as "
        f"`.chip-option` does; these differ (settings-toggle vs chip): {mismatch}"
    )
    for switch_row_marker in ("border-bottom",):
        assert switch_row_marker not in properties, (
            f"{sheet} `{prelude.strip()}` still carries the switch-row property "
            f"`{switch_row_marker}`; that is the second component, not a chip"
        )

    for source, text in (("dashboard.html", HTML), ("app.js", APP)):
        for match in re.finditer(r'class="([^"]*\bsettings-toggle\b[^"]*)"', text):
            classes = match.group(1).split()
            assert "chip-option" in classes, (
                f"{source} uses `settings-toggle` without `chip-option`: "
                f"{match.group(1)!r}. With no chip base the button would have no "
                "border, fill or type styling at all"
            )


def test_calendar_agenda_status_is_not_declared_twice_in_one_layer():
    """No top-level rule may be fully restated by a later rule in the same sheet.

    Measured defect: `appearance-overrides.css` declared
    `#page-calendar .calendar-agenda-status` twice at top level. The first
    (padding 8px 12px, gap 8px) was superseded wholesale by the second
    (padding 10px var(--ui-pad-x), gap 10px), so it could only ever mislead the
    next reader about which values the component uses.
    """
    declarations = {}
    for prelude, body, media in _iter_rules(SHEETS["appearance-overrides.css"]):
        if media != "none":
            continue
        if "#page-calendar .calendar-agenda-status" not in _selectors(prelude):
            continue
        for prop in _declarations(body):
            declarations.setdefault(prop, 0)
            declarations[prop] += 1

    repeated = sorted(prop for prop, count in declarations.items() if count > 1)
    assert not repeated, (
        "these properties are declared more than once for the same selector at "
        f"top level in appearance-overrides.css: {repeated}. The superseded "
        "passes must be merged, not left in place to lose by load order"
    )


def test_universe_grid_declares_only_its_live_layout():
    """`.universe-grid` is a block of asset rows, not a grid.

    Measured defect: the block rule declared `display:grid` with one column and
    `gap:0`, plus `border:0`, `border-radius:0` and `overflow:visible`, while
    later rules in the same sheet declare `display:block`, a 1px border and a
    radius. Eleven mutually-overriding `!important` properties, one winner,
    chosen by document order rather than intent.
    """
    for sheet in SHEETS:
        for prelude, body, _media in _iter_rules(SHEETS[sheet]):
            if "#page-tools .universe-grid" not in _selectors(prelude):
                continue
            properties = _declarations(body)
            assert "display" not in properties or properties["display"] == "block!important", (
                f"{sheet} declares a dead layout for `.universe-grid`: "
                f"display:{properties.get('display')}. The asset rows are a block "
                "stack; only one layout declaration may exist"
            )
            for dead in ("grid-template-columns",):
                assert dead not in properties, (
                    f"{sheet} declares `{dead}` on a block container: "
                    f"{properties.get(dead)!r}"
                )


def test_no_universe_grid_rule_is_fully_superseded_in_one_sheet():
    """A `.universe-grid` rule must not restate what a later rule already sets."""
    rules = [
        (prelude, _declarations(body), media)
        for prelude, body, media in _iter_rules(SHEETS["styles.css"])
        if "#page-tools .universe-grid" in _selectors(prelude)
    ]
    for index, (prelude, properties, media) in enumerate(rules):
        if len(properties) < 3:
            # A one-property pass is a legitimate layering refinement; the defect
            # was a whole block of layout properties that could never win.
            continue
        for later_prelude, later, later_media in rules[index + 1 :]:
            if later_media != media:
                # A responsive override is a legitimate restatement of the base.
                continue
            superseded = set(properties) & set(later)
            if superseded == set(properties) and properties:
                assert False, (
                    f"`{prelude}` is fully superseded by the later "
                    f"`{later_prelude}` on {sorted(superseded)}; it can never "
                    "win and only misleads the next reader"
                )