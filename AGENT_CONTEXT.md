## What this repo is

PA (“Price Action”) is a local-first discretionary trading replay + manual sim workspace. It treats **raw IBKR 1‑minute bars stored as parquet** as the canonical market data layer and builds a **no‑future‑leakage replay view** plus a **deterministic manual trading simulator** and chart-first Dash UI.

## Current product goal

- Provide a reliable replay trainer where the user can step through a session with **strict revealed-slice semantics**, annotate decisions, and place/modify simulated orders with **sim-truth-only state changes**.

## Current maturity level

- Raw data layer v1 is established (IBKR 1‑minute parquet canonical layout).
- Replay engine is minimal and explicit.
- Sim engine is deterministic with conservative intrabar assumptions.
- Dash app is the current UI entrypoint; tests lock key invariants.

## Package layout (durable core)

- `src/pa/data/`
  - Raw IBKR 1‑minute ingest/backfill/validate and replay-day loading/resampling helpers.
  - Canonical on-disk root is `TradingData/` (override via `PA_TRADINGDATA_BASE`).
- `src/pa/replay/`
  - Replay “truth”: current revealed index + visible slice, no future leakage.
- `src/pa/sim/`
  - Deterministic simulator “truth”: orders, fills, positions, bracket/OCO, persistence.
- `src/pa/apps/replay_dash/`
  - Dash UI glue: chart rendering, viewport logic, interaction + draft overlays, sim overlays, callbacks.
- `assets/`
  - Dash client-side helpers (keyboard, hover price).
- `tests/`
  - Durable invariant tests (sim semantics, viewport/marker identity, trade viz VWAPs, working-order drag contract).

## Main entry points / how to run

- **Dash app (current UI)**:

```bash
python -m pa.apps.replay_dash_app
```

- **Install deps**:

```bash
pip install -r requirements.txt
```

- **Ingest sample raw data** (example from `README.md`):

```bash
python -m pa.data.ingest_ibkr_bars_1min --symbol SPY --duration "4 D" --end "2026-04-23 16:00:00 America/New_York"
```

## Non-negotiable invariants (verified in code)

- **Canonical market data layer**: local **IBKR 1‑minute parquet** under `TradingData/raw/...` (see `README.md`).
- **No future leakage**:
  - `pa.replay.engine.ReplayEngine.visible_bars()` is the canonical revealed slice.
  - Chart overlays derived from sim state must be **clipped to the replay visible end** when rendering.
- **Sim truth is single source of truth**:
  - Real orders/fills/position live in `SimEngine.state` and are serialized into `SIM_STORE` for UI.
  - UI interactions may preview (draft overlays), but sim state changes must go through sim APIs (e.g. `SimEngine.modify_order_price` for working-order drag).
- **Monotonic, deterministic sim**:
  - Deterministic processing order and conservative OHLC fills.
  - Bracket legs arm from the **next 1‑minute bar after entry fill** (no hindsight activation).
  - OCO cancels sibling when one fills.
  - “No flip in one step”: fills that would flip the position are rejected.
- **Single figure owner**:
  - `render_chart` in `src/pa/apps/replay_dash/callbacks.py` owns the figure lifecycle (build base chart → add overlays → apply viewport).
- **Viewport semantics**:
  - Default: full-session **RTH x-range** (09:30–16:00 ET converted to UTC) and **y-range from revealed bars only**.
  - Manual pan/zoom is preserved when `viewport.mode == "manual"`; autoscale/reset is explicit.

## Replay truth / sim truth / UI glue boundaries

- **Replay truth**: `ReplayEngine` only exposes revealed bars; everything else (layout, overlays) must respect this.
- **Sim truth**: `SimEngine` owns state transitions; UI reads `SIM_STORE` and uses sim APIs for commits.
- **UI glue**: draft overlays + hover overlays are explicitly UI-only previews (no sim mutation).

## Overlay lifecycle grammar (current)

- **Draft** (UI-only): shown only when `_draft_overlays_allowed(sim_store)` is true (no open position and no active working orders).
- **Hover** (UI-only): ephemeral marker updated by client hover events.
- **Sim overlays** (display-only): derived from `SIM_STORE` and clipped to `visible_end_utc` to avoid future leakage.

## Durable test surface (keep these)

- `tests/test_sim_semantics.py`: deterministic sim invariants (activation, stop-limit behavior, bracket/OCO, no-flip).
- `tests/test_trade_viz.py`: trade episode VWAP derivation + planned bracket linkage.
- `tests/test_viewport_and_markers.py`: RTH session range contract + marker naming contract.
- `tests/test_working_order_drag_v1.py`: marker-key contract + `modify_order_price` contract.

## Editing rules for future agents

- Do **not** change replay/sim semantics without tests that prove no regression.
- Do **not** introduce new one-off scripts/tests into the durable surface; keep `tests/` intentional.
- Keep chart state boundaries strict:
  - preview = UI overlays
  - commit = sim APIs only
- Any changes affecting chart semantics should bump the chart style token (search for `PA-BW-v1`) intentionally.

## What not to add casually

- Scratch notebooks, ad-hoc scripts, or debug files committed into the repo root.
- Additional order state machines or duplicate “stores of truth”.
- Generated caches (`__pycache__`, `.pytest_cache`, etc.) — keep untracked/ignored.

## Likely next milestone

- Continue hardening replay+sim UI contracts (order placement/commit pathways, interaction edge cases) while preserving strict no-future-leakage and deterministic sim processing.

