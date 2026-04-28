from __future__ import annotations

from dataclasses import replace

from .models import Fill, OrderSide, Position, PositionSide


def _side_from_qty(qty: int) -> PositionSide:
    if qty > 0:
        return PositionSide.LONG
    if qty < 0:
        return PositionSide.SHORT
    return PositionSide.FLAT


def apply_fill_to_position(pos: Position, fill: Fill) -> Position:
    """
    Update position + realized PnL given one fill.

    v1 assumptions:
    - single symbol
    - integer qty
    - no fees
    - no partial fills (but this still works if qty chunks appear)
    """

    qty = int(fill.qty)
    if qty <= 0:
        raise ValueError("fill.qty must be positive")

    # Signed fill quantity in position units (long positive, short negative)
    if fill.side in (OrderSide.BUY, OrderSide.BUY_TO_COVER):
        dq = qty
    elif fill.side in (OrderSide.SELL, OrderSide.SELL_SHORT):
        dq = -qty
    else:
        raise ValueError(f"Unknown fill side: {fill.side}")

    cur_qty = int(pos.qty)
    cur_avg = float(pos.avg_entry) if pos.avg_entry is not None else None
    realized = float(pos.realized_pnl)

    new_qty = cur_qty + dq

    # If currently flat, opening a new position.
    if cur_qty == 0:
        return replace(
            pos,
            qty=new_qty,
            side=_side_from_qty(new_qty),
            avg_entry=float(fill.price),
        )

    # Same direction add.
    if (cur_qty > 0 and new_qty > 0) or (cur_qty < 0 and new_qty < 0):
        assert cur_avg is not None
        # Weighted average.
        w0 = abs(cur_qty)
        w1 = abs(dq)
        new_avg = (cur_avg * w0 + float(fill.price) * w1) / float(w0 + w1)
        return replace(pos, qty=new_qty, side=_side_from_qty(new_qty), avg_entry=float(new_avg))

    # Reducing or flipping.
    assert cur_avg is not None
    closing_qty = min(abs(cur_qty), abs(dq))
    remaining_qty = cur_qty + dq

    # Realized PnL based on closed shares.
    if cur_qty > 0:  # closing long by selling (dq negative)
        realized += closing_qty * (float(fill.price) - cur_avg)
    else:  # cur_qty < 0, closing short by buying (dq positive)
        realized += closing_qty * (cur_avg - float(fill.price))

    if remaining_qty == 0:
        return replace(pos, qty=0, side=PositionSide.FLAT, avg_entry=None, realized_pnl=float(realized))

    # Flip: remaining position opens at fill price (conservative simplification).
    if (cur_qty > 0 and remaining_qty < 0) or (cur_qty < 0 and remaining_qty > 0):
        return replace(
            pos,
            qty=remaining_qty,
            side=_side_from_qty(remaining_qty),
            avg_entry=float(fill.price),
            realized_pnl=float(realized),
        )

    # Reduce without flip: keep avg_entry.
    return replace(pos, qty=remaining_qty, side=_side_from_qty(remaining_qty), avg_entry=cur_avg, realized_pnl=float(realized))


def would_flip_position(pos: Position, fill: Fill) -> bool:
    """
    v1 rule: no flip-in-one-step. A fill may reduce or flatten a position, but
    must not cross through zero to the opposite side.
    """

    qty = int(fill.qty)
    if qty <= 0:
        return False
    if fill.side in (OrderSide.BUY, OrderSide.BUY_TO_COVER):
        dq = qty
    elif fill.side in (OrderSide.SELL, OrderSide.SELL_SHORT):
        dq = -qty
    else:
        return False

    cur_qty = int(pos.qty)
    new_qty = cur_qty + dq
    return (cur_qty > 0 and new_qty < 0) or (cur_qty < 0 and new_qty > 0)


def unrealized_pnl(pos: Position, last_price: float) -> float:
    if pos.qty == 0 or pos.avg_entry is None:
        return 0.0
    if pos.qty > 0:
        return float(pos.qty) * (float(last_price) - float(pos.avg_entry))
    return float(abs(pos.qty)) * (float(pos.avg_entry) - float(last_price))

