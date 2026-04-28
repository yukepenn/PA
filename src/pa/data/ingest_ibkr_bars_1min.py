from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd

from .ibkr_raw_ingest import (
    IbkrConfig,
    RAW_BASE_DEFAULT,
    connect_ib,
    fetch_bars_1min,
    to_canonical_bars_1min,
    upsert_monthly_parquet,
)


def _parse_end_to_utc(end_str: str) -> pd.Timestamp:
    s = end_str.strip()
    if not s:
        raise ValueError("end datetime string is empty")

    parts = s.split()
    # Allow: "2026-04-23 16:00:00 America/New_York"
    if len(parts) >= 3 and ("/" in parts[-1]):
        tz = parts[-1]
        dt_part = " ".join(parts[:-1])
        ts = pd.Timestamp(dt_part)
        if ts.tzinfo is not None:
            return ts.tz_convert("UTC")
        return ts.tz_localize(tz).tz_convert("UTC")

    ts = pd.Timestamp(s)
    if ts.tzinfo is None:
        raise ValueError('end datetime must include timezone, e.g. "2026-04-23 16:00:00 America/New_York"')
    return ts.tz_convert("UTC")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ingest IBKR 1-min bars into formal raw Parquet storage.")
    p.add_argument("--symbol", default="SPY", help="Symbol to download (default: SPY)")
    p.add_argument("--host", default=os.getenv("IB_HOST", "127.0.0.1"))
    p.add_argument("--port", type=int, default=int(os.getenv("IB_PORT", "4002")))
    p.add_argument("--client_id", type=int, default=int(os.getenv("IB_CLIENT_ID", "19")))

    p.add_argument("--duration", default="2 D", help="IB durationStr (default: 2 D)")
    p.add_argument("--what", default="TRADES", help='whatToShow (default: "TRADES")')
    p.add_argument("--rth", action="store_true", help="Regular Trading Hours only (default: true)")
    p.add_argument("--no-rth", dest="rth", action="store_false")
    p.set_defaults(rth=True)
    p.add_argument(
        "--end",
        default="",
        help='Optional request end datetime (e.g. "2026-04-23 16:00:00 America/New_York"). Default: now.',
    )

    p.add_argument(
        "--base_dir",
        default=str(RAW_BASE_DEFAULT),
        help='Base directory for all maintained data (default: auto-detected "<repo>/TradingData"; override via env PA_TRADINGDATA_BASE)',
    )
    p.add_argument("--debug_csv", default="", help="Optional path to write canonical CSV for inspection.")
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    cfg = IbkrConfig(host=args.host, port=int(args.port), client_id=int(args.client_id))
    ib = connect_ib(cfg)
    try:
        end_utc = None
        if args.end.strip():
            end_utc = _parse_end_to_utc(args.end)

        df_ib = fetch_bars_1min(
            ib,
            symbol=args.symbol,
            duration=args.duration,
            what=args.what,
            rth_only=bool(args.rth),
            end_utc=end_utc,
        )
        canonical = to_canonical_bars_1min(df_ib, symbol=args.symbol, rth_only=bool(args.rth))

        if args.debug_csv.strip():
            p = Path(args.debug_csv)
            p.parent.mkdir(parents=True, exist_ok=True)
            canonical.to_csv(p, index=False)

        written = upsert_monthly_parquet(Path(args.base_dir), canonical)

        ts_min = canonical["ts_utc"].min()
        ts_max = canonical["ts_utc"].max()
        rng = f"{ts_min} .. {ts_max}" if pd.notna(ts_min) and pd.notna(ts_max) else "n/a"

        print(f"OK: symbol={args.symbol.upper()} rows={len(canonical)} range={rng}")
        for w in written:
            print(f"WROTE: {w}")
        return 0
    finally:
        ib.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())

