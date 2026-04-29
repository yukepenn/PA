### [Unreleased] – 2026-04-27
- Feat(sim): add deterministic sim foundation
- Fix(sim): harden persistence and UI semantics
- Fix(replay_dash): authoritative trade episode VWAP from fills; RR zones use planned bracket levels + entry_order_id
- Fix(replay_dash): viewport store — no autorange wipe; wide_revealed mode + xaxis.range list parsing for stable manual zoom across step
- Fix(replay_dash): session-time default x-axis (full RTH); y from revealed bars; plot full revealed history; Autoscale/wide_revealed match session view; remove adaptive bar-window fit
- Style(replay_dash): minimal order-type hints for LIMIT/STOP/MKT short/long grammar
- Fix(data): auto-detect repo `TradingData` root; env override `PA_TRADINGDATA_BASE`

### [Unreleased] – 2026-04-28
- Fix(replay_dash): move store JSON decoding into store_io module (StringIO)
- Fix(replay_dash): make sim overlay marker names use full order_id
- Test(unit): add trade_viz/viewport/marker identity tests; add pytest conftest for src imports
- Feat(replay_dash): working-order drag v1 (modify working order prices via sim truth)
- Chore(repo): remove cache artifacts; add agent handoff doc
- Refactor(replay_dash): extract pure sim view render helpers and reorganize layout into section builders (no behavior change)

