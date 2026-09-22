# MULTIBOT2 Figma UI System

Design reference: https://www.figma.com/design/Z9QPPjUugr8uiHqAczt3mn

## Intent

This UI layer is a visual-system cleanup only. It does not alter signal generation, backtesting logic, risk rules, asset universe, persistence, or Telegram delivery.

## Visual system

- Mavis green accent with neutral light/dark surfaces
- One spacing rhythm: 8 / 12 / 20
- Compact controls with 34–36px action heights
- 10–16px corner radii for modern mode
- Subtle borders and restrained shadows
- BUY / SELL / FRESH / STALE use semantic status colors
- Responsive layouts preserve the same hierarchy on desktop and mobile
- Neo Brutalism remains an independent presentation option

## Main screens

1. Home — command center, KPIs, equity curve, risk limits, signal activity and live signals
2. Signals — grouped signal ledger with compact filters
3. History — completed trades, open positions and scan history
4. Calendar — date-grouped market events and impact summaries
5. Tools — appearance, backtest, universe, accounts, locked rules, diagnostics and release info

## Code handoff

- mavis-ui.css is the single new UI-system layer.
- dashboard.html loads it after the existing appearance overrides so existing DOM/wiring contracts remain intact.
- No business-logic files were changed in this UI pass.