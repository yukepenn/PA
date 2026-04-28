from __future__ import annotations

from dataclasses import dataclass

import plotly.graph_objects as go


@dataclass(frozen=True)
class PriceMarkerStyle:
    color: str
    dash: str = "solid"
    width: int = 2
    bgcolor: str = "rgba(255,255,255,0.82)"
    bordercolor: str | None = None
    text_color: str | None = None


def add_price_marker(
    fig: go.Figure,
    *,
    y: float,
    text: str,
    name: str,
    style: PriceMarkerStyle,
    active: bool = False,
    yshift_px: int = 0,
) -> None:
    """
    Plotly approximation of a TradingView-like price-scale marker:
    - full-width horizontal line (shape)
    - right-edge badge (annotation) sitting on the y-axis side

    The `name` is stored on both shape + annotation so relayout can map drags to fields.
    """

    line_width = int(style.width) + (1 if active else 0)
    border = style.bordercolor or style.color
    txtc = style.text_color or style.color
    bg = "rgba(255,255,255,0.92)" if active else style.bgcolor

    fig.add_shape(
        type="line",
        xref="paper",
        yref="y",
        x0=0,
        x1=1,
        y0=float(y),
        y1=float(y),
        line=dict(color=style.color, width=line_width, dash=style.dash),
        layer="above",
        editable=False,
        name=name,
    )
    fig.add_annotation(
        xref="paper",
        yref="y",
        x=1.0,
        y=float(y),
        xanchor="right",
        yanchor="bottom",
        text=text,
        showarrow=False,
        font=dict(size=11, color=txtc),
        bgcolor=bg,
        bordercolor=border,
        borderwidth=1,
        yshift=int(yshift_px),
        name=name,
    )


def suggest_yshift_px(existing_ys: list[float], *, y: float, px_step: int = 14, tol: float = 0.04) -> int:
    """
    Very small, stable stacking heuristic:
    if multiple markers are close in y, shift later ones upward in pixels.
    `tol` is in absolute price units (good enough for equities with ~0.01 tick).
    """

    near = 0
    yy = float(y)
    for prev in existing_ys:
        if abs(float(prev) - yy) <= float(tol):
            near += 1
    return near * int(px_step)

