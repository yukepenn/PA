from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class TradeEpisode:
    side: str  # "LONG" or "SHORT"
    entry_ts_utc: pd.Timestamp
    exit_ts_utc: pd.Timestamp | None
    entry_px: float  # authoritative VWAP of fills that OPEN the episode
    exit_px: float | None  # authoritative VWAP of fills that CLOSE the episode (last flatting cluster)
    entry_order_id: str | None  # bracket parent entry order id captured at open (if available)
    exit_order_id: str | None


def _ts_utc(ts) -> pd.Timestamp | None:
    try:
        t = pd.Timestamp(ts)
        return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    except Exception:
        return None


def _signed_qty_delta(side: str, qty: int) -> int:
    s = str(side or "").upper()
    q = int(qty or 0)
    if s in ("BUY", "BUY_TO_COVER"):
        return +q
    if s in ("SELL", "SELL_SHORT"):
        return -q
    return 0


def planned_bracket_levels_at_entry(sim_store: dict | None, *, entry_order_id: str | None) -> tuple[float | None, float | None]:
    """
    Planned stop/target frozen from SIM_STORE.orders by bracket linkage (planned RR at placement).
    """
    if not sim_store or not entry_order_id:
        return None, None

    stop_px = None
    tgt_px = None
    for o in sim_store.get("orders", []) or []:
        try:
            if str(o.get("parent_order_id") or "") != str(entry_order_id):
                continue
            typ = str(o.get("type", ""))
            if typ == "STOP" and o.get("stop_price") is not None and stop_px is None:
                stop_px = float(o.get("stop_price"))
            if typ == "LIMIT" and o.get("limit_price") is not None and tgt_px is None:
                tgt_px = float(o.get("limit_price"))
        except Exception:
            continue

    return stop_px, tgt_px


def derive_trade_episodes(sim_store: dict | None, *, visible_end_utc: pd.Timestamp | None = None) -> tuple[TradeEpisode | None, list[TradeEpisode]]:
    """
    Pure derivation from SIM_STORE.fills.

    IMPORTANT:
    - Entry/exit prices MUST be authoritative VWAPs derived from fills (never midpoint / rectangle centers).
    - Closing uses the cluster of fills that flatten to 0 (handles partial exits + scale-ins correctly).
    """

    if not sim_store:
        return None, []

    fills = list(sim_store.get("fills", []) or [])
    if not fills:
        return None, []

    def _sort_key(f):
        t = _ts_utc(f.get("ts_utc"))
        return (t if t is not None else pd.Timestamp.min.tz_localize("UTC"), str(f.get("fill_id", "") or ""))

    fills2 = sorted(fills, key=_sort_key)

    pos = 0
    episodes: list[TradeEpisode] = []

    # Open episode accumulator
    side: str | None = None
    entry_oid: str | None = None
    entry_ts: pd.Timestamp | None = None

    entry_notional = 0.0
    entry_qty = 0

    # Closing accumulator (flatten cluster)
    closing = False
    exit_notional = 0.0
    exit_qty = 0
    exit_ts: pd.Timestamp | None = None
    exit_oid: str | None = None

    def _reset_open():
        nonlocal side, entry_oid, entry_ts, entry_notional, entry_qty
        side = None
        entry_oid = None
        entry_ts = None
        entry_notional = 0.0
        entry_qty = 0

    def _reset_close():
        nonlocal closing, exit_notional, exit_qty, exit_ts, exit_oid
        closing = False
        exit_notional = 0.0
        exit_qty = 0
        exit_ts = None
        exit_oid = None

    for f in fills2:
        t = _ts_utc(f.get("ts_utc"))
        if t is None:
            continue
        try:
            px = float(f.get("price"))
            q = int(f.get("qty"))
            sd = str(f.get("side", ""))
        except Exception:
            continue

        d = _signed_qty_delta(sd, q)
        if d == 0:
            continue

        prev = pos
        pos = pos + d

        # Detect flip / unwind patterns:
        # - Flatten to 0: close episode with VWAP of closing fills.
        # - Flip across 0 in one fill: treat as close-then-open (close first leg at px/qty that closes).

        # Start opening a new episode when flat -> non-flat
        if prev == 0 and pos != 0:
            side = "LONG" if pos > 0 else "SHORT"
            entry_ts = t
            entry_oid = str(f.get("order_id")) if f.get("order_id") else None
            entry_notional = abs(px) * abs(q)
            entry_qty = abs(q)
            continue

        # Accumulate average entry while increasing exposure in same direction (scale-in / partial adds)
        if prev != 0 and abs(pos) > abs(prev) and side is not None:
            same_dir = (prev > 0 and pos > 0) or (prev < 0 and pos < 0)
            if same_dir:
                entry_notional += abs(px) * abs(q)
                entry_qty += abs(q)
                continue

        # Begin closing path (partial exit or full exit); accumulate VWAP until flat.
        if prev != 0 and abs(pos) < abs(prev):
            closing = True
            exit_notional += abs(px) * abs(q)
            exit_qty += abs(q)
            exit_ts = t
            exit_oid = str(f.get("order_id")) if f.get("order_id") else exit_oid

            if pos == 0 and entry_ts is not None and side is not None and exit_ts is not None:
                entry_px = float(entry_notional / entry_qty) if entry_qty > 0 else float(px)
                exit_px = float(exit_notional / exit_qty) if exit_qty > 0 else float(px)
                episodes.append(
                    TradeEpisode(
                        side=side,
                        entry_ts_utc=entry_ts,
                        exit_ts_utc=exit_ts,
                        entry_px=entry_px,
                        exit_px=exit_px,
                        entry_order_id=entry_oid,
                        exit_order_id=exit_oid,
                    )
                )
                _reset_open()
                _reset_close()
            continue

        # If we ended flat due to a flip in one shot (pos crosses 0), handle conservatively:
        # This path is rare in v1 (engine discourages flip-in-one-step), but keep stable behavior.
        if prev != 0 and pos != 0 and (prev > 0) != (pos > 0):
            # Close previous episode at this fill price for the closing qty portion (approximation)
            if entry_ts is not None and side is not None:
                entry_px = float(entry_notional / entry_qty) if entry_qty > 0 else float(px)
                episodes.append(
                    TradeEpisode(
                        side=side,
                        entry_ts_utc=entry_ts,
                        exit_ts_utc=t,
                        entry_px=entry_px,
                        exit_px=float(px),
                        entry_order_id=entry_oid,
                        exit_order_id=str(f.get("order_id")) if f.get("order_id") else None,
                    )
                )
            # Start new episode from remainder (best-effort)
            _reset_open()
            side = "LONG" if pos > 0 else "SHORT"
            entry_ts = t
            entry_oid = str(f.get("order_id")) if f.get("order_id") else None
            entry_notional = abs(px) * abs(q)
            entry_qty = abs(q)
            continue

    open_ep: TradeEpisode | None = None
    if pos != 0 and entry_ts is not None and side is not None:
        entry_px = float(entry_notional / entry_qty) if entry_qty > 0 else float(sim_store.get("position", {}).get("avg_entry") or 0.0)
        ve = visible_end_utc
        ve = ve.tz_localize("UTC") if (ve is not None and ve.tzinfo is None) else ve
        open_ep = TradeEpisode(
            side=side,
            entry_ts_utc=entry_ts,
            exit_ts_utc=ve,
            entry_px=entry_px,
            exit_px=None,
            entry_order_id=entry_oid,
            exit_order_id=None,
        )

    return open_ep, episodes
