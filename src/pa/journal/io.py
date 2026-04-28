from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pandas as pd

from ..data.ibkr_raw_ingest import RAW_BASE_DEFAULT
from .schemas import DecisionRecord


JOURNAL_BASE_DEFAULT = RAW_BASE_DEFAULT / "journal"


def _atomic_write_parquet(df: pd.DataFrame, dest: Path) -> None:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=dest.name + ".", suffix=".tmp", dir=str(dest.parent))
    os.close(fd)
    tmp = Path(tmp_path)
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def decisions_path(base_dir: Path, *, symbol: str, date_et: str) -> Path:
    sym = symbol.upper().strip()
    # Keep journal adjacent to market data root but separated by type.
    return Path(base_dir) / "decisions" / f"symbol={sym}" / f"date_et={date_et}" / "data.parquet"


def append_decision(record: DecisionRecord, base_dir: Path = JOURNAL_BASE_DEFAULT) -> Path:
    p = decisions_path(base_dir, symbol=record.symbol, date_et=record.date_et)
    row = record.to_row()
    df_new = pd.DataFrame([row])

    if p.exists():
        df_old = pd.read_parquet(p)
        df = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df = df_new

    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="raise")
    if "decision_id" in df.columns:
        df = df.drop_duplicates(subset=["decision_id"], keep="last")
    df = df.sort_values(["ts_utc"], ascending=True, kind="mergesort").reset_index(drop=True)

    _atomic_write_parquet(df, p)
    return p


def read_decisions(symbol: str, date_et: str, base_dir: Path = JOURNAL_BASE_DEFAULT) -> pd.DataFrame:
    """
    Read saved decisions for one symbol + one ET date.

    Returns an empty DataFrame if none exist yet.
    """
    p = decisions_path(base_dir, symbol=symbol, date_et=date_et)
    if not p.exists():
        return pd.DataFrame(
            columns=[
                "decision_id",
                "ts_utc",
                "symbol",
                "date_et",
                "timeframe",
                "action",
                "bar_index",
                "phase",
                "setup",
                "confidence",
                "quality",
                "planned_entry",
                "planned_stop",
                "planned_target",
                "pass_reason",
                "notes",
            ]
        )
    df = pd.read_parquet(p)
    if "ts_utc" in df.columns:
        df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    return df.sort_values(["ts_utc"], ascending=True, kind="mergesort").reset_index(drop=True)


def delete_decision(decision_id: str, symbol: str, date_et: str, base_dir: Path = JOURNAL_BASE_DEFAULT) -> Path:
    p = decisions_path(base_dir, symbol=symbol, date_et=date_et)
    if not p.exists():
        return p
    df = pd.read_parquet(p)
    if "decision_id" not in df.columns:
        return p
    df = df[df["decision_id"] != str(decision_id)].copy()
    if "ts_utc" in df.columns:
        df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
        df = df.sort_values(["ts_utc"], ascending=True, kind="mergesort").reset_index(drop=True)
    _atomic_write_parquet(df, p)
    return p

