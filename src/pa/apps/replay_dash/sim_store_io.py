from __future__ import annotations

import pandas as pd

from ...sim.engine import SimEngine
from ...sim.models import Order, OrderSide, OrderStatus, OrderType, Position, PositionSide, SimSessionMeta


def _ts(ts: pd.Timestamp | None) -> str | None:
    if ts is None:
        return None
    t = pd.Timestamp(ts)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    return t.isoformat()


def _ts_from(s: str | None) -> pd.Timestamp | None:
    if not s:
        return None
    return pd.Timestamp(s).tz_convert("UTC")


def _order_to_dict(o: Order) -> dict:
    return {
        "order_id": o.order_id,
        "symbol": o.symbol,
        "side": str(o.side.value),
        "type": str(o.type.value),
        "qty": int(o.qty),
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


def _order_from_dict(d: dict) -> Order:
    o = Order(
        order_id=str(d["order_id"]),
        symbol=str(d["symbol"]),
        side=OrderSide(str(d["side"])),
        type=OrderType(str(d["type"])),
        qty=int(d["qty"]),
        limit_price=d.get("limit_price", None),
        stop_price=d.get("stop_price", None),
        placed_at_utc=_ts_from(d.get("placed_at_utc")),
        active_from_utc=_ts_from(d.get("active_from_utc")),
        status=OrderStatus(str(d.get("status", OrderStatus.PENDING.value))),
        parent_order_id=d.get("parent_order_id", None),
        oco_group_id=d.get("oco_group_id", None),
    )
    if d.get("created_at_utc"):
        o.created_at_utc = _ts_from(d.get("created_at_utc")) or o.created_at_utc
    if d.get("updated_at_utc"):
        o.updated_at_utc = _ts_from(d.get("updated_at_utc")) or o.updated_at_utc
    return o


def _pos_to_dict(p: Position) -> dict:
    return {
        "symbol": p.symbol,
        "side": str(p.side.value),
        "qty": int(p.qty),
        "avg_entry": p.avg_entry,
        "realized_pnl": float(p.realized_pnl),
    }


def _pos_from_dict(d: dict, symbol: str) -> Position:
    return Position(
        symbol=symbol,
        side=PositionSide(str(d.get("side", PositionSide.FLAT.value))),
        qty=int(d.get("qty", 0)),
        avg_entry=d.get("avg_entry", None),
        realized_pnl=float(d.get("realized_pnl", 0.0)),
    )


def _new_sim_store(symbol: str, date_et: str) -> dict:
    meta = SimSessionMeta.new(symbol, date_et)
    return {
        "session_id": meta.session_id,
        "symbol": meta.symbol,
        "date_et": meta.date_et,
        "starting_equity": 0.0,
        "last_processed_utc": None,
        "last_equity": None,
        "persist_ok": True,
        "persist_err": "",
        "position": _pos_to_dict(Position(symbol=meta.symbol)),
        "orders": [],
        "fills": [],
    }


def _engine_from_store(sim_store: dict) -> SimEngine:
    meta = SimSessionMeta(session_id=str(sim_store["session_id"]), symbol=str(sim_store["symbol"]), date_et=str(sim_store["date_et"]))
    eng = SimEngine(meta, starting_equity=float(sim_store.get("starting_equity", 0.0)))
    eng.state.last_processed_utc = _ts_from(sim_store.get("last_processed_utc"))
    eng.state.position = _pos_from_dict(sim_store.get("position", {}), meta.symbol)
    orders = {}
    for od in sim_store.get("orders", []) or []:
        o = _order_from_dict(od)
        orders[o.order_id] = o
    eng.state.orders = orders
    return eng


def _store_from_engine(eng: SimEngine) -> dict:
    return {
        "session_id": eng.state.meta.session_id,
        "symbol": eng.state.meta.symbol,
        "date_et": eng.state.meta.date_et,
        "starting_equity": float(eng.starting_equity),
        "last_processed_utc": _ts(eng.state.last_processed_utc),
        "last_equity": None,
        "persist_ok": True,
        "persist_err": "",
        "position": _pos_to_dict(eng.state.position),
        "orders": [_order_to_dict(o) for o in eng.state.orders.values()],
        "fills": [],
    }

