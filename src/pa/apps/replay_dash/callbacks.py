from __future__ import annotations

import json
import os
from uuid import uuid4

import pandas as pd
from dash import ALL, Dash, Input, Output, State, callback_context, html, no_update

from .ids import IDS
from .chart import ChartFlags, add_draft_overlays, add_hover_overlay, add_sim_overlays, apply_session_viewport, build_figure, empty_figure
from .interaction import click_price_from_plotly, snap_price, validate_draft
from .order_interaction import click_modes_for_order_type, draft_ticket_summary, mode_help_text
from .order_hints import ticket_context_hints
from ...data.load_replay_day import ReplayDayRequest, load_replay_day_1min
from ...data.resample_bars import resample_1min_to_5min
from ...journal.io import append_decision, delete_decision, read_decisions
from ...journal.schemas import DecisionRecord
from ...replay.engine import ReplayEngine
from ...replay.models import Action, ReplayState
from ...sim.engine import SimEngine, activation_from_5m_bar_close
from ...sim.models import BracketSpec, Order, OrderSide, OrderStatus, OrderType, Position, PositionSide, SimSessionMeta
from ...sim.persistence import SIM_JOURNAL_BASE_DEFAULT, append_equity, append_fills, append_orders, write_metadata, write_position


def _clamp_index(i: int, max_i: int) -> int:
    if max_i < 0:
        return -1
    return max(0, min(int(i), int(max_i)))


def _parse_plotly_axis_ranges(relayout: dict) -> tuple[object | None, object | None, object | None, object | None]:
    """
    Plotly may emit either xaxis.range[0]/[1] or a single xaxis.range list — handle both.
    """

    x0 = relayout.get("xaxis.range[0]")
    x1 = relayout.get("xaxis.range[1]")
    xr = relayout.get("xaxis.range")
    if isinstance(xr, (list, tuple)) and len(xr) >= 2:
        if x0 is None:
            x0 = xr[0]
        if x1 is None:
            x1 = xr[1]

    y0 = relayout.get("yaxis.range[0]")
    y1 = relayout.get("yaxis.range[1]")
    yr = relayout.get("yaxis.range")
    if isinstance(yr, (list, tuple)) and len(yr) >= 2:
        if y0 is None:
            y0 = yr[0]
        if y1 is None:
            y1 = yr[1]

    return x0, x1, y0, y1


def _bar_ts_label(ts_utc: pd.Timestamp) -> str:
    ts = pd.Timestamp(ts_utc)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    ts_et = ts.tz_convert("America/New_York")
    return f"{ts_et.strftime('%Y-%m-%d %H:%M')} ET  ({ts.strftime('%H:%M')} UTC)"


def _render_status(msg: str, *, ok: bool | None = None) -> html.Div:
    color = "#475569"
    if ok is True:
        color = "#16a34a"
    elif ok is False:
        color = "#dc2626"
    return html.Div(msg, style={"fontSize": "12px", "color": color})


def _render_decisions_list(symbol: str, date_et: str) -> html.Div:
    df = read_decisions(symbol=symbol, date_et=date_et)
    if df.empty:
        return html.Div("No saved decisions yet.", style={"fontSize": "12px", "color": "#475569"})

    df = df.sort_values("ts_utc", ascending=False, kind="mergesort").head(10)
    items = []
    for _, r in df.iterrows():
        ts = r.get("ts_utc")
        ts_s = _bar_ts_label(ts) if pd.notna(ts) else "n/a"
        action = str(r.get("action", ""))
        phase = str(r.get("phase", "before") or "before")
        setup = str(r.get("setup", "") or "")
        bar_i = int(r.get("bar_index", -1)) if pd.notna(r.get("bar_index", None)) else -1
        decision_id = str(r.get("decision_id", "") or "")
        notes = str(r.get("notes", "") or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if len(notes) > 120:
            notes = notes[:120] + "…"

        items.append(
            html.Div(
                style={
                    "padding": "8px",
                    "border": "1px solid rgba(2,6,23,0.10)",
                    "borderRadius": "10px",
                    "marginBottom": "8px",
                    "background": "#ffffff",
                },
                children=[
                    html.Div(
                        style={"display": "flex", "justifyContent": "space-between", "gap": "8px"},
                        children=[
                            html.Div(f"{action} · {phase} · idx {bar_i}", style={"fontSize": "12px", "fontWeight": 700}),
                            html.Button(
                                "Delete",
                                id=IDS.del_decision(decision_id),
                                n_clicks=0,
                                style={
                                    "fontSize": "11px",
                                    "padding": "4px 8px",
                                    "borderRadius": "8px",
                                    "border": "1px solid rgba(2,6,23,0.10)",
                                    "background": "#ffffff",
                                    "cursor": "pointer",
                                },
                            )
                            if decision_id
                            else html.Span(),
                        ],
                    ),
                    html.Div(ts_s, style={"fontSize": "11px", "color": "#475569", "marginTop": "2px"}),
                    html.Div(f"Setup: {setup}" if setup else "Setup: —", style={"fontSize": "11px", "color": "#475569", "marginTop": "2px"}),
                    html.Div(notes if notes else "(no notes)", style={"fontSize": "12px", "marginTop": "6px", "whiteSpace": "pre-wrap"}),
                ],
            )
        )
    return html.Div(items)


def _try_persist(fn, *args, **kwargs) -> tuple[bool, str]:
    try:
        fn(*args, **kwargs)
        return True, ""
    except PermissionError as e:
        return False, f"Permission denied: {e}"
    except OSError as e:
        return False, f"OS error: {e}"
    except Exception as e:  # noqa: BLE001
        return False, f"Persist failed: {e}"


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
    # best-effort timestamps
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


def register(app: Dash) -> None:
    debug = os.getenv("PA_DEBUG", "") == "1"

    @app.callback(
        Output(IDS.BARS_STORE, "data"),
        Output(IDS.BARS1_STORE, "data"),
        Output(IDS.META_STORE, "data"),
        Output(IDS.INDEX_STORE, "data"),
        Output(IDS.STATUS_LEFT, "children"),
        Output(IDS.LOADED_STORE, "data"),
        Output(IDS.VIEW_REV_STORE, "data"),
        Output(IDS.VIEW_LOCK_STORE, "data"),
        Output(IDS.SIM_STORE, "data"),
        Output(IDS.INP_SETUP, "value"),
        Output(IDS.INP_CONF, "value"),
        Output(IDS.INP_QUALITY, "value"),
        Output(IDS.INP_ENTRY, "value"),
        Output(IDS.INP_STOP, "value"),
        Output(IDS.INP_TARGET, "value"),
        Output(IDS.INP_PASS_REASON, "value"),
        Output(IDS.INP_NOTES, "value"),
        Output(IDS.ACTION_STORE, "data"),
        Output(IDS.STATUS_RIGHT, "children"),
        Input(IDS.BTN_LOAD, "n_clicks"),
        State(IDS.SYMBOL, "value"),
        State(IDS.DATE_ET, "date"),
        prevent_initial_call=True,
    )
    def on_load(n_clicks: int, symbol: str, date_et: str):
        if debug:
            print(f"[on_load] n={n_clicks} symbol={symbol} date_et={date_et}", flush=True)
        if not symbol or not date_et:
            return (
                no_update,
                no_update,
                no_update,
                no_update,
                _render_status("Pick a symbol and date.", ok=False),
                False,
                no_update,
                False,
                no_update,
                "",
                None,
                None,
                None,
                None,
                None,
                "",
                "",
                Action.PASS.value,
                _render_status("", ok=None),
            )

        try:
            df1 = load_replay_day_1min(ReplayDayRequest(symbol=symbol, date_et=date_et))
            df5 = resample_1min_to_5min(df1)
            bars = df5.to_json(orient="split", date_format="iso")
            bars1 = df1.to_json(orient="split", date_format="iso")
            meta = {"symbol": symbol.upper(), "date_et": date_et, "bar_count": int(len(df5))}
            idx0 = 0 if len(df5) > 0 else -1
            view_rev = int(n_clicks or 0)  # autoscale on load
            sim_store = _new_sim_store(meta["symbol"], meta["date_et"])
            ok, err = _try_persist(
                write_metadata,
                SimSessionMeta(session_id=sim_store["session_id"], symbol=sim_store["symbol"], date_et=sim_store["date_et"]),
                base_dir=SIM_JOURNAL_BASE_DEFAULT,
            )
            sim_store["persist_ok"] = bool(ok)
            sim_store["persist_err"] = str(err or "")
            return (
                bars,
                bars1,
                meta,
                idx0,
                _render_status(f"Loaded {len(df5)} bars (5min).", ok=True),
                True,
                view_rev,
                False,
                sim_store,
                "",
                None,
                None,
                None,
                None,
                None,
                "",
                "",
                Action.PASS.value,
                _render_status(
                    ("Loaded new day. Decision fields cleared." if ok else f"Loaded day. Sim persistence disabled: {err}"),
                    ok=None if ok else False,
                ),
            )
        except Exception as e:  # noqa: BLE001
            if debug:
                print(f"[on_load] failed: {e!r}", flush=True)
            return (
                no_update,
                no_update,
                no_update,
                no_update,
                _render_status(f"Load failed: {e}", ok=False),
                False,
                no_update,
                no_update,
                no_update,
                "",
                None,
                None,
                None,
                None,
                None,
                "",
                "",
                Action.PASS.value,
                _render_status("", ok=None),
            )

    @app.callback(
        Output(IDS.BTN_RESET, "disabled"),
        Output(IDS.BTN_PREV1, "disabled"),
        Output(IDS.BTN_PREV5, "disabled"),
        Output(IDS.BTN_NEXT1, "disabled"),
        Output(IDS.BTN_NEXT5, "disabled"),
        Output(IDS.BTN_ALL, "disabled"),
        Output(IDS.BTN_SAVE, "disabled"),
        Output(IDS.BTN_PLAY, "disabled"),
        Input(IDS.LOADED_STORE, "data"),
    )
    def toggle_buttons(loaded: bool):
        disabled = not bool(loaded)
        return disabled, disabled, disabled, disabled, disabled, disabled, disabled, disabled

    @app.callback(
        Output(IDS.INTERACT_STORE, "data", allow_duplicate=True),
        Input(IDS.SIM_CLICK_MODE, "value"),
        State(IDS.INTERACT_STORE, "data"),
        prevent_initial_call=True,
    )
    def on_click_mode(mode, st):
        st = dict(st or {})
        st["click_mode"] = str(mode or "entry")
        return st

    @app.callback(
        Output(IDS.SIM_CLICK_MODE, "options"),
        Output(IDS.SIM_CLICK_MODE, "value"),
        Input(IDS.SIM_ORDER_TYPE, "value"),
        State(IDS.SIM_CLICK_MODE, "value"),
        prevent_initial_call=False,
    )
    def click_mode_options(order_type, cur):
        modes = click_modes_for_order_type(str(order_type or "MARKET"))
        opts = [{"label": m.label, "value": m.value} for m in modes]
        allowed = {m.value for m in modes}
        v = cur if cur in allowed else (modes[0].value if modes else "stop")
        return opts, v

    @app.callback(
        Output(IDS.SIM_CHART_TOOLS_HINT, "children"),
        Input(IDS.SIM_ORDER_TYPE, "value"),
        Input(IDS.SIM_CLICK_MODE, "value"),
        prevent_initial_call=False,
    )
    def render_chart_tools_hint(order_type, click_mode):
        return mode_help_text(order_type=str(order_type or "MARKET"), click_mode=str(click_mode or ""))

    @app.callback(
        Output(IDS.HOVER_READOUT, "children"),
        Output(IDS.INTERACT_STORE, "data", allow_duplicate=True),
        Input(IDS.CHART, "hoverData"),
        State(IDS.INTERACT_STORE, "data"),
        prevent_initial_call="initial_duplicate",
    )
    def on_hover(hover, st):
        st = dict(st or {})
        if not hover or not hover.get("points"):
            return "Hover: —", st
        p = hover["points"][0]
        x = p.get("x")
        y = p.get("y")
        if x is None:
            return "Hover: —", st
        st["hover_time_utc"] = str(x)
        if y is not None:
            try:
                st["hover_price"] = float(y)
            except Exception:
                pass
        price_s = f"{float(st.get('hover_price')):.2f}" if st.get("hover_price") is not None else "—"
        return html.Div([html.Span("Hover "), html.Span(price_s, style={"fontWeight": 800}), html.Span(f" @ {x}")]), st

    @app.callback(
        Output(IDS.SIM_LIMIT, "value", allow_duplicate=True),
        Output(IDS.SIM_STOP, "value", allow_duplicate=True),
        Output(IDS.SIM_STOP_LOSS, "value", allow_duplicate=True),
        Output(IDS.SIM_TAKE_PROFIT, "value", allow_duplicate=True),
        Input(IDS.CHART, "clickData"),
        State(IDS.SIM_CLICK_MODE, "value"),
        State(IDS.SIM_ORDER_TYPE, "value"),
        State(IDS.SIM_LIMIT, "value"),
        State(IDS.SIM_STOP, "value"),
        State(IDS.SIM_STOP_LOSS, "value"),
        State(IDS.SIM_TAKE_PROFIT, "value"),
        prevent_initial_call=True,
    )
    def on_chart_click(click, mode, otype, limit_v, stop_v, sl_v, tp_v):
        px = click_price_from_plotly(click)
        if px is None:
            return no_update, no_update, no_update, no_update
        px = snap_price(px, tick=0.01)
        mode = str(mode or "entry")
        ot = str(otype or "MARKET").upper()

        if mode == "entry":
            if ot in ("LIMIT", "STOP_LIMIT"):
                limit_v = px
            if ot in ("STOP", "STOP_LIMIT"):
                stop_v = px
            return limit_v, stop_v, no_update, no_update
        if mode == "entry_stop":
            return no_update, px, no_update, no_update
        if mode == "entry_limit":
            return px, no_update, no_update, no_update
        if mode == "stop":
            return no_update, no_update, px, no_update
        if mode == "target":
            return no_update, no_update, no_update, px
        return no_update, no_update, no_update, no_update

    @app.callback(
        Output(IDS.SIM_LIMIT, "value", allow_duplicate=True),
        Output(IDS.SIM_STOP, "value", allow_duplicate=True),
        Output(IDS.SIM_STOP_LOSS, "value", allow_duplicate=True),
        Output(IDS.SIM_TAKE_PROFIT, "value", allow_duplicate=True),
        Input(IDS.CHART, "relayoutData"),
        State(IDS.CHART, "figure"),
        State(IDS.SIM_ORDER_TYPE, "value"),
        State(IDS.SIM_LIMIT, "value"),
        State(IDS.SIM_STOP, "value"),
        State(IDS.SIM_STOP_LOSS, "value"),
        State(IDS.SIM_TAKE_PROFIT, "value"),
        prevent_initial_call=True,
    )
    def on_draft_drag(relayout, fig_json, otype, limit_v, stop_v, sl_v, tp_v):
        """
        Stage 1 dragline: dragging draft preview shapes updates the order-entry form.

        This is UI-only: it does NOT place or modify real sim orders.
        """

        if not relayout or not fig_json:
            return no_update, no_update, no_update, no_update

        # Look for shape y updates like: shapes[12].y0 / shapes[12].y1
        shape_updates: dict[int, float] = {}
        for k, v in (relayout or {}).items():
            if not isinstance(k, str):
                continue
            if not k.startswith("shapes[") or not k.endswith("].y0"):
                continue
            try:
                i = int(k.split("[", 1)[1].split("]", 1)[0])
                y = float(v)
            except Exception:
                continue
            shape_updates[i] = y

        if not shape_updates:
            return no_update, no_update, no_update, no_update

        shapes = ((fig_json.get("layout") or {}).get("shapes")) or []
        if not isinstance(shapes, list) or not shapes:
            return no_update, no_update, no_update, no_update

        def _snap(x: float) -> float:
            return snap_price(float(x), tick=0.01)

        ot = str(otype or "MARKET").upper()
        out_limit, out_stop, out_sl, out_tp = limit_v, stop_v, sl_v, tp_v

        for i, y in shape_updates.items():
            if i < 0 or i >= len(shapes):
                continue
            sh = shapes[i] or {}
            name = str(sh.get("name", "") or "")
            y2 = _snap(y)

            # Map by explicit shape name (prevents STOP_LIMIT collisions).
            if name == "draft:entry":
                if ot == "LIMIT":
                    out_limit = y2
                elif ot == "STOP":
                    out_stop = y2
                # MARKET has no entry; STOP_LIMIT uses explicit legs.
            elif name == "draft:entry_limit":
                if ot == "STOP_LIMIT":
                    out_limit = y2
            elif name == "draft:entry_stop":
                if ot == "STOP_LIMIT":
                    out_stop = y2
            elif name == "draft:stop_loss":
                out_sl = y2
            elif name == "draft:take_profit":
                out_tp = y2

        return out_limit, out_stop, out_sl, out_tp

    @app.callback(
        Output(IDS.INTERACT_STORE, "data", allow_duplicate=True),
        Output(IDS.SIM_VALIDATION, "children"),
        Output(IDS.BTN_SIM_PLACE, "disabled"),
        Output(IDS.SIM_TICKET_SUMMARY, "children"),
        Input(IDS.SIM_SIDE, "value"),
        Input(IDS.SIM_ORDER_TYPE, "value"),
        Input(IDS.SIM_QTY, "value"),
        Input(IDS.SIM_LIMIT, "value"),
        Input(IDS.SIM_STOP, "value"),
        Input(IDS.SIM_STOP_LOSS, "value"),
        Input(IDS.SIM_TAKE_PROFIT, "value"),
        State(IDS.SIM_STORE, "data"),
        State(IDS.INTERACT_STORE, "data"),
        State(IDS.LOADED_STORE, "data"),
        prevent_initial_call="initial_duplicate",
    )
    def update_draft(side, otype, qty, limit_px, stop_px, sl, tp, sim_store, st, loaded):
        st = dict(st or {})
        if not loaded:
            return st, "", True, ""

        # Policy: one-at-a-time. While a position is open, disable draft construction overlays.
        try:
            pos = (sim_store or {}).get("position") or {}
            if int(pos.get("qty", 0) or 0) != 0:
                st["draft"] = {}
                st["draft_valid"] = False
                st["draft_errors"] = ["Position is open: close/flatten before starting a new draft ticket."]
                msg = html.Div(
                    [
                        html.Div("Draft disabled:", style={"fontWeight": 700, "color": "#dc2626"}),
                        html.Div("• Position is open. Flatten/close before placing a new ticket.", style={"fontSize": "12px"}),
                    ]
                )
                summ = draft_ticket_summary(
                    side=str(side),
                    order_type=str(otype),
                    qty=int(qty) if qty is not None and str(qty) != "" else None,
                    limit_px=None,
                    stop_px=None,
                    stop_loss=None,
                    take_profit=None,
                    mark_price=None,
                )
                return st, msg, True, summ
        except Exception:
            pass
        # snap draft prices
        def _sn(v):
            if v is None or str(v) == "":
                return None
            return snap_price(float(v), tick=0.01)

        limit_v = _sn(limit_px)
        stop_v = _sn(stop_px)
        sl_v = _sn(sl)
        tp_v = _sn(tp)
        mark = None
        if sim_store and sim_store.get("last_equity"):
            mark = float(sim_store["last_equity"].get("last_price", 0.0))

        val = validate_draft(
            side=str(side),
            order_type=str(otype),
            qty=int(qty) if qty is not None and str(qty) != "" else None,
            limit_px=limit_v,
            stop_px=stop_v,
            stop_loss=sl_v,
            take_profit=tp_v,
            mark_price=mark,
        )
        # draft preview lines (UI-only; must be type-aware)
        ot = str(otype or "").upper()
        if ot == "STOP_LIMIT":
            st["draft"] = {"entry_stop": stop_v, "entry_limit": limit_v, "stop_loss": sl_v, "take_profit": tp_v}
        elif ot == "LIMIT":
            st["draft"] = {"entry": limit_v, "stop_loss": sl_v, "take_profit": tp_v}
        elif ot == "STOP":
            st["draft"] = {"entry": stop_v, "stop_loss": sl_v, "take_profit": tp_v}
        elif ot == "MARKET":
            # MARKET has no draft entry line.
            st["draft"] = {"stop_loss": sl_v, "take_profit": tp_v}
        else:
            st["draft"] = {"entry": limit_v, "stop_loss": sl_v, "take_profit": tp_v}
        st["draft_valid"] = bool(val.ok)
        st["draft_errors"] = list(val.errors)
        if val.ok:
            hints = ticket_context_hints(
                side=str(side),
                order_type=str(otype),
                limit_px=limit_v,
                stop_px=stop_v,
                stop_loss=sl_v,
                take_profit=tp_v,
                mark_price=mark,
            )
            msg = html.Div(
                [
                    html.Div("Draft OK. Click chart to fill Entry/Stop/Target.", style={"color": "#16a34a"}),
                    *(
                        [
                            html.Div(style={"height": "8px"}),
                            html.Div("Hints:", style={"fontWeight": 700, "fontSize": "12px", "color": "#475569"}),
                        ]
                        + [html.Div(f"• {h}", style={"fontSize": "12px", "color": "#64748b"}) for h in hints[:6]]
                        if hints
                        else []
                    ),
                ]
            )
        else:
            msg = html.Div([html.Div("Fix:", style={"fontWeight": 700, "color": "#dc2626"})] + [html.Div(f"• {e}") for e in val.errors])
        summ = draft_ticket_summary(
            side=str(side),
            order_type=str(otype),
            qty=int(qty) if qty is not None and str(qty) != "" else None,
            limit_px=limit_v,
            stop_px=stop_v,
            stop_loss=sl_v,
            take_profit=tp_v,
            mark_price=mark,
        )
        return st, msg, (not bool(val.ok)), summ

    @app.callback(
        Output(IDS.SHOW_VOLUME_STORE, "data"),
        Output(IDS.SHOW_DECISION_STORE, "data"),
        Input(IDS.BTN_TOGGLE_VOLUME, "n_clicks"),
        Input(IDS.BTN_TOGGLE_DECISION, "n_clicks"),
        State(IDS.SHOW_VOLUME_STORE, "data"),
        State(IDS.SHOW_DECISION_STORE, "data"),
        prevent_initial_call=True,
    )
    def on_toggle_view(nv, nd, show_vol, show_dec):
        trigger = callback_context.triggered[0]["prop_id"].split(".")[0] if callback_context.triggered else ""
        show_vol = bool(show_vol)
        show_dec = bool(show_dec)
        if trigger == IDS.BTN_TOGGLE_VOLUME:
            show_vol = not show_vol
        elif trigger == IDS.BTN_TOGGLE_DECISION:
            show_dec = not show_dec
        return show_vol, show_dec

    @app.callback(
        Output(IDS.MAIN_GRID, "style"),
        Output(IDS.DECISION_PANEL, "style"),
        Input(IDS.SHOW_DECISION_STORE, "data"),
        State(IDS.MAIN_GRID, "style"),
        State(IDS.DECISION_PANEL, "style"),
        prevent_initial_call=False,
    )
    def apply_decision_visibility(show_decision: bool, grid_style, decision_style):
        show = bool(show_decision)
        grid_style = {"display": "grid", "gap": "12px"}
        if show:
            grid_style["gridTemplateColumns"] = "248px 1fr 296px"
            decision_style = decision_style or {}
            decision_style.pop("display", None)
        else:
            grid_style["gridTemplateColumns"] = "248px 1fr"
            decision_style = {**(decision_style or {}), "display": "none"}
        return grid_style, decision_style

    @app.callback(
        Output(IDS.VIEW_REV_STORE, "data"),
        Output(IDS.VIEW_LOCK_STORE, "data"),
        Output(IDS.VIEWPORT_STORE, "data"),
        Input(IDS.BTN_AUTOSCALE, "n_clicks"),
        State(IDS.VIEW_REV_STORE, "data"),
        prevent_initial_call=True,
    )
    def on_autoscale(n, view_rev):
        view_rev = int(view_rev) if view_rev is not None else 0
        return view_rev + 1, False, {"mode": "auto", "x": None, "y": None}

    @app.callback(
        Output(IDS.VIEW_LOCK_STORE, "data", allow_duplicate=True),
        Input(IDS.CHART, "relayoutData"),
        State(IDS.VIEW_LOCK_STORE, "data"),
        prevent_initial_call=True,
    )
    def on_chart_relayout(relayout, locked):
        """
        If user pans/zooms, lock view so stepping won't keep autoscaling.
        """
        if not relayout:
            return no_update
        keys = set(relayout.keys())
        if any(k.startswith("xaxis.range") or k.startswith("yaxis.range") for k in keys) or "xaxis.autorange" in keys or "yaxis.autorange" in keys:
            return True
        return no_update

    @app.callback(
        Output(IDS.VIEWPORT_STORE, "data", allow_duplicate=True),
        Input(IDS.CHART, "relayoutData"),
        State(IDS.VIEWPORT_STORE, "data"),
        prevent_initial_call=True,
    )
    def on_viewport_capture(relayout, viewport):
        """
        Capture manual viewport ranges so stepping/play can preserve the user's view.
        """
        if not relayout:
            return no_update
        viewport = dict(viewport or {"mode": "auto", "x": None, "y": None})
        keys = set(relayout.keys())

        x0, x1, y0, y1 = _parse_plotly_axis_ranges(relayout)

        explicit_x = x0 is not None and x1 is not None
        explicit_y = y0 is not None and y1 is not None

        changed = False
        if explicit_x:
            viewport["x"] = [str(x0), str(x1)]
            changed = True
        if explicit_y:
            viewport["y"] = [float(y0), float(y1)]
            changed = True

        # Double-click "reset" often emits xaxis.autorange without numeric ranges in the same payload.
        # Never wipe stored x/y here — that produced mode=manual with null ranges (broken).
        # If Plotly sends explicit ranges (same event or follow-up relayout), we capture them above.
        # If we only see autorange, switch to wide_revealed: server applies full RTH session x + y from revealed bars each render.
        if not changed and ("xaxis.autorange" in keys or "yaxis.autorange" in keys):
            viewport["mode"] = "wide_revealed"
            viewport["x"] = None
            viewport["y"] = None
            changed = True

        if changed:
            if explicit_x or explicit_y:
                viewport["mode"] = "manual"
            return viewport
        return no_update

    @app.callback(
        Output(IDS.SHOW_OR_STORE, "data"),
        Input(IDS.BTN_TOGGLE_OR, "n_clicks"),
        State(IDS.SHOW_OR_STORE, "data"),
        prevent_initial_call=True,
    )
    def on_toggle_or(n, show_or):
        return not bool(show_or)

    @app.callback(
        Output(IDS.SPEED_STORE, "data"),
        Output(IDS.PLAY_TIMER, "interval"),
        Input(IDS.SPEED, "value"),
        prevent_initial_call=False,
    )
    def on_speed(speed):
        speed = speed or "1x"
        interval = {"1x": 800, "2x": 400, "5x": 150}.get(speed, 800)
        return speed, interval

    @app.callback(
        Output(IDS.PLAY_STORE, "data"),
        Input(IDS.BTN_PLAY, "n_clicks"),
        State(IDS.PLAY_STORE, "data"),
        State(IDS.LOADED_STORE, "data"),
        prevent_initial_call=True,
    )
    def on_play(n, playing, loaded):
        if not loaded:
            return False
        return not bool(playing)

    @app.callback(
        Output(IDS.PLAY_TIMER, "disabled"),
        Input(IDS.PLAY_STORE, "data"),
        Input(IDS.LOADED_STORE, "data"),
    )
    def on_timer_enable(playing, loaded):
        return (not bool(loaded)) or (not bool(playing))

    @app.callback(
        Output(IDS.INDEX_STORE, "data", allow_duplicate=True),
        Output(IDS.STATUS_LEFT, "children", allow_duplicate=True),
        Input(IDS.PLAY_TIMER, "n_intervals"),
        State(IDS.INDEX_STORE, "data"),
        State(IDS.META_STORE, "data"),
        State(IDS.SPEED_STORE, "data"),
        prevent_initial_call=True,
    )
    def on_tick(n_intervals, idx, meta, speed):
        if not meta:
            return no_update, no_update
        max_i = int(meta.get("bar_count", 0)) - 1
        step = {"1x": 1, "2x": 2, "5x": 5}.get(speed or "1x", 1)
        idx = int(idx) if idx is not None else 0
        idx2 = _clamp_index(idx + step, max_i)
        return idx2, _render_status(f"Playing: {idx2}/{max_i}", ok=None)

    @app.callback(Output(IDS.PHASE_STORE, "data"), Input(IDS.PHASE_TABS, "value"))
    def on_phase(phase):
        return phase or "before"

    @app.callback(
        Output(IDS.SIM_STORE, "data", allow_duplicate=True),
        Output(IDS.SIM_STATUS, "children", allow_duplicate=True),
        Input(IDS.BTN_RESET, "n_clicks"),
        State(IDS.META_STORE, "data"),
        prevent_initial_call=True,
    )
    def sim_reset(n_clicks, meta):
        if not meta:
            return no_update, no_update
        sim_store = _new_sim_store(meta["symbol"], meta["date_et"])
        ok, err = _try_persist(
            write_metadata,
            SimSessionMeta(session_id=sim_store["session_id"], symbol=sim_store["symbol"], date_et=sim_store["date_et"]),
            base_dir=SIM_JOURNAL_BASE_DEFAULT,
        )
        sim_store["persist_ok"] = bool(ok)
        sim_store["persist_err"] = str(err or "")
        msg = "Sim reset for this day." if ok else f"Sim reset, but persistence disabled: {err}"
        return sim_store, _render_status(msg, ok=None if ok else False)

    @app.callback(
        Output(IDS.SIM_STORE, "data", allow_duplicate=True),
        Output(IDS.SIM_STATUS, "children", allow_duplicate=True),
        Input(IDS.INDEX_STORE, "data"),
        State(IDS.BARS_STORE, "data"),
        State(IDS.BARS1_STORE, "data"),
        State(IDS.META_STORE, "data"),
        State(IDS.SIM_STORE, "data"),
        prevent_initial_call=True,
    )
    def sim_advance(idx, bars5_data, bars1_data, meta, sim_store):
        if not bars5_data or not bars1_data or not meta or not sim_store:
            return no_update, no_update

        df5 = pd.read_json(bars5_data, orient="split")
        if df5.empty:
            return no_update, no_update
        idx = _clamp_index(int(idx or 0), len(df5) - 1)
        target_5m_close = pd.Timestamp(df5.iloc[idx]["ts_utc"])
        target_5m_close = target_5m_close.tz_localize("UTC") if target_5m_close.tzinfo is None else target_5m_close.tz_convert("UTC")

        eng = _engine_from_store(sim_store)
        # Safety: sim is monotonic. Allow replay to move backward, but do not roll back sim.
        last = eng.state.last_processed_utc
        if last is not None:
            last_u = pd.Timestamp(last).tz_convert("UTC")
            if target_5m_close < last_u:
                warn = (
                    "Replay moved backward. Sim state is monotonic and will not roll back automatically. "
                    "Use Reset to restart the sim session."
                )
                return no_update, _render_status(warn, ok=False)

        df1 = pd.read_json(bars1_data, orient="split")
        if df1.empty:
            return no_update, no_update
        df1["ts_utc"] = pd.to_datetime(df1["ts_utc"], utc=True, errors="raise")
        df1 = df1.sort_values("ts_utc", ascending=True, kind="mergesort").reset_index(drop=True)

        if last is None:
            start_ts = df1.iloc[0]["ts_utc"]
        else:
            start_ts = pd.Timestamp(last) + pd.Timedelta(minutes=1)

        # Do not process beyond currently visible 5m close.
        df_slice = df1[(df1["ts_utc"] >= start_ts) & (df1["ts_utc"] <= target_5m_close)].copy()
        if df_slice.empty:
            return no_update, no_update

        fills = eng.process_bars(df_slice)

        # Persist (best-effort; do not break replay if disk is not writable).
        session_id = eng.state.meta.session_id
        ok_all = True
        err_last = ""
        if fills:
            ok, err = _try_persist(append_fills, fills, SIM_JOURNAL_BASE_DEFAULT, session_id)
            ok_all = ok_all and ok
            err_last = err_last or err
        # Equity snapshots: engine adds one per processed bar.
        new_snaps = eng.state.equity[-len(df_slice) :]
        ok, err = _try_persist(append_equity, new_snaps, SIM_JOURNAL_BASE_DEFAULT, session_id)
        ok_all = ok_all and ok
        err_last = err_last or err
        ok, err = _try_persist(write_position, eng.state.position, SIM_JOURNAL_BASE_DEFAULT, session_id)
        ok_all = ok_all and ok
        err_last = err_last or err

        sim_store2 = _store_from_engine(eng)
        sim_store2["persist_ok"] = bool(sim_store.get("persist_ok", True) and ok_all)
        sim_store2["persist_err"] = str(err_last or sim_store.get("persist_err", "") or "")

        # Carry forward fills in store for UI + chart overlays (idempotent by fill_id).
        prev_fills = list(sim_store.get("fills", []) or [])
        seen_ids = {str(x.get("fill_id", "")) for x in prev_fills if x.get("fill_id")}
        for f in fills:
            if f.fill_id in seen_ids:
                continue
            prev_fills.append(
                {
                    "fill_id": f.fill_id,
                    "order_id": f.order_id,
                    "side": str(f.side.value),
                    "qty": int(f.qty),
                    "price": float(f.price),
                    "ts_utc": _ts(f.ts_utc),
                }
            )
        # Keep only last N for UI/overlays (avoid huge client payloads).
        sim_store2["fills"] = prev_fills[-200:]

        if eng.state.equity:
            s = eng.state.equity[-1]
            sim_store2["last_equity"] = {
                "ts_utc": _ts(s.ts_utc),
                "last_price": float(s.last_price),
                "unrealized_pnl": float(s.unrealized_pnl),
                "realized_pnl": float(s.realized_pnl),
                "equity": float(s.equity),
                "avg_entry": s.avg_entry,
                "position_qty": int(s.position_qty),
                "position_side": str(s.position_side.value),
            }

        msg = f"Sim advanced to {target_5m_close.strftime('%H:%M')} UTC. New fills: {len(fills)}."
        if not ok_all:
            msg = msg + f" (persistence disabled: {err_last})"
        return sim_store2, _render_status(msg, ok=True if fills else (None if ok_all else False))

    @app.callback(
        Output(IDS.SIM_STORE, "data", allow_duplicate=True),
        Output(IDS.SIM_STATUS, "children", allow_duplicate=True),
        Output(IDS.INTERACT_STORE, "data", allow_duplicate=True),
        Output(IDS.SIM_LIMIT, "value", allow_duplicate=True),
        Output(IDS.SIM_STOP, "value", allow_duplicate=True),
        Output(IDS.SIM_STOP_LOSS, "value", allow_duplicate=True),
        Output(IDS.SIM_TAKE_PROFIT, "value", allow_duplicate=True),
        Input(IDS.BTN_SIM_PLACE, "n_clicks"),
        State(IDS.SIM_SIDE, "value"),
        State(IDS.SIM_ORDER_TYPE, "value"),
        State(IDS.SIM_QTY, "value"),
        State(IDS.SIM_LIMIT, "value"),
        State(IDS.SIM_STOP, "value"),
        State(IDS.SIM_STOP_LOSS, "value"),
        State(IDS.SIM_TAKE_PROFIT, "value"),
        State(IDS.BARS_STORE, "data"),
        State(IDS.META_STORE, "data"),
        State(IDS.INDEX_STORE, "data"),
        State(IDS.SIM_STORE, "data"),
        State(IDS.INTERACT_STORE, "data"),
        prevent_initial_call=True,
    )
    def sim_place(n, side, otype, qty, limit_px, stop_px, sl, tp, bars5_data, meta, idx, sim_store, interact_store):
        if not bars5_data or not meta or not sim_store:
            return no_update, _render_status("Load a day first.", ok=False), no_update, no_update, no_update, no_update, no_update
        df5 = pd.read_json(bars5_data, orient="split")
        if df5.empty:
            return no_update, _render_status("No bars loaded.", ok=False), no_update, no_update, no_update, no_update, no_update
        idx = _clamp_index(int(idx or 0), len(df5) - 1)
        seen_close = pd.Timestamp(df5.iloc[idx]["ts_utc"])
        seen_close = seen_close.tz_localize("UTC") if seen_close.tzinfo is None else seen_close.tz_convert("UTC")
        active_from = activation_from_5m_bar_close(seen_close)

        eng = _engine_from_store(sim_store)
        try:
            side_e = OrderSide(str(side))
            type_e = OrderType(str(otype))
            q = int(qty or 1)
            limit_v = float(limit_px) if limit_px is not None and str(limit_px) != "" else None
            stop_v = float(stop_px) if stop_px is not None and str(stop_px) != "" else None
            sl_v = float(sl) if sl is not None and str(sl) != "" else None
            tp_v = float(tp) if tp is not None and str(tp) != "" else None

            created: list[Order] = []
            if sl_v is not None or tp_v is not None:
                legs = eng.place_bracket_order(
                    entry_side=side_e if side_e in (OrderSide.BUY, OrderSide.SELL_SHORT) else side_e,
                    entry_type=type_e,
                    qty=q,
                    placed_at_utc=seen_close,
                    active_from_utc=active_from,
                    entry_limit=limit_v,
                    entry_stop=stop_v,
                    bracket=BracketSpec(stop_loss=sl_v, take_profit=tp_v),
                )
                created = list(legs.values())
            else:
                o = eng.place_order(
                    side=side_e,
                    type=type_e,
                    qty=q,
                    limit_price=limit_v,
                    stop_price=stop_v,
                    placed_at_utc=seen_close,
                    active_from_utc=active_from,
                )
                created = [o]

            ok, err = _try_persist(append_orders, created, SIM_JOURNAL_BASE_DEFAULT, eng.state.meta.session_id)
            sim_store2 = _store_from_engine(eng)
            sim_store2["persist_ok"] = bool(sim_store.get("persist_ok", True) and ok)
            sim_store2["persist_err"] = str(err or sim_store.get("persist_err", "") or "")
            msg = f"Placed {len(created)} order(s). Active from {active_from.strftime('%H:%M')} UTC."
            if not ok:
                msg = msg + f" (persistence disabled: {err})"
            # Policy: successful place clears the draft ticket (clean lifecycle).
            st2 = dict(interact_store or {})
            st2.pop("draft", None)
            st2["draft"] = {}
            st2["draft_valid"] = False
            st2["draft_errors"] = []
            return sim_store2, _render_status(msg, ok=True if ok else False), st2, None, None, None, None
        except Exception as e:  # noqa: BLE001
            return no_update, _render_status(f"Place failed: {e}", ok=False), no_update, no_update, no_update, no_update, no_update

    @app.callback(
        Output(IDS.SIM_STORE, "data", allow_duplicate=True),
        Output(IDS.SIM_STATUS, "children", allow_duplicate=True),
        Input(IDS.BTN_SIM_CANCEL, "n_clicks"),
        State(IDS.SIM_CANCEL_ORDER_ID, "value"),
        State(IDS.SIM_STORE, "data"),
        prevent_initial_call=True,
    )
    def sim_cancel(n, order_id, sim_store):
        if not sim_store:
            return no_update, no_update
        if not order_id:
            return no_update, _render_status("Select an order to cancel.", ok=False)
        eng = _engine_from_store(sim_store)
        try:
            o = eng.cancel_order(str(order_id))
            ok, err = _try_persist(append_orders, [o], SIM_JOURNAL_BASE_DEFAULT, eng.state.meta.session_id)
            s2 = _store_from_engine(eng)
            s2["persist_ok"] = bool(sim_store.get("persist_ok", True) and ok)
            s2["persist_err"] = str(err or sim_store.get("persist_err", "") or "")
            msg = "Canceled." if ok else f"Canceled (persistence disabled: {err})"
            return s2, _render_status(msg, ok=True if ok else False)
        except Exception as e:  # noqa: BLE001
            return no_update, _render_status(f"Cancel failed: {e}", ok=False)

    @app.callback(
        Output(IDS.SIM_STORE, "data", allow_duplicate=True),
        Output(IDS.SIM_STATUS, "children", allow_duplicate=True),
        Input(IDS.BTN_SIM_FLATTEN, "n_clicks"),
        State(IDS.BARS_STORE, "data"),
        State(IDS.INDEX_STORE, "data"),
        State(IDS.SIM_STORE, "data"),
        prevent_initial_call=True,
    )
    def sim_flatten(n, bars5_data, idx, sim_store):
        if not sim_store or not bars5_data:
            return no_update, no_update
        df5 = pd.read_json(bars5_data, orient="split")
        if df5.empty:
            return no_update, _render_status("No bars loaded.", ok=False)
        idx = _clamp_index(int(idx or 0), len(df5) - 1)
        seen_close = pd.Timestamp(df5.iloc[idx]["ts_utc"])
        seen_close = seen_close.tz_localize("UTC") if seen_close.tzinfo is None else seen_close.tz_convert("UTC")
        active_from = activation_from_5m_bar_close(seen_close)

        eng = _engine_from_store(sim_store)
        try:
            o = eng.flatten(placed_at_utc=seen_close, active_from_utc=active_from)
            if o is None:
                return no_update, _render_status("Already flat.", ok=None)
            ok, err = _try_persist(append_orders, [o], SIM_JOURNAL_BASE_DEFAULT, eng.state.meta.session_id)
            s2 = _store_from_engine(eng)
            s2["persist_ok"] = bool(sim_store.get("persist_ok", True) and ok)
            s2["persist_err"] = str(err or sim_store.get("persist_err", "") or "")
            msg = f"Flatten order placed. Active from {active_from.strftime('%H:%M')} UTC."
            if not ok:
                msg = msg + f" (persistence disabled: {err})"
            return s2, _render_status(msg, ok=True if ok else False)
        except Exception as e:  # noqa: BLE001
            return no_update, _render_status(f"Flatten failed: {e}", ok=False)

    @app.callback(
        Output(IDS.SIM_POS_SUMMARY, "children"),
        Output(IDS.SIM_PNL_SUMMARY, "children"),
        Output(IDS.SIM_SESSION_SUMMARY, "children"),
        Output(IDS.SIM_ACTIVE_ORDERS, "children"),
        Output(IDS.SIM_FILLS, "children"),
        Output(IDS.SIM_CANCEL_ORDER_ID, "options"),
        Input(IDS.SIM_STORE, "data"),
        prevent_initial_call=False,
    )
    def sim_render(sim_store):
        if not sim_store:
            return "No sim session.", "", "", "", "", []
        eng = _engine_from_store(sim_store)
        pos = eng.state.position
        avg_s = f"{pos.avg_entry:.2f}" if pos.avg_entry is not None else "—"
        pos_line = html.Div(
            [
                html.Span(f"{pos.side.value}", style={"fontWeight": 800}),
                html.Span(f"  qty {pos.qty}", style={"marginLeft": "8px"}),
                html.Span(f"  avg {avg_s}", style={"marginLeft": "8px"}),
            ],
            style={"fontSize": "13px"},
        )

        # PnL from last equity snapshot if available (advanced as replay progresses)
        le = sim_store.get("last_equity")
        if le:
            pnl_line = html.Div(
                [
                    html.Span("U ", style={"color": "#64748b"}),
                    html.Span(f"{float(le.get('unrealized_pnl', 0.0)):.2f}", style={"fontWeight": 800}),
                    html.Span("   R ", style={"color": "#64748b", "marginLeft": "10px"}),
                    html.Span(f"{float(le.get('realized_pnl', 0.0)):.2f}", style={"fontWeight": 800}),
                    html.Span("   Eq ", style={"color": "#64748b", "marginLeft": "10px"}),
                    html.Span(f"{float(le.get('equity', 0.0)):.2f}", style={"fontWeight": 800}),
                    html.Span(f"   mark {float(le.get('last_price', 0.0)):.2f}", style={"color": "#64748b", "marginLeft": "10px"}),
                ],
                style={"fontSize": "13px"},
            )
        else:
            pnl_line = html.Div(
                [
                    html.Span("U ", style={"color": "#64748b"}),
                    html.Span("0.00", style={"fontWeight": 800}),
                    html.Span("   R ", style={"color": "#64748b", "marginLeft": "10px"}),
                    html.Span(f"{pos.realized_pnl:.2f}", style={"fontWeight": 800}),
                    html.Span("   Eq ", style={"color": "#64748b", "marginLeft": "10px"}),
                    html.Span(f"{(eng.starting_equity + pos.realized_pnl):.2f}", style={"fontWeight": 800}),
                ],
                style={"fontSize": "13px"},
            )

        persist_ok = bool(sim_store.get("persist_ok", True))
        persist_err = str(sim_store.get("persist_err", "") or "")

        sess = html.Div(
            [
                html.Span(f"Session {str(sim_store.get('session_id',''))[:8]}", style={"fontWeight": 700}),
                html.Span(f" · fills {len(sim_store.get('fills', []) or [])}", style={"marginLeft": "8px", "color": "#64748b"}),
                html.Span(f" · active orders {len([o for o in (sim_store.get('orders', []) or []) if str(o.get('status','')) in ('PENDING','WORKING','TRIGGERED')])}", style={"marginLeft": "8px", "color": "#64748b"}),
                html.Span(" · persisted" if persist_ok else " · persistence disabled", style={"marginLeft": "8px", "color": "#16a34a" if persist_ok else "#dc2626"}),
                html.Span(f" ({persist_err})" if (not persist_ok and persist_err) else "", style={"color": "#dc2626"}),
            ],
            style={"fontSize": "12px"},
        )

        active = [o for o in eng.state.orders.values() if o.status in (OrderStatus.PENDING, OrderStatus.WORKING, OrderStatus.TRIGGERED)]
        active.sort(key=lambda o: str(o.created_at_utc))
        if not active:
            active_div = html.Div("No active orders.", style={"fontSize": "12px", "color": "#475569"})
            cancel_opts = []
        else:
            cancel_opts = [{"label": f"{o.order_id[:8]} · {o.side.value} {o.type.value} x{o.qty} · {o.status.value}", "value": o.order_id} for o in active]
            header = html.Tr(
                [
                    html.Th("id", style={"textAlign": "left", "fontSize": "11px", "color": "#64748b", "fontWeight": 700}),
                    html.Th("side", style={"textAlign": "left", "fontSize": "11px", "color": "#64748b", "fontWeight": 700}),
                    html.Th("type", style={"textAlign": "left", "fontSize": "11px", "color": "#64748b", "fontWeight": 700}),
                    html.Th("qty", style={"textAlign": "right", "fontSize": "11px", "color": "#64748b", "fontWeight": 700}),
                    html.Th("status", style={"textAlign": "left", "fontSize": "11px", "color": "#64748b", "fontWeight": 700}),
                    html.Th("active", style={"textAlign": "left", "fontSize": "11px", "color": "#64748b", "fontWeight": 700}),
                    html.Th("px", style={"textAlign": "left", "fontSize": "11px", "color": "#64748b", "fontWeight": 700}),
                ]
            )
            body = []
            for o in active[:15]:
                af = pd.Timestamp(o.active_from_utc).strftime("%H:%M") + " UTC" if o.active_from_utc is not None else "now"
                px = []
                if o.limit_price is not None:
                    px.append(f"L {float(o.limit_price):.2f}")
                if o.stop_price is not None:
                    px.append(f"S {float(o.stop_price):.2f}")
                px_s = ", ".join(px) if px else "—"
                body.append(
                    html.Tr(
                        [
                            html.Td(o.order_id[:8], style={"fontSize": "12px", "fontFamily": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"}),
                            html.Td(o.side.value, style={"fontSize": "12px"}),
                            html.Td(o.type.value, style={"fontSize": "12px"}),
                            html.Td(str(int(o.qty)), style={"fontSize": "12px", "textAlign": "right"}),
                            html.Td(o.status.value, style={"fontSize": "12px", "fontWeight": 700 if o.status.value in ("WORKING", "TRIGGERED") else 500}),
                            html.Td(af, style={"fontSize": "12px"}),
                            html.Td(px_s, style={"fontSize": "12px"}),
                        ]
                    )
                )
            active_div = html.Table(
                [html.Thead(header), html.Tbody(body)],
                style={"width": "100%", "borderCollapse": "collapse"},
            )

        fills = list(sim_store.get("fills", []) or [])[-10:]
        if not fills:
            fills_div = html.Div("No fills yet.", style={"fontSize": "12px", "color": "#475569"})
        else:
            header = html.Tr(
                [
                    html.Th("time", style={"textAlign": "left", "fontSize": "11px", "color": "#64748b", "fontWeight": 700}),
                    html.Th("side", style={"textAlign": "left", "fontSize": "11px", "color": "#64748b", "fontWeight": 700}),
                    html.Th("qty", style={"textAlign": "right", "fontSize": "11px", "color": "#64748b", "fontWeight": 700}),
                    html.Th("price", style={"textAlign": "right", "fontSize": "11px", "color": "#64748b", "fontWeight": 700}),
                    html.Th("order", style={"textAlign": "left", "fontSize": "11px", "color": "#64748b", "fontWeight": 700}),
                ]
            )
            body = []
            for f in reversed(fills):
                ts = pd.Timestamp(f["ts_utc"]).tz_convert("UTC").strftime("%H:%M") + " UTC" if f.get("ts_utc") else "n/a"
                body.append(
                    html.Tr(
                        [
                            html.Td(ts, style={"fontSize": "12px"}),
                            html.Td(str(f.get("side", "")), style={"fontSize": "12px"}),
                            html.Td(str(int(f.get("qty", 0))), style={"fontSize": "12px", "textAlign": "right"}),
                            html.Td(f"{float(f.get('price', 0.0)):.2f}", style={"fontSize": "12px", "textAlign": "right", "fontFamily": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"}),
                            html.Td(str(f.get("order_id", ""))[:8], style={"fontSize": "12px", "fontFamily": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"}),
                        ]
                    )
                )
            fills_div = html.Table([html.Thead(header), html.Tbody(body)], style={"width": "100%", "borderCollapse": "collapse"})

        return pos_line, pnl_line, sess, active_div, fills_div, cancel_opts

    @app.callback(
        Output(IDS.BTN_SIM_CANCEL, "disabled", allow_duplicate=True),
        Output(IDS.BTN_SIM_FLATTEN, "disabled", allow_duplicate=True),
        Output(IDS.SIM_SELECTED_ORDER, "children"),
        Input(IDS.SIM_CANCEL_ORDER_ID, "value"),
        State(IDS.SIM_STORE, "data"),
        prevent_initial_call=True,
    )
    def sim_buttons(selected_order_id, sim_store):
        if not sim_store:
            return True, True, ""
        eng = _engine_from_store(sim_store)
        can_flatten = eng.state.position.qty != 0
        cancel_disabled = not bool(selected_order_id)
        flatten_disabled = not bool(can_flatten)

        # Selected order details (for confidence / ergonomics)
        detail = ""
        if selected_order_id:
            od = next((o for o in (sim_store.get("orders", []) or []) if o.get("order_id") == selected_order_id), None)
            if od:
                px = []
                if od.get("limit_price") is not None:
                    px.append(f"L {float(od.get('limit_price')):.2f}")
                if od.get("stop_price") is not None:
                    px.append(f"S {float(od.get('stop_price')):.2f}")
                af = od.get("active_from_utc")
                af_s = pd.Timestamp(af).tz_convert("UTC").strftime("%H:%M") + " UTC" if af else "now"
                detail = f"Selected: {str(od.get('side',''))} {str(od.get('type',''))} x{int(od.get('qty',0))} · {str(od.get('status',''))} · active {af_s}" + (
                    f" · {', '.join(px)}" if px else ""
                )
        return cancel_disabled, flatten_disabled, detail

    @app.callback(
        Output(IDS.INDEX_STORE, "data"),
        Output(IDS.STATUS_LEFT, "children"),
        Output(IDS.INP_SETUP, "value", allow_duplicate=True),
        Output(IDS.INP_CONF, "value", allow_duplicate=True),
        Output(IDS.INP_QUALITY, "value", allow_duplicate=True),
        Output(IDS.INP_ENTRY, "value", allow_duplicate=True),
        Output(IDS.INP_STOP, "value", allow_duplicate=True),
        Output(IDS.INP_TARGET, "value", allow_duplicate=True),
        Output(IDS.INP_PASS_REASON, "value", allow_duplicate=True),
        Output(IDS.INP_NOTES, "value", allow_duplicate=True),
        Output(IDS.ACTION_STORE, "data", allow_duplicate=True),
        Output(IDS.VIEW_REV_STORE, "data", allow_duplicate=True),
        Output(IDS.VIEW_LOCK_STORE, "data", allow_duplicate=True),
        Input(IDS.BTN_RESET, "n_clicks"),
        Input(IDS.BTN_PREV1, "n_clicks"),
        Input(IDS.BTN_PREV5, "n_clicks"),
        Input(IDS.BTN_NEXT1, "n_clicks"),
        Input(IDS.BTN_NEXT5, "n_clicks"),
        Input(IDS.BTN_ALL, "n_clicks"),
        State(IDS.INDEX_STORE, "data"),
        State(IDS.META_STORE, "data"),
        State(IDS.VIEW_REV_STORE, "data"),
        State(IDS.VIEW_LOCK_STORE, "data"),
        prevent_initial_call=True,
    )
    def on_step(reset_n, p1, p5, n1, n5, all_n, idx, meta, view_rev, view_lock):
        if not meta:
            return (
                no_update,
                _render_status("Load a day first.", ok=False),
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
            )
        max_i = int(meta.get("bar_count", 0)) - 1
        idx = int(idx) if idx is not None else 0
        view_rev = int(view_rev) if view_rev is not None else 0
        locked = bool(view_lock)

        trigger = callback_context.triggered[0]["prop_id"].split(".")[0] if callback_context.triggered else ""
        if trigger == IDS.BTN_RESET:
            idx = 0 if max_i >= 0 else -1
            # Reset should return to a good reading view.
            return (
                idx,
                _render_status(f"Reset. Index: {idx}/{max_i}", ok=None),
                "",
                None,
                None,
                None,
                None,
                None,
                "",
                "",
                Action.PASS.value,
                view_rev + 1,
                False,
            )
        if trigger == IDS.BTN_PREV1:
            idx = _clamp_index(idx - 1, max_i)
        elif trigger == IDS.BTN_PREV5:
            idx = _clamp_index(idx - 5, max_i)
        elif trigger == IDS.BTN_NEXT1:
            idx = _clamp_index(idx + 1, max_i)
        elif trigger == IDS.BTN_NEXT5:
            idx = _clamp_index(idx + 5, max_i)
        elif trigger == IDS.BTN_ALL:
            idx = max_i

        return (
            idx,
            _render_status(f"Index: {idx}/{max_i}", ok=None),
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            no_update,
            (view_rev + 1 if (not locked and trigger in (IDS.BTN_NEXT1, IDS.BTN_NEXT5, IDS.BTN_ALL, IDS.BTN_PREV1, IDS.BTN_PREV5)) else no_update),
            (False if trigger == IDS.BTN_ALL else no_update),
        )

    @app.callback(
        Output(IDS.REPLAY_INFO, "children"),
        Input(IDS.BARS_STORE, "data"),
        Input(IDS.META_STORE, "data"),
        Input(IDS.INDEX_STORE, "data"),
    )
    def render_replay_info(bars_data, meta, idx):
        if not bars_data or not meta:
            return "No day loaded."
        df = pd.read_json(bars_data, orient="split")
        if df.empty:
            return "No bars loaded."
        idx = int(idx) if idx is not None else 0
        idx = _clamp_index(idx, len(df) - 1)
        cur_ts = pd.Timestamp(df.iloc[idx]["ts_utc"])
        ts_label = _bar_ts_label(cur_ts)
        return html.Div(
            [
                html.Div(f"{meta['symbol']} · {meta['date_et']}", style={"fontWeight": 700}),
                html.Div(f"Current bar close: {ts_label}", style={"marginTop": "4px"}),
                html.Div(f"Progress: {idx + 1} / {len(df)}", style={"marginTop": "2px"}),
            ]
        )

    @app.callback(
        Output(IDS.CHART, "figure"),
        Input(IDS.BARS_STORE, "data"),
        Input(IDS.META_STORE, "data"),
        Input(IDS.INDEX_STORE, "data"),
        Input(IDS.SHOW_VOLUME_STORE, "data"),
        Input(IDS.VIEW_REV_STORE, "data"),
        Input(IDS.SHOW_OR_STORE, "data"),
        Input(IDS.SIM_STORE, "data"),
        Input(IDS.INTERACT_STORE, "data"),
        State(IDS.VIEWPORT_STORE, "data"),
    )
    def render_chart(bars_data, meta, idx, show_volume, view_rev, show_or, sim_store, interact_store, viewport):
        if not bars_data or not meta:
            return empty_figure()
        df = pd.read_json(bars_data, orient="split")
        idx = int(idx) if idx is not None else 0
        idx = _clamp_index(idx, len(df) - 1)
        flags = ChartFlags(show_volume=bool(show_volume), show_or=bool(show_or))
        fig = build_figure(df, symbol=meta["symbol"], date_et=meta["date_et"], idx=idx, flags=flags)

        st = dict(interact_store or {})

        # Clean overlay lifecycle grammar:
        # - draft overlays only when there is no open position and no active working orders
        has_open_pos = False
        has_active_orders = False
        try:
            pos = (sim_store or {}).get("position") or {}
            has_open_pos = int(pos.get("qty", 0) or 0) != 0
            active_status = {"PENDING", "WORKING", "TRIGGERED"}
            has_active_orders = any(str(o.get("status", "")) in active_status for o in (sim_store or {}).get("orders", []) or [])
        except Exception:
            pass

        if not has_open_pos and not has_active_orders:
            # Draft preview overlays (UI-only; not actual sim orders).
            draft = st.get("draft") or {}
            valid = bool(st.get("draft_valid", True))
            fig = add_draft_overlays(fig, draft=draft, valid=valid, active_mode=str(st.get("click_mode") or ""))

        # Hover price marker (UI-only; updates continuously with mouse movement).
        hp = st.get("hover_price", None)
        try:
            hp_f = float(hp) if hp is not None else None
        except Exception:
            hp_f = None
        fig = add_hover_overlay(fig, hover_price=hp_f)

        # Display-only sim overlays, clipped to current visible replay end.
        try:
            visible_end = pd.Timestamp(df.iloc[idx]["ts_utc"])
        except Exception:
            visible_end = None
        fig = add_sim_overlays(fig, sim_store=sim_store, visible_end_utc=visible_end)

        rev = int(view_rev) if view_rev is not None else 0
        # Include a chart style token so browsers don't accidentally reuse an old uirevision state.
        fig.update_layout(uirevision=f"{meta['symbol']}-{meta['date_et']}-{rev}-PA-BW-v1")
        vp = dict(viewport or {})
        mode = str(vp.get("mode", "auto"))

        # Explicit pan/zoom ranges from Plotly (preferred — survives Next1 exactly).
        if mode == "manual":
            xr = vp.get("x")
            yr = vp.get("y")
            if isinstance(xr, list) and len(xr) == 2 and xr[0] and xr[1]:
                fig.update_xaxes(range=[xr[0], xr[1]], row=1, col=1)
                if flags.show_volume:
                    fig.update_xaxes(range=[xr[0], xr[1]], row=2, col=1)
            if isinstance(yr, list) and len(yr) == 2:
                try:
                    fig.update_yaxes(range=[float(yr[0]), float(yr[1])], row=1, col=1)
                except Exception:
                    pass
        else:
            # auto, wide_revealed (double-click autorange), or default: full RTH session on x; y from revealed bars.
            eng = ReplayEngine(bars=df, state=ReplayState(symbol=meta["symbol"], date_et=meta["date_et"], index=int(idx)))
            vis = eng.visible_bars()
            fig = apply_session_viewport(fig, vis, date_et=meta["date_et"], show_volume=flags.show_volume)
        return fig

    @app.callback(
        Output(IDS.ACTION_STORE, "data"),
        Output(IDS.STATUS_RIGHT, "children"),
        Input(IDS.BTN_LONG, "n_clicks"),
        Input(IDS.BTN_SHORT, "n_clicks"),
        Input(IDS.BTN_PASS, "n_clicks"),
        prevent_initial_call=True,
    )
    def select_action(nl, ns, np):
        trigger = callback_context.triggered[0]["prop_id"].split(".")[0] if callback_context.triggered else ""
        if trigger == IDS.BTN_LONG:
            return Action.LONG.value, _render_status("Action: Long", ok=None)
        if trigger == IDS.BTN_SHORT:
            return Action.SHORT.value, _render_status("Action: Short", ok=None)
        return Action.PASS.value, _render_status("Action: Pass", ok=None)

    @app.callback(
        Output(IDS.STATUS_RIGHT, "children", allow_duplicate=True),
        Output(IDS.DECISIONS_LIST, "children", allow_duplicate=True),
        Input(IDS.BTN_SAVE, "n_clicks"),
        State(IDS.BARS_STORE, "data"),
        State(IDS.META_STORE, "data"),
        State(IDS.INDEX_STORE, "data"),
        State(IDS.ACTION_STORE, "data"),
        State(IDS.INP_SETUP, "value"),
        State(IDS.PHASE_STORE, "data"),
        State(IDS.INP_CONF, "value"),
        State(IDS.INP_QUALITY, "value"),
        State(IDS.INP_ENTRY, "value"),
        State(IDS.INP_STOP, "value"),
        State(IDS.INP_TARGET, "value"),
        State(IDS.INP_PASS_REASON, "value"),
        State(IDS.INP_NOTES, "value"),
        prevent_initial_call=True,
    )
    def save_decision(n_clicks, bars_data, meta, idx, action, setup, phase, conf, quality, entry, stop, target, pass_reason, notes):
        if not bars_data or not meta:
            return _render_status("Load a day first.", ok=False), no_update
        df = pd.read_json(bars_data, orient="split")
        if df.empty:
            return _render_status("No bars loaded.", ok=False), no_update
        idx = _clamp_index(int(idx or 0), len(df) - 1)
        row = df.iloc[idx]
        ts_utc = pd.Timestamp(row["ts_utc"])
        ts_utc = ts_utc.tz_localize("UTC") if ts_utc.tzinfo is None else ts_utc.tz_convert("UTC")

        rec = DecisionRecord(
            decision_id=str(uuid4()),
            ts_utc=ts_utc,
            symbol=meta["symbol"],
            date_et=meta["date_et"],
            timeframe="5min",
            action=Action(action),
            bar_index=idx,
            phase=str(phase or "before"),
            setup=str(setup or "").strip(),
            confidence=int(conf) if conf is not None and str(conf) != "" else None,
            quality=int(quality) if quality is not None and str(quality) != "" else None,
            planned_entry=float(entry) if entry is not None and str(entry) != "" else None,
            planned_stop=float(stop) if stop is not None and str(stop) != "" else None,
            planned_target=float(target) if target is not None and str(target) != "" else None,
            pass_reason=str(pass_reason or "").strip(),
            notes=str(notes or "").strip(),
        )
        try:
            append_decision(rec)
            return _render_status(f"Saved decision at idx={idx}.", ok=True), _render_decisions_list(meta["symbol"], meta["date_et"])
        except Exception as e:  # noqa: BLE001
            return _render_status(f"Save failed: {e}", ok=False), no_update

    @app.callback(
        Output(IDS.STATUS_RIGHT, "children", allow_duplicate=True),
        Output(IDS.DECISIONS_LIST, "children", allow_duplicate=True),
        Input({"type": "del_decision", "id": ALL}, "n_clicks"),
        State(IDS.META_STORE, "data"),
        prevent_initial_call=True,
    )
    def on_delete_decision(n_clicks_list, meta):
        if not meta:
            return no_update, no_update
        if not callback_context.triggered:
            return no_update, no_update
        trig = callback_context.triggered[0]["prop_id"].split(".")[0]
        try:
            tid = json.loads(trig)
            decision_id = str(tid.get("id", ""))
        except Exception:
            decision_id = ""
        if not decision_id:
            return no_update, no_update
        try:
            delete_decision(decision_id, symbol=meta["symbol"], date_et=meta["date_et"])
            return _render_status("Deleted.", ok=True), _render_decisions_list(meta["symbol"], meta["date_et"])
        except Exception as e:  # noqa: BLE001
            return _render_status(f"Delete failed: {e}", ok=False), no_update

    @app.callback(Output(IDS.DECISIONS_LIST, "children"), Input(IDS.META_STORE, "data"))
    def refresh_decisions(meta):
        if not meta:
            return html.Div("Load a day to view decisions.", style={"fontSize": "12px", "color": "#475569"})
        return _render_decisions_list(meta["symbol"], meta["date_et"])

    @app.callback(
        Output(IDS.INDEX_STORE, "data", allow_duplicate=True),
        Output(IDS.PLAY_STORE, "data", allow_duplicate=True),
        Output(IDS.VIEW_REV_STORE, "data", allow_duplicate=True),
        Output(IDS.SHOW_VOLUME_STORE, "data", allow_duplicate=True),
        Output(IDS.SHOW_DECISION_STORE, "data", allow_duplicate=True),
        Output(IDS.ACTION_STORE, "data", allow_duplicate=True),
        Output(IDS.STATUS_LEFT, "children", allow_duplicate=True),
        Input(IDS.KEY_EVENT, "value"),
        State(IDS.LOADED_STORE, "data"),
        State(IDS.INDEX_STORE, "data"),
        State(IDS.META_STORE, "data"),
        State(IDS.PLAY_STORE, "data"),
        State(IDS.VIEW_REV_STORE, "data"),
        State(IDS.SHOW_VOLUME_STORE, "data"),
        State(IDS.SHOW_DECISION_STORE, "data"),
        prevent_initial_call=True,
    )
    def on_key_event(val, loaded, idx, meta, playing, view_rev, show_vol, show_dec):
        if not loaded or not meta:
            return no_update, no_update, no_update, no_update, no_update, no_update, no_update
        try:
            payload = json.loads(val) if val else {}
        except Exception:
            payload = {}
        key = str(payload.get("key", "")).lower()
        shift = bool(payload.get("shift", False))
        idx = int(idx) if idx is not None else 0
        max_i = int(meta.get("bar_count", 0)) - 1

        idx_out = no_update
        playing_out = no_update
        view_rev_out = no_update
        show_vol_out = no_update
        show_dec_out = no_update
        action_out = no_update
        status = no_update

        if key in ("arrowleft", "arrowright"):
            step = 5 if shift else 1
            idx_out = _clamp_index(idx - step, max_i) if key == "arrowleft" else _clamp_index(idx + step, max_i)
            status = _render_status(f"Index: {idx_out}/{max_i}", ok=None)
        elif key in (" ", "spacebar"):
            playing_out = not bool(playing)
            status = _render_status("Play" if playing_out else "Pause", ok=None)
        elif key == "a":
            v = int(view_rev) if view_rev is not None else 0
            view_rev_out = v + 1
        elif key == "v":
            show_vol_out = not bool(show_vol)
        elif key == "d":
            show_dec_out = not bool(show_dec)
        elif key == "1":
            action_out = Action.LONG.value
        elif key == "2":
            action_out = Action.SHORT.value
        elif key == "3":
            action_out = Action.PASS.value

        return idx_out, playing_out, view_rev_out, show_vol_out, show_dec_out, action_out, status

