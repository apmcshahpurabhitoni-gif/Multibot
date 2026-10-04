// Sweep every appearance combination and assert the matrix from
// docs/DESIGN_SYSTEM/validation.md §3.
//
// The combination is switched through the appearance entry points -- the same
// path a user's click on a chip takes -- which write the localStorage keys
// `initAppearance()` reads on the next bootstrap. Assigning `dataset`
// directly would be reverted on the next poll, which is the mistake that doc
// warns about, so that is deliberately not done here.
//
// Run with: playwright-cli eval "$(cat tools/sweep_appearance.js)"
(() => {
  const STYLES = ["modern", "material3", "neo"];
  const ACCENTS = ["emerald", "indigo", "amber", "rose", "cyan"];
  const THEMES = ["light", "dark"];
  // The viewport is owned by `playwright-cli resize`, not by the page, so this
// sweep runs once per width and reports the width it measured.
  const results = [];
  const VIEWPORT = `${window.innerWidth}x${window.innerHeight}`;

  const round = (n) => Math.round(n * 100) / 100;

  const checkPage = () => {
    const problems = [];
    if (document.documentElement.scrollWidth > window.innerWidth) {
      problems.push(`overflow ${document.documentElement.scrollWidth}>${window.innerWidth}`);
    }
    const controls = [
      ...document.querySelectorAll("button, a, [role=button], input, select"),
    ].filter((el) => el.offsetParent !== null);
    for (const el of controls) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && (r.width < 24 || r.height < 24)) {
        problems.push(`target ${Math.round(r.width)}x${Math.round(r.height)} ${el.className || el.tagName}`);
      }
    }
    const h1s = [...document.querySelectorAll("h1")].filter((el) => el.offsetParent !== null);
    if (h1s.length !== 1) problems.push(`h1 count ${h1s.length}`);
    for (const el of controls) {
      const named = (el.getAttribute("aria-label") || el.textContent || "").trim();
      if (!named) problems.push(`unnamed ${el.className || el.tagName}`);
    }
    for (const el of document.querySelectorAll("input, select")) {
      if (el.offsetParent === null) continue;
      const labelled =
        el.getAttribute("aria-label") ||
        el.closest("label") ||
        el.labels?.length;
      if (!labelled) problems.push(`unlabelled input ${el.className || el.type}`);
    }
    return problems;
  };

  const openTools = () => {
    setPage("tools");
    document.querySelectorAll("[data-tool-collapse]").forEach((card) => {
      if (!card.classList.contains("is-open")) card.querySelector("[data-tool-toggle]").click();
    });
  };

  for (const style of STYLES) {
    for (const accent of ACCENTS) {
      for (const theme of THEMES) {
        window.applyStyle(style);
        window.applyAccent(accent);
        applyTheme(theme);
        // Force a reflow so the new geometry is measured, not the old one.
        void document.body.offsetHeight;
        const key = `${VIEWPORT} ${style}/${accent}/${theme}`;
        const problems = [];
        const rootStyle = document.documentElement.dataset.style;
        const rootAccent = document.documentElement.dataset.accent;
        if (rootStyle !== style) problems.push(`style=${rootStyle}`);
        if (rootAccent !== accent) problems.push(`accent=${rootAccent}`);
        if (localStorage.getItem("mavis-style") !== style) problems.push("style not persisted");
        if (localStorage.getItem("mavis-accent") !== accent) problems.push("accent not persisted");
        if (localStorage.getItem("mavis-theme") !== theme) problems.push("theme not persisted");
        openTools();
        problems.push(...checkPage());
        results.push({ key, problems });
      }
    }
  }

  const failed = results.filter((r) => r.problems.length);
  return JSON.stringify(
    {
      viewport: VIEWPORT,
      rendered: results.length,
      failed: failed.length,
      failures: failed.slice(0, 12),
      sample: results.filter((_, i) => i % 7 === 0).map((r) => r.key),
    },
    null,
    1,
  );
})()