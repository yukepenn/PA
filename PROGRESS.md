<!-- PROGRESS.md -->
- [2026-04-27] Added v1 sim layer foundation (models, fills, PnL, persistence)
- [2026-04-27] Hardened sim UI glue (monotonic warnings, idempotent fills)
- [2026-04-27] Fixed trade episode entry/exit VWAP + planned RR linkage; chart uses authoritative fill prices (no midpoint leakage)
- [2026-04-27] Fixed viewport: double-click autorange no longer clears ranges; wide_revealed + explicit Plotly range parsing preserves view across Next1
- [2026-04-27] Replay chart default viewport: full RTH session x-range (09:30–16:00 ET), all revealed bars plotted; removed bar-count adaptive window / fit-to-visible-bars x-axis
- [2026-04-27] Data root path: auto-detect `<repo>/TradingData` by default; allow override via `PA_TRADINGDATA_BASE` (portable across drives)

