# PA (Price Action) — Data Foundation

This repository is currently focused on building a **formal raw market data layer** for discretionary price-action training.

## Raw data layer (v1)

- **Root**: `<repo>/TradingData/` (default auto-detected)
- **Override**: set env `PA_TRADINGDATA_BASE` to point elsewhere (e.g. `C:\PA\TradingData`)
- **Canonical raw layer**: IBKR **1-minute bars only**
- **Format**: Parquet (monthly partitions)
- **Canonical timestamp column**: `ts_utc` (stored in **UTC**)
- **Defaults**: `useRTH=True`, `whatToShow="TRADES"`

### Storage layout

`<repo>\TradingData\raw\ibkr\bars_1min\symbol=<SYMBOL>\year=<YYYY>\month=<MM>\data.parquet`

### Canonical schema

- `ts_utc`
- `symbol`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `bar_size` (always `"1min"`)
- `source` (always `"ibkr"`)
- `rth_only`

## Quickstart

Install dependencies:

```bash
pip install -r requirements.txt
```

Pull a small sample (ends at a fixed datetime):

```bash
python -m pa.data.ingest_ibkr_bars_1min --symbol SPY --duration "4 D" --end "2026-04-23 16:00:00 America/New_York"
```

Run a monthly backfill:

```bash
python -m pa.data.backfill_ibkr_1min --symbol SPY --start "2025-05-01" --end "2026-04-23 16:00:00 America/New_York"
```

Validate stored raw data:

```bash
python -m pa.data.validate_raw_bars --symbol SPY --start "2025-05-01" --end "2026-04-23 16:00:00 America/New_York"
```

## Acceptance checklist (raw v1)

- Monthly `data.parquet` files exist for expected months
- Duplicate count by `(symbol, ts_utc)` is `0`
- Schema matches the canonical columns and constraints (`ts_utc` is UTC, `bar_size="1min"`, `source="ibkr"`, `rth_only=True`)
- Daily bar counts in RTH are typically `390` (with expected half-days/holidays lower)

