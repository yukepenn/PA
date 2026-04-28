from __future__ import annotations

import argparse
import os
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .ibkr_raw_ingest import (
    IbkrConfig,
    RAW_BASE_DEFAULT,
    fetch_bars_1min,
    to_canonical_bars_1min,
    upsert_monthly_parquet,
    connect_ib,
)


def _parse_end_to_utc(end_str: str) -> pd.Timestamp:
    s = end_str.strip()
    parts = s.split()
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
    p = argparse.ArgumentParser(description="Monthly-chunk backfill for IBKR 1-min raw bars (stocks/ETFs).")
    p.add_argument("--symbol", default="SPY")
    p.add_argument("--host", default=os.getenv("IB_HOST", "127.0.0.1"))
    p.add_argument("--port", type=int, default=int(os.getenv("IB_PORT", "4002")))
    p.add_argument("--client_id", type=int, default=int(os.getenv("IB_CLIENT_ID", "19")))

    p.add_argument("--start", required=True, help='Start date (YYYY-mm-dd), interpreted in America/New_York RTH context.')
    p.add_argument("--end", required=True, help='End datetime (e.g. "2026-04-23 16:00:00 America/New_York").')
    p.add_argument("--sleep_s", type=float, default=2.0, help="Sleep between requests (default: 2s).")
    p.add_argument("--base_dir", default=str(RAW_BASE_DEFAULT))
    p.add_argument("--what", default="TRADES")
    p.add_argument("--rth", action="store_true")
    p.add_argument("--no-rth", dest="rth", action="store_false")
    p.set_defaults(rth=True)
    return p.parse_args()


def _month_end_sequence(end_utc: pd.Timestamp, start_date: pd.Timestamp) -> list[pd.Timestamp]:
    # Walk backwards by month boundaries using ET months, but expressed in UTC instants for IBKR endDateTime.
    et = "America/New_York"
    end_et = pd.Timestamp(end_utc).tz_convert(et)
    start_et = pd.Timestamp(start_date).tz_localize(et)

    seq: list[pd.Timestamp] = []
    cur = end_et
    while cur.date() >= start_et.date():
        seq.append(cur.tz_convert("UTC"))
        # Step back by one calendar month at the same local wall-clock time.
        # This avoids tying chunk boundaries to month-begins and keeps the logic simple.
        cur = cur - pd.DateOffset(months=1)
    return seq


def main() -> int:
    args = _parse_args()
    cfg = IbkrConfig(host=args.host, port=int(args.port), client_id=int(args.client_id))

    start_date = pd.Timestamp(args.start)
    end_utc = _parse_end_to_utc(args.end)
    start_floor_utc = pd.Timestamp(args.start).tz_localize("America/New_York").tz_convert("UTC")

    month_ends = _month_end_sequence(end_utc, start_date)
    if not month_ends:
        raise SystemExit("Nothing to do (end < start).")

    ib = connect_ib(cfg)
    try:
        total_rows = 0
        for i, chunk_end_utc in enumerate(month_ends, start=1):
            print(f"REQ {i}/{len(month_ends)} end_utc={chunk_end_utc} duration=1 M", flush=True)
            df_ib = fetch_bars_1min(
                ib,
                symbol=args.symbol,
                duration="1 M",
                what=args.what,
                rth_only=bool(args.rth),
                end_utc=chunk_end_utc,
            )
            canonical = to_canonical_bars_1min(df_ib, symbol=args.symbol, rth_only=bool(args.rth))
            canonical = canonical[canonical["ts_utc"] >= start_floor_utc].reset_index(drop=True)

            written = upsert_monthly_parquet(Path(args.base_dir), canonical)
            total_rows += len(canonical)

            print(
                f"CHUNK {i}/{len(month_ends)} end_utc={chunk_end_utc} rows={len(canonical)} wrote={len(written)}",
                flush=True,
            )
            if args.sleep_s > 0 and i < len(month_ends):
                time.sleep(float(args.sleep_s))

        print(f"OK: symbol={args.symbol.upper()} chunks={len(month_ends)} total_rows_ingested={total_rows}", flush=True)
        return 0
    finally:
        ib.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())

