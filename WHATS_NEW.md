# What's New — MULTIBOT2 v3.2.8

Generated from release_notes.py.

- ✨ Release notes moved into a header button with a modal, freeing a full dashboard section.
- 🎯 Modern style now matches Neo Brutalism's tactile feel: hover lift and press feedback on every interactive control.
- 🐛 Fixed the mobile navigation anchoring to the page bottom instead of the screen: the html element no longer matches the theme-button selectors.
- 🎨 Rebalanced the color system: neutral slate surfaces replace the green-tinted palette and all five accent choices are cleaner in light and dark themes.
- 📲 The fixed bottom navigation now also covers tablet widths, so there is no viewport range without navigation.
- 📱 Backtest trades and generated signals are bounded, touch-scrollable panels that no longer stretch the mobile page or sit behind navigation.
- 🗂️ Signals and History date groups use consistent spacing and borders so headings and dates are never hidden or clipped.
- 🔒 Dashboard API reads now validate HTTP status, body and JSON before rendering, preventing stale results after empty or malformed responses.
