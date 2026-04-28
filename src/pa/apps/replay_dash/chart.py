from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ...replay.engine import ReplayEngine
from ...replay.models import ReplayState

from .price_labels import PriceMarkerStyle, add_price_marker, suggest_yshift_px
from .trade_viz import derive_trade_episodes, planned_bracket_levels_at_entry
from .viewport import rth_session_x_range_utc


@dataclass(frozen=True)
class ChartFlags:
    show_volume: bool = True
    show_or: bool = False


def add_sim_overlays(
    fig: go.Figure,
    *,
    sim_store: dict | None,
    visible_end_utc: pd.Timestamp | None,
) -> go.Figure:
    """
    Display-only overlays for sim state:
    - active entry order lines (limit/stop/stop-limit)
    - active bracket stop/target lines
    - position avg entry line
    - recent fill markers (clipped to visible_end_utc)
    """

    if not sim_store:
        return fig

    try:
        end = pd.Timestamp(visible_end_utc) if visible_end_utc is not None else None
        if end is not None:
            end = end.tz_localize("UTC") if end.tzinfo is None else end.tz_convert("UTC")
    except Exception:
        end = None

    used_ys: list[float] = []

    def _marker(y: float, *, color: str, dash: str, label: str, name: str) -> None:
        yshift = suggest_yshift_px(used_ys, y=float(y))
        used_ys.append(float(y))
        add_price_marker(
            fig,
            y=float(y),
            text=label,
            name=name,
            style=PriceMarkerStyle(color=color, dash=dash, width=2, bgcolor="rgba(255,255,255,0.78)"),
            active=False,
            yshift_px=yshift,
        )

    # Position/trade context
    pos = sim_store.get("position") or {}
    qty = int(pos.get("qty", 0) or 0)
    avg = pos.get("avg_entry", None)

    # Orders (active only)
    orders = list(sim_store.get("orders", []) or [])
    active_status = {"PENDING", "WORKING", "TRIGGERED"}
    active_orders = [o for o in orders if str(o.get("status", "")) in active_status]

    # If a trade is open, prefer day-trader style risk/reward visualization over generic full-width working lines.
    open_ep, closed_eps = derive_trade_episodes(sim_store, visible_end_utc=end)
    if qty != 0 and avg is not None and str(avg) != "" and open_ep is not None and end is not None:
        entry_px = float(open_ep.entry_px)
        side = open_ep.side

        # Planned RR frozen from bracket placement (authoritative semantics for review).
        stop_px, tgt_px = planned_bracket_levels_at_entry(sim_store, entry_order_id=open_ep.entry_order_id)
        # Fallback: active bracket legs still present while open.
        if stop_px is None or tgt_px is None:
            for o in active_orders:
                if not o.get("parent_order_id"):
                    continue
                typ = str(o.get("type", ""))
                lp = o.get("limit_price", None)
                sp = o.get("stop_price", None)
                if stop_px is None and typ == "STOP" and sp is not None:
                    stop_px = float(sp)
                if tgt_px is None and typ == "LIMIT" and lp is not None:
                    tgt_px = float(lp)

        x0 = open_ep.entry_ts_utc
        x1 = end

        def _band(y0: float, y1: float, *, fill: str, name: str) -> None:
            lo = float(min(y0, y1))
            hi = float(max(y0, y1))
            fig.add_shape(
                type="rect",
                xref="x",
                yref="y",
                x0=x0,
                x1=x1,
                y0=lo,
                y1=hi,
                fillcolor=fill,
                line=dict(width=0),
                layer="below",
                name=name,
            )

        # Profit/loss zones (stronger but still professional)
        if stop_px is not None:
            if side == "LONG":
                _band(stop_px, entry_px, fill="rgba(220,38,38,0.14)", name="trade:loss")
            else:
                _band(entry_px, stop_px, fill="rgba(220,38,38,0.14)", name="trade:loss")
        if tgt_px is not None:
            if side == "LONG":
                _band(entry_px, tgt_px, fill="rgba(22,163,74,0.14)", name="trade:profit")
            else:
                _band(tgt_px, entry_px, fill="rgba(22,163,74,0.14)", name="trade:profit")

        # Markers: entry/stop/target (bounded in time; but price badges still show at right edge).
        _marker(entry_px, color="rgba(2,6,23,0.78)", dash="solid", label=f"Entry fill {entry_px:.2f}", name="trade:entry")
        if stop_px is not None:
            _marker(stop_px, color="rgba(234,88,12,0.92)", dash="dash", label=f"Stop (plan) {stop_px:.2f}", name="trade:stop")
        if tgt_px is not None:
            _marker(tgt_px, color="rgba(139,92,246,0.90)", dash="dash", label=f"Tgt (plan) {tgt_px:.2f}", name="trade:target")

        # Still show fill markers for context.
        # (fall through to fill marker section below)

    else:
        # Not in an open position: show avg entry (if any) and active working orders.
        if avg is not None and str(avg) != "":
            _marker(float(avg), color="rgba(2,6,23,0.62)", dash="dash", label=f"Avg {float(avg):.2f}", name="sim:avg_entry")

        # Entry orders: parent_order_id is None
        for o in active_orders:
            if o.get("parent_order_id"):
                continue
            typ = str(o.get("type", ""))
            lp = o.get("limit_price", None)
            sp = o.get("stop_price", None)
            status = str(o.get("status", ""))
            oid = str(o.get("order_id", ""))[:6]

            if typ == "LIMIT" and lp is not None:
                _marker(
                    float(lp),
                    color="rgba(37,99,235,0.80)",
                    dash="solid",
                    label=f"E LMT {float(lp):.2f} · {status} · {oid}",
                    name=f"sim:entry_limit:{oid}",
                )
            elif typ == "STOP" and sp is not None:
                _marker(
                    float(sp),
                    color="rgba(245,158,11,0.88)",
                    dash="solid",
                    label=f"E STP {float(sp):.2f} · {status} · {oid}",
                    name=f"sim:entry_stop:{oid}",
                )
            elif typ == "STOP_LIMIT":
                if sp is not None:
                    _marker(
                        float(sp),
                        color="rgba(245,158,11,0.88)",
                        dash="dot",
                        label=f"E STP {float(sp):.2f} · {status} · {oid}",
                        name=f"sim:entry_stop:{oid}",
                    )
                if lp is not None:
                    _marker(
                        float(lp),
                        color="rgba(37,99,235,0.80)",
                        dash="dot",
                        label=f"E LMT {float(lp):.2f} · {status} · {oid}",
                        name=f"sim:entry_limit:{oid}",
                    )

        # Bracket legs: STOP (stop-loss) and LIMIT (target)
        for o in active_orders:
            if not o.get("parent_order_id"):
                continue
            typ = str(o.get("type", ""))
            lp = o.get("limit_price", None)
            sp = o.get("stop_price", None)
            status = str(o.get("status", ""))
            oid = str(o.get("order_id", ""))[:6]
            if typ == "STOP" and sp is not None:
                _marker(
                    float(sp),
                    color="rgba(234,88,12,0.90)",
                    dash="dash",
                    label=f"Stop {float(sp):.2f} · {status} · {oid}",
                    name=f"sim:stop_loss:{oid}",
                )
            elif typ == "LIMIT" and lp is not None:
                _marker(
                    float(lp),
                    color="rgba(139,92,246,0.86)",
                    dash="dash",
                    label=f"Tgt {float(lp):.2f} · {status} · {oid}",
                    name=f"sim:target:{oid}",
                )

    # Closed trades: bounded historical boxes (entry->exit), clipped to visible end.
    if closed_eps and end is not None:
        def _band(x0, x1, y0: float, y1: float, *, fill: str, name: str) -> None:
            lo = float(min(y0, y1))
            hi = float(max(y0, y1))
            fig.add_shape(
                type="rect",
                xref="x",
                yref="y",
                x0=x0,
                x1=x1,
                y0=lo,
                y1=hi,
                fillcolor=fill,
                line=dict(width=0),
                layer="below",
                name=name,
            )

        for ep in closed_eps[-8:]:
            if ep.exit_ts_utc is None or ep.exit_px is None:
                continue
            x0 = ep.entry_ts_utc
            x1 = ep.exit_ts_utc
            if x0 > end:
                continue
            if x1 > end:
                x1 = end

            entry_px = float(ep.entry_px)
            exit_px = float(ep.exit_px)
            stop_px, tgt_px = planned_bracket_levels_at_entry(sim_store, entry_order_id=ep.entry_order_id)

            # Preserve planned RR structure (as-of entry): both risk (red) and reward (green).
            if stop_px is not None:
                if ep.side == "LONG":
                    _band(x0, x1, stop_px, entry_px, fill="rgba(220,38,38,0.14)", name="trade:closed_risk")
                else:
                    _band(x0, x1, entry_px, stop_px, fill="rgba(220,38,38,0.14)", name="trade:closed_risk")
            if tgt_px is not None:
                if ep.side == "LONG":
                    _band(x0, x1, entry_px, tgt_px, fill="rgba(22,163,74,0.14)", name="trade:closed_reward")
                else:
                    _band(x0, x1, tgt_px, entry_px, fill="rgba(22,163,74,0.14)", name="trade:closed_reward")

            # If no bracket info is available, fall back to a subtle entry->exit box.
            if stop_px is None and tgt_px is None:
                win = (ep.side == "LONG" and exit_px >= entry_px) or (ep.side == "SHORT" and exit_px <= entry_px)
                fill = "rgba(22,163,74,0.08)" if win else "rgba(220,38,38,0.08)"
                fig.add_shape(
                    type="rect",
                    xref="x",
                    yref="y",
                    x0=x0,
                    x1=x1,
                    y0=min(entry_px, exit_px),
                    y1=max(entry_px, exit_px),
                    fillcolor=fill,
                    line=dict(color="rgba(2,6,23,0.20)", width=1, dash="dot"),
                    layer="below",
                    name="trade:closed_box",
                )

            fig.add_trace(
                go.Scatter(
                    x=[ep.entry_ts_utc],
                    y=[float(ep.entry_px)],
                    mode="markers",
                    marker=dict(size=11, color="rgba(2,6,23,0.90)", symbol="circle"),
                    name="Entry fill",
                    hovertemplate="<b>Entry fill</b><br>%{x|%H:%M} UTC<br>%{y:.2f}<extra></extra>",
                    showlegend=False,
                ),
                row=1,
                col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=[ep.exit_ts_utc],
                    y=[float(ep.exit_px)],
                    mode="markers",
                    marker=dict(size=11, color="rgba(2,6,23,0.90)", symbol="x"),
                    name="Exit fill",
                    hovertemplate="<b>Exit fill</b><br>%{x|%H:%M} UTC<br>%{y:.2f}<extra></extra>",
                    showlegend=False,
                ),
                row=1,
                col=1,
            )

    # Fill markers (recent, clipped to visible end to avoid future leakage in replay view)
    fills = list(sim_store.get("fills", []) or [])[-50:]
    if fills:
        xs = []
        ys = []
        cs = []
        syms = []
        for f in fills:
            ts_s = f.get("ts_utc")
            if not ts_s:
                continue
            try:
                t = pd.Timestamp(ts_s)
                t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
            except Exception:
                continue
            if end is not None and t > end:
                continue
            px = f.get("price", None)
            if px is None:
                continue
            side = str(f.get("side", ""))
            xs.append(t)
            ys.append(float(px))
            if side in ("BUY", "BUY_TO_COVER"):
                cs.append("rgba(22,163,74,0.95)")
                syms.append("triangle-up")
            else:
                cs.append("rgba(220,38,38,0.95)")
                syms.append("triangle-down")

        if xs:
            fig.add_trace(
                go.Scatter(
                    x=xs,
                    y=ys,
                    mode="markers",
                    marker=dict(size=12, color=cs, symbol=syms, line=dict(width=1.5, color="rgba(255,255,255,0.95)")),
                    name="Fills",
                    hovertemplate="Fill<br>%{x|%H:%M} UTC<br>%{y:.2f}<extra></extra>",
                ),
                row=1,
                col=1,
            )

    return fig


def add_draft_overlays(fig: go.Figure, *, draft: dict | None, valid: bool, active_mode: str | None = None) -> go.Figure:
    """
    Display-only draft preview lines (not actual orders).
    """

    if not draft:
        return fig

    used_ys: list[float] = []

    # Distinct colors per draft field (critical for readability and safe mapping).
    C_ENTRY_LIMIT = "rgba(37,99,235,0.70)"
    C_ENTRY_STOP = "rgba(245,158,11,0.78)"
    C_SL = "rgba(234,88,12,0.86)"
    C_TP = "rgba(139,92,246,0.74)"
    C_BAD = "rgba(220,38,38,0.88)"

    def _draft_marker(y: float, *, label: str, name: str, color: str, active: bool) -> None:
        yshift = suggest_yshift_px(used_ys, y=float(y))
        used_ys.append(float(y))
        add_price_marker(
            fig,
            y=float(y),
            text=label,
            name=name,
            style=PriceMarkerStyle(color=color, dash="dot", width=2, bgcolor="rgba(255,255,255,0.72)"),
            active=active,
            yshift_px=yshift,
        )
        # Make the draft line draggable; keep the badge non-draggable.
        # We rely on relayoutData updating shapes[i].y0 for drag events.
        fig.layout.shapes[-1].update(editable=True)

    ok = bool(valid)
    mode = str(active_mode or "")
    if draft.get("entry") is not None:
        _draft_marker(
            float(draft["entry"]),
            label=f"Draft entry {float(draft['entry']):.2f}",
            name="draft:entry",
            color=(C_ENTRY_LIMIT if ok else C_BAD),
            active=(mode == "entry"),
        )
    # STOP_LIMIT explicit legs
    if draft.get("entry_stop") is not None:
        _draft_marker(
            float(draft["entry_stop"]),
            label=f"Draft entry stop {float(draft['entry_stop']):.2f}",
            name="draft:entry_stop",
            color=(C_ENTRY_STOP if ok else C_BAD),
            active=(mode == "entry_stop"),
        )
    if draft.get("entry_limit") is not None:
        _draft_marker(
            float(draft["entry_limit"]),
            label=f"Draft entry limit {float(draft['entry_limit']):.2f}",
            name="draft:entry_limit",
            color=(C_ENTRY_LIMIT if ok else C_BAD),
            active=(mode == "entry_limit"),
        )
    if draft.get("stop_loss") is not None:
        _draft_marker(
            float(draft["stop_loss"]),
            label=f"Draft SL {float(draft['stop_loss']):.2f}",
            name="draft:stop_loss",
            color=(C_SL if ok else C_BAD),
            active=(mode == "stop"),
        )
    if draft.get("take_profit") is not None:
        _draft_marker(
            float(draft["take_profit"]),
            label=f"Draft TP {float(draft['take_profit']):.2f}",
            name="draft:take_profit",
            color=(C_TP if ok else C_BAD),
            active=(mode == "target"),
        )
    return fig


def add_hover_overlay(fig: go.Figure, *, hover_price: float | None) -> go.Figure:
    if hover_price is None:
        return fig
    used_ys: list[float] = []
    y = float(hover_price)
    yshift = suggest_yshift_px(used_ys, y=y, tol=0.02)
    used_ys.append(y)
    add_price_marker(
        fig,
        y=y,
        text=f"{y:.2f}",
        name="hover:price",
        style=PriceMarkerStyle(color="rgba(2,6,23,0.55)", dash="dot", width=1, bgcolor="rgba(255,255,255,0.88)", text_color="rgba(2,6,23,0.90)"),
        active=True,
        yshift_px=yshift,
    )
    return fig


def empty_figure(msg: str = "Load a day to start") -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        margin=dict(l=10, r=10, t=40, b=10),
        height=720,
        title=dict(text=msg, x=0.01, xanchor="left"),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    return fig


def session_markers_shapes(date_et: str) -> list[dict]:
    xr = rth_session_x_range_utc(date_et)
    if not xr:
        return []
    open_et, close_et = xr
    line = dict(color="rgba(2,6,23,0.18)", width=1, dash="dot")
    return [
        dict(type="line", xref="x", yref="paper", x0=open_et, x1=open_et, y0=0, y1=1, line=line),
        dict(type="line", xref="x", yref="paper", x0=close_et, x1=close_et, y0=0, y1=1, line=line),
    ]


def compute_orh_orl(df_5min: pd.DataFrame, date_et: str) -> tuple[float | None, float | None]:
    if df_5min.empty:
        return None, None
    et = "America/New_York"
    start_et = pd.Timestamp(f"{date_et} 09:30:00").tz_localize(et).tz_convert("UTC")
    end_et = pd.Timestamp(f"{date_et} 10:00:00").tz_localize(et).tz_convert("UTC")
    ts = pd.to_datetime(df_5min["ts_utc"], utc=True, errors="coerce")
    w = df_5min.loc[(ts >= start_et) & (ts <= end_et)]
    if w.empty:
        return None, None
    hi = pd.to_numeric(w["high"], errors="coerce").max()
    lo = pd.to_numeric(w["low"], errors="coerce").min()
    if pd.isna(hi) or pd.isna(lo):
        return None, None
    return float(hi), float(lo)


def apply_session_viewport(fig: go.Figure, visible: pd.DataFrame, *, date_et: str, show_volume: bool) -> go.Figure:
    """
    Recommended default view: full RTH session on x; y from revealed bars only with light padding.
    """
    xr = rth_session_x_range_utc(date_et)
    if xr:
        x0, x1 = xr
        fig.update_xaxes(range=[x0, x1], row=1, col=1)
        if show_volume:
            fig.update_xaxes(range=[x0, x1], row=2, col=1)
    if visible.empty:
        return fig
    lo = pd.to_numeric(visible["low"], errors="coerce").min()
    hi = pd.to_numeric(visible["high"], errors="coerce").max()
    if pd.isna(lo) or pd.isna(hi):
        return fig
    pad = float(hi - lo) * 0.028
    if pad <= 0:
        pad = float(hi) * 0.01 if float(hi) != 0 else 1.0
    fig.update_yaxes(range=[lo - pad, hi + pad], row=1, col=1)
    return fig


def build_figure(df_5min: pd.DataFrame, *, symbol: str, date_et: str, idx: int, flags: ChartFlags) -> go.Figure:
    if df_5min.empty:
        return empty_figure("No data loaded")

    eng = ReplayEngine(bars=df_5min, state=ReplayState(symbol=symbol, date_et=date_et, index=int(idx)))
    visible = eng.visible_bars()
    # Bump this string when changing chart visual grammar to force obvious confirmation.
    style_ver = "PA-BW-v1"
    title = f"{symbol} — {date_et} — {len(visible)}/{len(df_5min)}  ·  {style_ver}"

    rows = 2 if flags.show_volume else 1
    fig = make_subplots(
        rows=rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.02,
        row_heights=[0.92, 0.08] if flags.show_volume else [1.0],
    )

    fig.add_trace(
        go.Candlestick(
            x=visible["ts_utc"],
            open=visible["open"],
            high=visible["high"],
            low=visible["low"],
            close=visible["close"],
            # Classic black/white PA readability:
            # - up bars: hollow white with black border
            # - down bars: dark filled with black border
            increasing_line_color="rgba(2,6,23,0.92)",
            decreasing_line_color="rgba(2,6,23,0.92)",
            increasing_fillcolor="rgba(255,255,255,0.0)",
            decreasing_fillcolor="rgba(15,23,42,0.62)",
            increasing=dict(line=dict(width=1.8)),
            decreasing=dict(line=dict(width=1.8)),
            name="Price",
        ),
        row=1,
        col=1,
    )

    if flags.show_volume:
        fig.add_trace(
            go.Bar(
                x=visible["ts_utc"],
                y=visible["volume"],
                marker_color="rgba(100,116,139,0.50)",
                opacity=0.28,
                name="Volume",
            ),
            row=2,
            col=1,
        )

    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        margin=dict(l=8, r=8, t=46, b=10),
        height=860,
        title=dict(text=title, x=0.01, xanchor="left"),
        showlegend=False,
        hovermode="x unified",
        xaxis_rangeslider_visible=False,
        dragmode="pan",
        shapes=session_markers_shapes(date_et),
    )
    fig.update_xaxes(
        showgrid=False,
        zeroline=False,
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikedash="dot",
        spikecolor="rgba(2,6,23,0.28)",
        spikethickness=1,
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor="rgba(2,6,23,0.06)",
        zeroline=False,
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikedash="dot",
        spikecolor="rgba(2,6,23,0.28)",
        spikethickness=1,
        side="right",
    )

    # X/Y session viewport is applied in render_chart (manual preserve vs full RTH default).

    if flags.show_or:
        orh, orl = compute_orh_orl(df_5min, date_et)
        if orh is not None and orl is not None:
            fig.add_hline(y=orh, line_width=1, line_dash="dot", line_color="rgba(37,99,235,0.55)")
            fig.add_hline(y=orl, line_width=1, line_dash="dot", line_color="rgba(37,99,235,0.55)")

    return fig

