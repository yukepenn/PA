from __future__ import annotations

import pandas as pd

from .models import Bar1m, Order, OrderSide, OrderStatus, OrderType


def _as_utc(ts: pd.Timestamp) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def order_is_active(order: Order, bar_ts_utc: pd.Timestamp) -> bool:
    if order.active_from_utc is None:
        return True
    return _as_utc(bar_ts_utc) >= _as_utc(order.active_from_utc)


def _market_fill_price(order: Order, bar: Bar1m) -> float:
    # v1: market fills at next eligible 1-min bar open.
    return float(bar.open)


def _limit_fill_price(order: Order, bar: Bar1m) -> float | None:
    lp = order.limit_price
    if lp is None:
        return None

    o, h, l = float(bar.open), float(bar.high), float(bar.low)
    lp = float(lp)

    if order.side in (OrderSide.BUY, OrderSide.BUY_TO_COVER):
        if o <= lp:
            return o  # better-than-limit fill
        if l <= lp:
            return lp
        return None

    # SELL / SELL_SHORT
    if o >= lp:
        return o  # better-than-limit fill
    if h >= lp:
        return lp
    return None


def _stop_fill_price(order: Order, bar: Bar1m) -> float | None:
    sp = order.stop_price
    if sp is None:
        return None

    o, h, l = float(bar.open), float(bar.high), float(bar.low)
    sp = float(sp)

    if order.side in (OrderSide.BUY, OrderSide.BUY_TO_COVER):
        # Buy stop triggers when price trades >= stop.
        if o >= sp:
            return o  # gap-through stop -> fill at open (worse)
        if h >= sp:
            return sp
        return None

    # Sell stop triggers when price trades <= stop.
    if o <= sp:
        return o  # gap-through stop -> fill at open (worse)
    if l <= sp:
        return sp
    return None


def _stop_limit_fill_price(order: Order, bar: Bar1m) -> float | None:
    """
    Stop-limit fill semantics (v1, deterministic, conservative):

    Two-phase behavior:
    - Before trigger: behaves like a stop order that, once triggered, turns into a limit order.
    - After trigger (order.status == TRIGGERED): behaves exactly like a LIMIT order.

    Trigger rules (BUY / BUY_TO_COVER):
    - Triggered if open >= stop OR high >= stop.
    - On a gap-trigger (open >= stop), the limit leg can only fill if open <= limit.
      If open > limit, it is triggered but NOT filled (limit unreachable on the gap).

    Trigger rules (SELL / SELL_SHORT):
    - Triggered if open <= stop OR low <= stop.
    - On a gap-trigger (open <= stop), the limit leg can only fill if open >= limit.
      If open < limit, it is triggered but NOT filled.

    After trigger:
    - Use limit fill rules on subsequent bars (and same bar if reachable without optimism).
    """

    sp = order.stop_price
    lp = order.limit_price
    if sp is None or lp is None:
        return None

    o, h, l = float(bar.open), float(bar.high), float(bar.low)
    sp = float(sp)
    lp = float(lp)

    if order.side in (OrderSide.BUY, OrderSide.BUY_TO_COVER):
        # Already triggered -> behave like limit.
        if order.status == OrderStatus.TRIGGERED:
            return _limit_fill_price(order, bar)

        # Not triggered yet: detect trigger.
        gap_trigger = o >= sp
        intrabar_trigger = h >= sp
        if not (gap_trigger or intrabar_trigger):
            return None

        # If it triggers, we only allow same-bar fill if limit is reachable.
        # Gap trigger: must be able to buy at/below limit.
        if gap_trigger:
            if o <= lp:
                return o
            return None  # triggered, but limit unreachable on gap

        # Intrabar trigger (not at open): require that low <= limit, fill at limit (not better).
        if l <= lp:
            return lp
        return None  # triggered, but limit unreachable this bar

    # SELL / SELL_SHORT
    if order.status == OrderStatus.TRIGGERED:
        return _limit_fill_price(order, bar)

    gap_trigger = o <= sp
    intrabar_trigger = l <= sp
    if not (gap_trigger or intrabar_trigger):
        return None

    if gap_trigger:
        if o >= lp:
            return o
        return None

    if h >= lp:
        return lp
    return None


def try_fill(order: Order, bar: Bar1m) -> float | None:
    """
    Return fill price if order would fill on this bar, else None.
    Caller must enforce activation timing.
    """

    if order.type == OrderType.MARKET:
        return _market_fill_price(order, bar)
    if order.type == OrderType.LIMIT:
        return _limit_fill_price(order, bar)
    if order.type == OrderType.STOP:
        return _stop_fill_price(order, bar)
    if order.type == OrderType.STOP_LIMIT:
        return _stop_limit_fill_price(order, bar)
    raise ValueError(f"Unsupported order type: {order.type}")

