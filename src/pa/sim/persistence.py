from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pandas as pd

from ..data.ibkr_raw_ingest import RAW_BASE_DEFAULT
from .models import EquitySnapshot, Fill, Order, Position, SimSessionMeta


SIM_JOURNAL_BASE_DEFAULT = RAW_BASE_DEFAULT / "journal" / "sim_sessions"


def session_dir(base_dir: Path, session_id: str) -> Path:
    return Path(base_dir) / f"session_id={session_id}"


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


def write_metadata(meta: SimSessionMeta, base_dir: Path = SIM_JOURNAL_BASE_DEFAULT) -> Path:
    d = session_dir(base_dir, meta.session_id)
    d.mkdir(parents=True, exist_ok=True)
    p = d / "metadata.json"
    payload = {
        "session_id": meta.session_id,
        "symbol": meta.symbol,
        "date_et": meta.date_et,
        "created_at_utc": str(pd.Timestamp(meta.created_at_utc).tz_convert("UTC")),
        "notes": meta.notes,
    }
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p


def append_orders(orders: list[Order], base_dir: Path, session_id: str) -> Path:
    p = session_dir(base_dir, session_id) / "orders.parquet"
    rows = []
    for o in orders:
        rows.append(
            {
                "order_id": o.order_id,
                "symbol": o.symbol,
                "side": str(o.side.value),
                "type": str(o.type.value),
                "qty": int(o.qty),
                "tif": str(o.tif.value),
                "limit_price": o.limit_price,
                "stop_price": o.stop_price,
                "placed_at_utc": _ts(o.placed_at_utc),
                "active_from_utc": _ts(o.active_from_utc),
                "status": str(o.status.value),
                "parent_order_id": o.parent_order_id,
                "oco_group_id": o.oco_group_id,
                "created_at_utc": _ts(o.created_at_utc),
                "updated_at_utc": _ts(o.updated_at_utc),
            }
        )
    df_new = pd.DataFrame(rows)
    return _append_parquet(df_new, p, dedupe_cols=["order_id"])


def append_fills(fills: list[Fill], base_dir: Path, session_id: str) -> Path:
    p = session_dir(base_dir, session_id) / "fills.parquet"
    rows = []
    for f in fills:
        rows.append(
            {
                "fill_id": f.fill_id,
                "order_id": f.order_id,
                "symbol": f.symbol,
                "side": str(f.side.value),
                "qty": int(f.qty),
                "price": float(f.price),
                "ts_utc": _ts(f.ts_utc),
                "created_at_utc": _ts(f.created_at_utc),
            }
        )
    df_new = pd.DataFrame(rows)
    # v1 invariant: one order can only fill once (no partial fills).
    # Use (order_id, ts_utc) as the idempotency key to reduce duplicate-write risk
    # from repeated callback execution.
    return _append_parquet(df_new, p, dedupe_cols=["order_id", "ts_utc"], sort_cols=["ts_utc"])


def write_position(pos: Position, base_dir: Path, session_id: str) -> Path:
    p = session_dir(base_dir, session_id) / "positions.parquet"
    df = pd.DataFrame(
        [
            {
                "symbol": pos.symbol,
                "side": str(pos.side.value),
                "qty": int(pos.qty),
                "avg_entry": pos.avg_entry,
                "realized_pnl": float(pos.realized_pnl),
            }
        ]
    )
    _atomic_write_parquet(df, p)
    return p


def append_equity(snaps: list[EquitySnapshot], base_dir: Path, session_id: str) -> Path:
    p = session_dir(base_dir, session_id) / "equity.parquet"
    rows = []
    for s in snaps:
        rows.append(
            {
                "ts_utc": _ts(s.ts_utc),
                "symbol": s.symbol,
                "position_side": str(s.position_side.value),
                "position_qty": int(s.position_qty),
                "avg_entry": s.avg_entry,
                "last_price": float(s.last_price),
                "unrealized_pnl": float(s.unrealized_pnl),
                "realized_pnl": float(s.realized_pnl),
                "equity": float(s.equity),
            }
        )
    df_new = pd.DataFrame(rows)
    return _append_parquet(df_new, p, dedupe_cols=["ts_utc", "symbol"], sort_cols=["ts_utc"])


def _ts(ts: pd.Timestamp | None) -> pd.Timestamp | None:
    if ts is None:
        return None
    t = pd.Timestamp(ts)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def _append_parquet(df_new: pd.DataFrame, p: Path, *, dedupe_cols: list[str], sort_cols: list[str] | None = None) -> Path:
    p = Path(p)
    if p.exists():
        df_old = pd.read_parquet(p)
        df = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df = df_new

    for c in df.columns:
        if c.endswith("_utc") or c == "ts_utc":
            df[c] = pd.to_datetime(df[c], utc=True, errors="coerce")

    df = df.drop_duplicates(subset=dedupe_cols, keep="last")
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=True, kind="mergesort").reset_index(drop=True)
    _atomic_write_parquet(df, p)
    return p

