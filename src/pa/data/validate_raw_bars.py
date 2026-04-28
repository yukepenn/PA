from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .ibkr_raw_ingest import CANONICAL_COLS, RAW_BASE_DEFAULT, RAW_REL, validate_canonical_bars_1min


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
    p = argparse.ArgumentParser(description="Validate stored raw IBKR 1-min parquet partitions.")
    p.add_argument("--symbol", default="SPY")
    p.add_argument("--base_dir", default=str(RAW_BASE_DEFAULT))
    p.add_argument("--start", default="", help="Optional start date YYYY-mm-dd (ET) for checks.")
    p.add_argument("--end", default="", help='Optional end datetime (e.g. "2026-04-23 16:00:00 America/New_York") for checks.')
    return p.parse_args()


def _list_month_files(base_dir: Path, symbol: str) -> list[Path]:
    root = Path(base_dir) / RAW_REL / f"symbol={symbol.upper()}"
    if not root.exists():
        return []
    return sorted(root.rglob("data.parquet"))


def main() -> int:
    args = _parse_args()
    base_dir = Path(args.base_dir)
    symbol = args.symbol.upper().strip()

    files = _list_month_files(base_dir, symbol)
    if not files:
        raise SystemExit(f"No partitions found under {(base_dir / RAW_REL / f'symbol={symbol}')}")

    start_utc = None
    end_utc = None
    if args.start.strip():
        start_utc = pd.Timestamp(args.start).tz_localize("America/New_York").tz_convert("UTC")
    if args.end.strip():
        end_utc = _parse_end_to_utc(args.end)

    print(f"FOUND: {len(files)} monthly files for symbol={symbol}")

    all_daily_counts: list[pd.DataFrame] = []
    any_errors = False

    for p in files:
        df = pd.read_parquet(p)
        try:
            validate_canonical_bars_1min(df[CANONICAL_COLS])
        except Exception as e:
            any_errors = True
            print(f"SCHEMA_FAIL: {p} err={e}")
            continue

        df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="raise")
        if start_utc is not None:
            df = df[df["ts_utc"] >= start_utc]
        if end_utc is not None:
            df = df[df["ts_utc"] <= end_utc]

        dups = int(df.duplicated(subset=["symbol", "ts_utc"]).sum())
        ts_min = df["ts_utc"].min() if not df.empty else None
        ts_max = df["ts_utc"].max() if not df.empty else None

        # Daily bar counts in ET (RTH context)
        if not df.empty:
            ts_et = df["ts_utc"].dt.tz_convert("America/New_York")
            daily = ts_et.dt.date.value_counts().sort_index()
            daily_df = daily.rename("bars").to_frame()
            all_daily_counts.append(daily_df)

        print(f"OK: {p} rows={len(df)} dups={dups} min={ts_min} max={ts_max}")
        if dups != 0:
            any_errors = True

    if all_daily_counts:
        daily_all = pd.concat(all_daily_counts).groupby(level=0).sum().sort_index()
        desc = daily_all["bars"].describe(percentiles=[0.01, 0.05, 0.5, 0.95, 0.99]).to_dict()
        print("DAILY_BARS_SUMMARY_ET:")
        for k in ["count", "mean", "min", "1%", "5%", "50%", "95%", "99%", "max"]:
            if k in desc:
                v = desc[k]
                if isinstance(v, float):
                    v = round(v, 3)
                print(f"  {k}: {v}")

        # Show a few low-count days (quick gap smoke)
        low = daily_all.sort_values("bars").head(10)
        print("LOWEST_DAILY_COUNTS_ET (top 10):")
        for d, r in low.iterrows():
            print(f"  {d}: {int(r['bars'])}")

    if any_errors:
        raise SystemExit("VALIDATION_FAILED (see messages above)")

    print("VALIDATION_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

