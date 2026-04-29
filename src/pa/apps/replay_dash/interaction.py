from __future__ import annotations

import math
from dataclasses import dataclass


def snap_price(px: float, *, tick: float = 0.01) -> float:
    if tick <= 0:
        return float(px)
    return round(float(px) / float(tick)) * float(tick)


def parse_shape_y_updates(relayout: dict | None) -> dict[int, float]:
    """
    Extract Plotly shape y-position updates from relayoutData.

    Expected keys look like: ``shapes[12].y0``.
    The return value maps shape index -> new y value.
    """
    if not relayout:
        return {}

    shape_updates: dict[int, float] = {}
    for k, v in relayout.items():
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
    return shape_updates


@dataclass(frozen=True)
class DraftValidation:
    ok: bool
    errors: list[str]


def validate_draft(
    *,
    side: str,
    order_type: str,
    qty: int | None,
    limit_px: float | None,
    stop_px: float | None,
    stop_loss: float | None,
    take_profit: float | None,
    mark_price: float | None,
) -> DraftValidation:
    errs: list[str] = []

    q = int(qty or 0)
    if q <= 0:
        errs.append("Qty must be > 0.")

    ot = str(order_type or "").upper()
    if ot == "LIMIT" and limit_px is None:
        errs.append("LIMIT requires Limit price.")
    if ot == "STOP" and stop_px is None:
        errs.append("STOP requires Stop price.")
    if ot == "STOP_LIMIT" and (stop_px is None or limit_px is None):
        errs.append("STOP_LIMIT requires both Stop and Limit.")

    # Determine entry reference price for bracket validation.
    entry_ref: float | None = None
    if ot == "LIMIT":
        entry_ref = limit_px
    elif ot == "STOP":
        entry_ref = stop_px
    elif ot == "STOP_LIMIT":
        entry_ref = limit_px
    elif ot == "MARKET":
        entry_ref = mark_price

    s = str(side or "").upper()
    if entry_ref is not None and (stop_loss is not None or take_profit is not None):
        if s in ("BUY", "LONG"):
            if stop_loss is not None and not (float(stop_loss) < float(entry_ref)):
                errs.append("For LONG: stop loss must be < entry.")
            if take_profit is not None and not (float(entry_ref) < float(take_profit)):
                errs.append("For LONG: target must be > entry.")
        elif s in ("SELL_SHORT", "SHORT"):
            if stop_loss is not None and not (float(stop_loss) > float(entry_ref)):
                errs.append("For SHORT: stop loss must be > entry.")
            if take_profit is not None and not (float(take_profit) < float(entry_ref)):
                errs.append("For SHORT: target must be < entry.")

    # Basic numeric sanity.
    for name, v in [("Limit", limit_px), ("Stop", stop_px), ("Stop loss", stop_loss), ("Target", take_profit)]:
        if v is None:
            continue
        if not math.isfinite(float(v)):
            errs.append(f"{name} must be a valid number.")

    return DraftValidation(ok=(len(errs) == 0), errors=errs)


def click_price_from_plotly(click_data: dict | None) -> float | None:
    """
    Extract a price from Plotly clickData.
    Prefer y if present; otherwise fall back to hovertext parsing is avoided (fragile).
    """

    if not click_data:
        return None
    pts = click_data.get("points") or []
    if not pts:
        return None
    p0 = pts[0] or {}
    y = p0.get("y")
    if y is None:
        return None
    try:
        return float(y)
    except Exception:
        return None

