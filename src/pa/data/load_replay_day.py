from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .ibkr_raw_ingest import RAW_BASE_DEFAULT, RAW_REL, CANONICAL_COLS, validate_canonical_bars_1min


@dataclass(frozen=True)
class ReplayDayRequest:
    symbol: str
    date_et: str  # YYYY-mm-dd
    base_dir: Path = RAW_BASE_DEFAULT
    rth_only: bool = True  # raw layer is currently RTH-only


def _month_partition_path(base_dir: Path, symbol: str, year: int, month: int) -> Path:
    return (
        Path(base_dir)
        / RAW_REL
        / f"symbol={symbol.upper()}"
        / f"year={year:04d}"
        / f"month={month:02d}"
        / "data.parquet"
    )


def load_replay_day_1min(req: ReplayDayRequest) -> pd.DataFrame:
    """
    Load one ET trading day of 1-minute bars from the monthly Parquet partitions.

    Returns canonical columns with `ts_utc` UTC-aware and sorted ascending.
    """
    symbol = req.symbol.upper().strip()
    et = "America/New_York"
    day_et = pd.Timestamp(req.date_et).tz_localize(et)
    day_start_utc = day_et.tz_convert("UTC")
    day_end_utc = (day_et + pd.Timedelta(days=1)).tz_convert("UTC")

    y = int(day_et.year)
    m = int(day_et.month)
    p = _month_partition_path(req.base_dir, symbol, y, m)
    if not p.exists():
        raise FileNotFoundError(f"Monthly partition not found: {p}")

    df = pd.read_parquet(p)
    df = df[CANONICAL_COLS].copy()
    validate_canonical_bars_1min(df)

    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="raise")
    df = df[(df["ts_utc"] >= day_start_utc) & (df["ts_utc"] < day_end_utc)].copy()

    if req.rth_only:
        df = df[df["rth_only"] == True]  # noqa: E712

    df = df.sort_values("ts_utc", ascending=True, kind="mergesort").reset_index(drop=True)
    if df.empty:
        raise ValueError(f"No bars found for symbol={symbol} date_et={req.date_et} in {p}")
    return df

