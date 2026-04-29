<!-- PROGRESS.md -->
- [2026-04-27] Added v1 sim layer foundation (models, fills, PnL, persistence)
- [2026-04-27] Hardened sim UI glue (monotonic warnings, idempotent fills)
- [2026-04-27] Fixed trade episode entry/exit VWAP + planned RR linkage; chart uses authoritative fill prices (no midpoint leakage)
- [2026-04-27] Fixed viewport: double-click autorange no longer clears ranges; wide_revealed + explicit Plotly range parsing preserves view across Next1
- [2026-04-27] Replay chart default viewport: full RTH session x-range (09:30–16:00 ET), all revealed bars plotted; removed bar-count adaptive window / fit-to-visible-bars x-axis
- [2026-04-27] Data root path: auto-detect `<repo>/TradingData` by default; allow override via `PA_TRADINGDATA_BASE` (portable across drives)
- [2026-04-28] Replay Dash reliability: moved store JSON→DataFrame decoding into `store_io.py` (pandas FutureWarning fix); consolidated draft lifecycle helpers; hardened sim overlay identity (full order_id in marker names); added unit tests for trade_viz + viewport + marker naming; added pytest conftest for `src/` import
- [2026-04-28] Working-order drag v1: draggable working order lines; mouseup commits via sim-truth `modify_order_price`; added marker key helper + unit tests
- [2026-04-28] Repo hygiene: removed committed cache artifacts; added `AGENT_CONTEXT.md` handoff for future agents
- [2026-04-28] Replay Dash maintainability pass: extracted pure sim panel rendering helpers to `sim_view.py`, thinned callback view formatting, and split `layout.py` into section builders with unchanged IDs/behavior

