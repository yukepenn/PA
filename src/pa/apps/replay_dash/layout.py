from __future__ import annotations

import pandas as pd
from dash import dcc, html

from .ids import IDS
from .styles import btn_primary_style, btn_style, input_style, label_style, panel_style, palette
from ...replay.models import Action


SYMBOLS_DEFAULT = ["SPY", "QQQ", "IWM"]


def build_layout(default_date_et: str) -> html.Div:
    colors = palette()
    pstyle = panel_style(colors)
    lstyle = label_style(colors)
    istyle = input_style()
    bstyle = btn_style(colors)
    bprimary = btn_primary_style(colors)

    return html.Div(
        style={
            "background": colors["bg"],
            "color": colors["text"],
            "minHeight": "100vh",
            "padding": "14px",
            "fontFamily": "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial",
        },
        children=[
            dcc.Input(id=IDS.KEY_EVENT, value="", style={"display": "none"}),

            dcc.Store(id=IDS.BARS_STORE),
            dcc.Store(id=IDS.BARS1_STORE),
            dcc.Store(id=IDS.META_STORE),
            dcc.Store(id=IDS.INDEX_STORE, data=0),
            dcc.Store(id=IDS.ACTION_STORE, data=Action.PASS.value),
            dcc.Store(id=IDS.LOADED_STORE, data=False),
            dcc.Store(id=IDS.SHOW_VOLUME_STORE, data=False),
            dcc.Store(id=IDS.SHOW_DECISION_STORE, data=True),
            dcc.Store(id=IDS.VIEW_REV_STORE, data=0),
            dcc.Store(id=IDS.VIEW_LOCK_STORE, data=False),
            dcc.Store(id=IDS.VIEWPORT_STORE, data={"mode": "auto", "x": None, "y": None}),
            dcc.Store(id=IDS.PLAY_STORE, data=False),
            dcc.Store(id=IDS.SPEED_STORE, data="1x"),
            dcc.Store(id=IDS.PHASE_STORE, data="before"),
            dcc.Store(id=IDS.SHOW_OR_STORE, data=False),
            dcc.Store(id=IDS.SIM_STORE),
            dcc.Store(id=IDS.INTERACT_STORE, data={"click_mode": "entry", "draft": {}, "draft_valid": True, "draft_errors": []}),

            dcc.Interval(id=IDS.PLAY_TIMER, interval=800, disabled=True, n_intervals=0),

            html.Div(
                id=IDS.MAIN_GRID,
                style={"display": "grid", "gridTemplateColumns": "248px 1fr 296px", "gap": "12px"},
                children=[
                    # Left controls
                    html.Div(
                        style=pstyle,
                        children=[
                            html.Div("Replay Controls", style={"fontWeight": 700, "marginBottom": "10px"}),
                            html.Div(id=IDS.REPLAY_INFO, style={"fontSize": "12px", "color": colors["muted"], "marginBottom": "10px"}),

                            html.Div("Symbol", style=lstyle),
                            dcc.Dropdown(
                                id=IDS.SYMBOL,
                                options=[{"label": s, "value": s} for s in SYMBOLS_DEFAULT],
                                value="SPY",
                                clearable=False,
                                style=istyle,
                            ),
                            html.Div(style={"height": "10px"}),
                            html.Div("Date (ET)", style=lstyle),
                            dcc.DatePickerSingle(
                                id=IDS.DATE_ET,
                                date=default_date_et,
                                display_format="YYYY-MM-DD",
                                style=istyle,
                            ),
                            html.Div(style={"height": "12px"}),

                            html.Div(
                                style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "8px"},
                                children=[
                                    html.Button("Load", id=IDS.BTN_LOAD, n_clicks=0, style={**bprimary, "width": "100%"}),
                                    html.Button("Reset", id=IDS.BTN_RESET, n_clicks=0, style={**bstyle, "width": "100%"}, disabled=True),
                                ],
                            ),
                            html.Div(style={"height": "8px"}),

                            html.Div(
                                style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "8px"},
                                children=[
                                    html.Button("Play / Pause", id=IDS.BTN_PLAY, n_clicks=0, style={**bstyle, "width": "100%"}, disabled=True),
                                    dcc.Dropdown(
                                        id=IDS.SPEED,
                                        options=[{"label": s, "value": s} for s in ["1x", "2x", "5x"]],
                                        value="1x",
                                        clearable=False,
                                        style={"width": "100%"},
                                    ),
                                ],
                            ),
                            html.Div(style={"height": "8px"}),

                            html.Div(
                                style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "8px"},
                                children=[
                                    html.Button("Prev 1", id=IDS.BTN_PREV1, n_clicks=0, style={**bstyle, "width": "100%"}, disabled=True),
                                    html.Button("Prev 5", id=IDS.BTN_PREV5, n_clicks=0, style={**bstyle, "width": "100%"}, disabled=True),
                                ],
                            ),
                            html.Div(style={"height": "8px"}),
                            html.Div(
                                style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "8px"},
                                children=[
                                    html.Button("Next 1", id=IDS.BTN_NEXT1, n_clicks=0, style={**bstyle, "width": "100%"}, disabled=True),
                                    html.Button("Next 5", id=IDS.BTN_NEXT5, n_clicks=0, style={**bstyle, "width": "100%"}, disabled=True),
                                ],
                            ),
                            html.Div(style={"height": "8px"}),
                            html.Button("Display all", id=IDS.BTN_ALL, n_clicks=0, style={**bstyle, "width": "100%"}, disabled=True),

                            html.Div(style={"height": "12px"}),
                            html.Div("View", style=lstyle),
                            html.Div(
                                style={"display": "flex", "gap": "8px", "flexWrap": "wrap"},
                                children=[
                                    html.Button("Volume (V)", id=IDS.BTN_TOGGLE_VOLUME, n_clicks=0, style=bstyle),
                                    html.Button("Decision (D)", id=IDS.BTN_TOGGLE_DECISION, n_clicks=0, style=bstyle),
                                ],
                            ),

                            html.Div(style={"height": "12px"}),
                            html.Div(id=IDS.STATUS_LEFT, style={"fontSize": "12px", "color": colors["muted"]}),
                        ],
                    ),

                    # Center chart workspace
                    html.Div(
                        style=pstyle,
                        children=[
                            html.Div(
                                style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "gap": "10px"},
                                children=[
                                    html.Div("Replay", style={"fontWeight": 700}),
                                    html.Div(
                                        style={"display": "flex", "gap": "8px", "flexWrap": "wrap"},
                                        children=[
                                            html.Button("Autoscale (A)", id=IDS.BTN_AUTOSCALE, n_clicks=0, style=bstyle),
                                            html.Button("ORH/ORL", id=IDS.BTN_TOGGLE_OR, n_clicks=0, style=bstyle),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(style={"height": "10px"}),
                            html.Div(id=IDS.HOVER_READOUT, style={"fontSize": "12px", "color": colors["muted"], "marginBottom": "8px"}),
                            dcc.Graph(
                                id=IDS.CHART,
                                figure=None,
                                config={
                                    "displayModeBar": True,
                                    "scrollZoom": True,
                                    "doubleClick": "reset",
                                    # Stage 1 dragline: allow dragging draft shapes only.
                                    "editable": True,
                                    "edits": {"shapePosition": True},
                                },
                            ),
                        ],
                    ),

                    # Right decision panel
                    html.Div(
                        id=IDS.DECISION_PANEL,
                        style=pstyle,
                        children=[
                            dcc.Tabs(
                                id=IDS.RIGHT_TABS,
                                value="journal",
                                children=[
                                    dcc.Tab(
                                        label="Journal",
                                        value="journal",
                                        children=[
                                            html.Div("Decision", style={"fontWeight": 700, "marginBottom": "10px", "marginTop": "10px"}),
                                            dcc.Tabs(
                                                id=IDS.PHASE_TABS,
                                                value="before",
                                                children=[dcc.Tab(label="Before", value="before"), dcc.Tab(label="After review", value="after")],
                                            ),
                                            html.Div(style={"height": "10px"}),
                                            html.Div("Setup", style=lstyle),
                                            dcc.Input(id=IDS.INP_SETUP, type="text", placeholder="e.g. H2 / Micro double bottom", style=istyle),
                                            html.Div(style={"height": "10px"}),
                                            html.Div(
                                                style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "8px"},
                                                children=[
                                                    html.Div([html.Div("Confidence (1-5)", style=lstyle), dcc.Input(id=IDS.INP_CONF, type="number", min=1, max=5, step=1, placeholder="1-5", style=istyle)]),
                                                    html.Div([html.Div("Quality (1-5)", style=lstyle), dcc.Input(id=IDS.INP_QUALITY, type="number", min=1, max=5, step=1, placeholder="1-5", style=istyle)]),
                                                ],
                                            ),
                                            html.Div(style={"height": "10px"}),
                                            html.Div(
                                                style={"display": "grid", "gridTemplateColumns": "1fr 1fr 1fr", "gap": "8px"},
                                                children=[
                                                    html.Div([html.Div("Planned entry", style=lstyle), dcc.Input(id=IDS.INP_ENTRY, type="number", step=0.01, style=istyle)]),
                                                    html.Div([html.Div("Planned stop", style=lstyle), dcc.Input(id=IDS.INP_STOP, type="number", step=0.01, style=istyle)]),
                                                    html.Div([html.Div("Planned target", style=lstyle), dcc.Input(id=IDS.INP_TARGET, type="number", step=0.01, style=istyle)]),
                                                ],
                                            ),
                                            html.Div(style={"height": "10px"}),
                                            html.Div("Pass reason (if Pass)", style=lstyle),
                                            dcc.Input(id=IDS.INP_PASS_REASON, type="text", placeholder="Why pass?", style=istyle),
                                            html.Div(style={"height": "10px"}),
                                            html.Div("Notes", style=lstyle),
                                            dcc.Textarea(id=IDS.INP_NOTES, placeholder="Concise notes for this phase.", style={"width": "100%", "height": "120px", "resize": "vertical"}),
                                            html.Div(style={"height": "12px"}),
                                            html.Div("Action", style=lstyle),
                                            html.Div(
                                                style={"display": "grid", "gridTemplateColumns": "1fr 1fr 1fr", "gap": "8px"},
                                                children=[
                                                    html.Button("Long (1)", id=IDS.BTN_LONG, n_clicks=0, style=bstyle),
                                                    html.Button("Short (2)", id=IDS.BTN_SHORT, n_clicks=0, style=bstyle),
                                                    html.Button("Pass (3)", id=IDS.BTN_PASS, n_clicks=0, style=bstyle),
                                                ],
                                            ),
                                            html.Div(style={"height": "10px"}),
                                            html.Button("Save Decision", id=IDS.BTN_SAVE, n_clicks=0, disabled=True, style={**bprimary, "width": "100%"}),
                                            html.Div(style={"height": "10px"}),
                                            html.Div(id=IDS.STATUS_RIGHT, style={"fontSize": "12px", "color": colors["muted"]}),
                                            html.Hr(style={"borderColor": "rgba(2,6,23,0.10)", "margin": "12px 0"}),
                                            html.Div("Today's saved decisions", style={"fontWeight": 700, "marginBottom": "8px"}),
                                            html.Div(id=IDS.DECISIONS_LIST),
                                        ],
                                    ),
                                    dcc.Tab(
                                        label="Sim",
                                        value="sim",
                                        children=[
                                            html.Div(
                                                "Sim is monotonic: stepping replay backward does not roll back sim state. Use Reset to restart a sim session.",
                                                style={
                                                    "fontSize": "12px",
                                                    "color": colors["muted"],
                                                    "marginTop": "10px",
                                                    "marginBottom": "10px",
                                                },
                                            ),
                                            html.Div("Position", style={"fontWeight": 800, "marginBottom": "6px"}),
                                            html.Div(id=IDS.SIM_POS_SUMMARY),
                                            html.Div(style={"height": "8px"}),
                                            html.Div("PnL", style={"fontWeight": 800, "marginBottom": "6px"}),
                                            html.Div(id=IDS.SIM_PNL_SUMMARY),
                                            html.Div(style={"height": "8px"}),
                                            html.Div(id=IDS.SIM_SESSION_SUMMARY),
                                            html.Div(style={"height": "10px"}),
                                            html.Div(id=IDS.SIM_STATUS, style={"fontSize": "12px", "color": colors["muted"]}),
                                            html.Hr(style={"borderColor": "rgba(2,6,23,0.10)", "margin": "12px 0"}),
                                            html.Div("Active orders", style={"fontWeight": 800, "marginBottom": "6px"}),
                                            html.Div(id=IDS.SIM_ACTIVE_ORDERS),
                                            html.Div(style={"height": "10px"}),
                                            html.Div(
                                                style={"display": "grid", "gridTemplateColumns": "1fr 92px", "gap": "8px"},
                                                children=[
                                                    dcc.Dropdown(id=IDS.SIM_CANCEL_ORDER_ID, placeholder="Select order to cancel", style=istyle),
                                                    html.Button("Cancel", id=IDS.BTN_SIM_CANCEL, n_clicks=0, style={**bstyle, "width": "100%"}, disabled=True),
                                                ],
                                            ),
                                            html.Div(style={"height": "6px"}),
                                            html.Div(id=IDS.SIM_SELECTED_ORDER, style={"fontSize": "12px", "color": colors["muted"]}),
                                            html.Div(style={"height": "8px"}),
                                            html.Button("Flatten position", id=IDS.BTN_SIM_FLATTEN, n_clicks=0, style={**bstyle, "width": "100%"}, disabled=True),
                                            html.Hr(style={"borderColor": "rgba(2,6,23,0.10)", "margin": "12px 0"}),
                                            html.Div("Fills (latest)", style={"fontWeight": 800, "marginBottom": "6px"}),
                                            html.Div(id=IDS.SIM_FILLS),
                                            html.Hr(style={"borderColor": "rgba(2,6,23,0.10)", "margin": "12px 0"}),
                                            html.Div("Order Entry", style={"fontWeight": 800, "marginBottom": "10px"}),
                                            html.Div(
                                                [
                                                    html.Div("Chart order tools", style={"fontWeight": 800, "marginBottom": "6px"}),
                                                    dcc.RadioItems(
                                                        id=IDS.SIM_CLICK_MODE,
                                                        options=[],
                                                        value="entry",
                                                        inline=True,
                                                        style={"fontSize": "12px"},
                                                        inputStyle={"marginRight": "6px"},
                                                        labelStyle={
                                                            "marginRight": "10px",
                                                            "padding": "3px 8px",
                                                            "border": "1px solid rgba(2,6,23,0.14)",
                                                            "borderRadius": "999px",
                                                            "background": "rgba(255,255,255,0.9)",
                                                            "cursor": "pointer",
                                                        },
                                                    ),
                                                    html.Div(style={"height": "6px"}),
                                                    html.Div(id=IDS.SIM_CHART_TOOLS_HINT, style={"fontSize": "12px", "color": colors["muted"]}),
                                                ],
                                                style={"padding": "8px", "border": "1px solid rgba(2,6,23,0.10)", "borderRadius": "10px", "background": "rgba(248,250,252,0.85)"},
                                            ),
                                            html.Div(style={"height": "8px"}),
                                            html.Div(id=IDS.SIM_TICKET_SUMMARY, style={"fontSize": "12px", "color": colors["muted"]}),
                                            html.Div(
                                                style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "8px"},
                                                children=[
                                                    html.Div(
                                                        [
                                                            html.Div("Side", style=lstyle),
                                                            dcc.Dropdown(
                                                                id=IDS.SIM_SIDE,
                                                                options=[
                                                                    {"label": "Buy", "value": "BUY"},
                                                                    {"label": "Sell", "value": "SELL"},
                                                                    {"label": "Sell short", "value": "SELL_SHORT"},
                                                                    {"label": "Buy to cover", "value": "BUY_TO_COVER"},
                                                                ],
                                                                value="BUY",
                                                                clearable=False,
                                                                style=istyle,
                                                            ),
                                                        ]
                                                    ),
                                                    html.Div(
                                                        [
                                                            html.Div("Type", style=lstyle),
                                                            dcc.Dropdown(
                                                                id=IDS.SIM_ORDER_TYPE,
                                                                options=[{"label": t, "value": t} for t in ["MARKET", "LIMIT", "STOP", "STOP_LIMIT"]],
                                                                value="MARKET",
                                                                clearable=False,
                                                                style=istyle,
                                                            ),
                                                        ]
                                                    ),
                                                ],
                                            ),
                                            html.Div(style={"height": "8px"}),
                                            html.Div(
                                                style={"display": "grid", "gridTemplateColumns": "1fr 1fr 1fr", "gap": "8px"},
                                                children=[
                                                    html.Div([html.Div("Qty", style=lstyle), dcc.Input(id=IDS.SIM_QTY, type="number", min=1, step=1, value=1, style=istyle)]),
                                                    html.Div([html.Div("Limit", style=lstyle), dcc.Input(id=IDS.SIM_LIMIT, type="number", step=0.01, placeholder="(if LIMIT)", style=istyle)]),
                                                    html.Div([html.Div("Stop", style=lstyle), dcc.Input(id=IDS.SIM_STOP, type="number", step=0.01, placeholder="(if STOP)", style=istyle)]),
                                                ],
                                            ),
                                            html.Div(style={"height": "8px"}),
                                            html.Div(
                                                style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "8px"},
                                                children=[
                                                    html.Div([html.Div("Stop loss (opt)", style=lstyle), dcc.Input(id=IDS.SIM_STOP_LOSS, type="number", step=0.01, style=istyle)]),
                                                    html.Div([html.Div("Take profit (opt)", style=lstyle), dcc.Input(id=IDS.SIM_TAKE_PROFIT, type="number", step=0.01, style=istyle)]),
                                                ],
                                            ),
                                            html.Div(style={"height": "10px"}),
                                            html.Button("Place order", id=IDS.BTN_SIM_PLACE, n_clicks=0, style={**bprimary, "width": "100%"}, disabled=True),
                                            html.Div(style={"height": "8px"}),
                                            html.Div(id=IDS.SIM_VALIDATION, style={"fontSize": "12px", "color": colors["muted"]}),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            )
        ],
    )

