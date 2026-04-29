from __future__ import annotations

import pandas as pd
from dash import html

from ...sim.models import OrderStatus, Position


def render_position_summary(pos: Position) -> html.Div:
    avg_s = f"{pos.avg_entry:.2f}" if pos.avg_entry is not None else "—"
    return html.Div(
        [
            html.Span(f"{pos.side.value}", style={"fontWeight": 800}),
            html.Span(f"  qty {pos.qty}", style={"marginLeft": "8px"}),
            html.Span(f"  avg {avg_s}", style={"marginLeft": "8px"}),
        ],
        style={"fontSize": "13px"},
    )


def render_pnl_summary(sim_store: dict, pos: Position, *, starting_equity: float) -> html.Div:
    le = sim_store.get("last_equity")
    if le:
        return html.Div(
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
    return html.Div(
        [
            html.Span("U ", style={"color": "#64748b"}),
            html.Span("0.00", style={"fontWeight": 800}),
            html.Span("   R ", style={"color": "#64748b", "marginLeft": "10px"}),
            html.Span(f"{pos.realized_pnl:.2f}", style={"fontWeight": 800}),
            html.Span("   Eq ", style={"color": "#64748b", "marginLeft": "10px"}),
            html.Span(f"{(starting_equity + pos.realized_pnl):.2f}", style={"fontWeight": 800}),
        ],
        style={"fontSize": "13px"},
    )


def render_session_summary(sim_store: dict) -> html.Div:
    persist_ok = bool(sim_store.get("persist_ok", True))
    persist_err = str(sim_store.get("persist_err", "") or "")
    active_count = len([o for o in (sim_store.get("orders", []) or []) if str(o.get("status", "")) in ("PENDING", "WORKING", "TRIGGERED")])
    return html.Div(
        [
            html.Span(f"Session {str(sim_store.get('session_id', ''))[:8]}", style={"fontWeight": 700}),
            html.Span(f" · fills {len(sim_store.get('fills', []) or [])}", style={"marginLeft": "8px", "color": "#64748b"}),
            html.Span(f" · active orders {active_count}", style={"marginLeft": "8px", "color": "#64748b"}),
            html.Span(" · persisted" if persist_ok else " · persistence disabled", style={"marginLeft": "8px", "color": "#16a34a" if persist_ok else "#dc2626"}),
            html.Span(f" ({persist_err})" if (not persist_ok and persist_err) else "", style={"color": "#dc2626"}),
        ],
        style={"fontSize": "12px"},
    )


def render_active_orders(active_orders: list) -> tuple[html.Div | html.Table, list[dict]]:
    if not active_orders:
        return html.Div("No active orders.", style={"fontSize": "12px", "color": "#475569"}), []

    cancel_opts = [{"label": f"{o.order_id[:8]} · {o.side.value} {o.type.value} x{o.qty} · {o.status.value}", "value": o.order_id} for o in active_orders]
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
    for o in active_orders[:15]:
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
    table = html.Table([html.Thead(header), html.Tbody(body)], style={"width": "100%", "borderCollapse": "collapse"})
    return table, cancel_opts


def render_recent_fills(sim_store: dict):
    fills = list(sim_store.get("fills", []) or [])[-10:]
    if not fills:
        return html.Div("No fills yet.", style={"fontSize": "12px", "color": "#475569"})

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
    return html.Table([html.Thead(header), html.Tbody(body)], style={"width": "100%", "borderCollapse": "collapse"})


def render_selected_order_detail(sim_store: dict, selected_order_id: str | None) -> str:
    if not selected_order_id:
        return ""
    od = next((o for o in (sim_store.get("orders", []) or []) if o.get("order_id") == selected_order_id), None)
    if not od:
        return ""
    px = []
    if od.get("limit_price") is not None:
        px.append(f"L {float(od.get('limit_price')):.2f}")
    if od.get("stop_price") is not None:
        px.append(f"S {float(od.get('stop_price')):.2f}")
    af = od.get("active_from_utc")
    af_s = pd.Timestamp(af).tz_convert("UTC").strftime("%H:%M") + " UTC" if af else "now"
    return f"Selected: {str(od.get('side',''))} {str(od.get('type',''))} x{int(od.get('qty',0))} · {str(od.get('status',''))} · active {af_s}" + (
        f" · {', '.join(px)}" if px else ""
    )


def active_working_orders(orders: list) -> list:
    active = [o for o in orders if o.status in (OrderStatus.PENDING, OrderStatus.WORKING, OrderStatus.TRIGGERED)]
    active.sort(key=lambda o: str(o.created_at_utc))
    return active

