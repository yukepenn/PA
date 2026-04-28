### [Unreleased] – 2026-04-27
- Feat(sim): add deterministic sim foundation
- Fix(sim): harden persistence and UI semantics
- Fix(replay_dash): authoritative trade episode VWAP from fills; RR zones use planned bracket levels + entry_order_id
- Fix(replay_dash): viewport store — no autorange wipe; wide_revealed mode + xaxis.range list parsing for stable manual zoom across step
- Fix(replay_dash): session-time default x-axis (full RTH); y from revealed bars; plot full revealed history; Autoscale/wide_revealed match session view; remove adaptive bar-window fit
- Style(replay_dash): minimal order-type hints for LIMIT/STOP/MKT short/long grammar
- Fix(data): auto-detect repo `TradingData` root; env override `PA_TRADINGDATA_BASE`

