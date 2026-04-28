from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pandas as pd

from .fill_rules import order_is_active, try_fill
from .models import (
    Bar1m,
    BracketSpec,
    EquitySnapshot,
    Fill,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PositionSide,
    SimSessionMeta,
    SimState,
    TimeInForce,
)
from .pnl import apply_fill_to_position, unrealized_pnl, would_flip_position


def _as_utc(ts: pd.Timestamp) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def _minute_after(ts_utc: pd.Timestamp) -> pd.Timestamp:
    t = _as_utc(ts_utc)
    # bars are already aligned to minutes; still, be explicit.
    return (t.floor("min") + pd.Timedelta(minutes=1)).tz_convert("UTC")


class SimEngine:
    """
    Deterministic manual trading simulator core.

    v1 constraints:
    - single symbol
    - single active position
    - no partial fills
    - OHLC-only, conservative intrabar assumptions
    - execution truth is 1-minute bars (UI may be 5-minute)
    """

    def __init__(self, meta: SimSessionMeta, *, starting_equity: float = 0.0) -> None:
        meta = replace(meta, symbol=meta.symbol.upper().strip())
        self.state = SimState(meta=meta, position=Position(symbol=meta.symbol))
        self.starting_equity = float(starting_equity)

    # -----------------------------
    # Order placement / management
    # -----------------------------

    def place_order(
        self,
        *,
        side: OrderSide,
        type: OrderType,
        qty: int,
        symbol: str | None = None,
        limit_price: float | None = None,
        stop_price: float | None = None,
        placed_at_utc: pd.Timestamp,
        active_from_utc: pd.Timestamp,
        tif: TimeInForce = TimeInForce.DAY,
        parent_order_id: str | None = None,
        oco_group_id: str | None = None,
    ) -> Order:
        sym = (symbol or self.state.meta.symbol).upper().strip()
        if sym != self.state.meta.symbol:
            raise ValueError("v1 supports single symbol only")
        if int(qty) <= 0:
            raise ValueError("qty must be positive")

        o = Order(
            order_id=str(uuid4()),
            symbol=sym,
            side=side,
            type=type,
            qty=int(qty),
            tif=tif,
            limit_price=limit_price,
            stop_price=stop_price,
            placed_at_utc=_as_utc(placed_at_utc),
            active_from_utc=_as_utc(active_from_utc),
            status=OrderStatus.PENDING,
            parent_order_id=parent_order_id,
            oco_group_id=oco_group_id,
        )
        self.state.orders[o.order_id] = o
        return o

    def place_bracket_order(
        self,
        *,
        entry_side: OrderSide,
        entry_type: OrderType,
        qty: int,
        placed_at_utc: pd.Timestamp,
        active_from_utc: pd.Timestamp,
        entry_limit: float | None = None,
        entry_stop: float | None = None,
        bracket: BracketSpec | None = None,
    ) -> dict[str, Order]:
        """
        Place an entry order and (optionally) attach stop-loss / take-profit.

        Exit legs are created immediately but remain PENDING until entry fills.
        They will be activated to start from the first 1-min bar after entry fill.
        """

        bracket = bracket or BracketSpec()
        oco = str(uuid4())

        entry = self.place_order(
            side=entry_side,
            type=entry_type,
            qty=qty,
            limit_price=entry_limit,
            stop_price=entry_stop,
            placed_at_utc=placed_at_utc,
            active_from_utc=active_from_utc,
        )

        legs: dict[str, Order] = {"entry": entry}

        if bracket.stop_loss is not None:
            legs["stop"] = self.place_order(
                side=_exit_side_for_entry(entry_side),
                type=OrderType.STOP,
                qty=qty,
                stop_price=float(bracket.stop_loss),
                placed_at_utc=placed_at_utc,
                active_from_utc=_as_utc(active_from_utc),  # will be updated on entry fill
                parent_order_id=entry.order_id,
                oco_group_id=oco,
            )

        if bracket.take_profit is not None:
            legs["target"] = self.place_order(
                side=_exit_side_for_entry(entry_side),
                type=OrderType.LIMIT,
                qty=qty,
                limit_price=float(bracket.take_profit),
                placed_at_utc=placed_at_utc,
                active_from_utc=_as_utc(active_from_utc),  # will be updated on entry fill
                parent_order_id=entry.order_id,
                oco_group_id=oco,
            )

        return legs

    def cancel_order(self, order_id: str, *, ts_utc: pd.Timestamp | None = None) -> Order:
        o = self._get(order_id)
        if o.status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED):
            return o
        o.status = OrderStatus.CANCELED
        o.updated_at_utc = _as_utc(ts_utc) if ts_utc is not None else pd.Timestamp.now(tz="UTC")
        self.state.orders[o.order_id] = o
        return o

    def cancel_oco_group(self, oco_group_id: str, *, keep_order_id: str | None = None, ts_utc: pd.Timestamp | None = None) -> None:
        for oid, o in list(self.state.orders.items()):
            if o.oco_group_id != oco_group_id:
                continue
            if keep_order_id and oid == keep_order_id:
                continue
            if o.status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED):
                continue
            self.cancel_order(oid, ts_utc=ts_utc)

    def flatten(self, *, placed_at_utc: pd.Timestamp, active_from_utc: pd.Timestamp) -> Order | None:
        """
        Flatten current position via market order.
        """

        pos = self.state.position
        if pos.qty == 0:
            return None

        if pos.qty > 0:
            side = OrderSide.SELL
        else:
            side = OrderSide.BUY_TO_COVER

        return self.place_order(
            side=side,
            type=OrderType.MARKET,
            qty=abs(int(pos.qty)),
            placed_at_utc=placed_at_utc,
            active_from_utc=active_from_utc,
        )

    # -----------------------------
    # Processing bars (execution)
    # -----------------------------

    def process_bar(self, bar: Bar1m) -> list[Fill]:
        """
        Process one 1-minute bar:
        - activate pending orders whose active_from_utc <= bar.ts_utc
        - try to fill WORKING orders (conservative OHLC rules)
        - apply fills to position and update OCO groups
        - snapshot equity
        """

        bts = _as_utc(bar.ts_utc)
        fills: list[Fill] = []

        # Activate orders (PENDING -> WORKING).
        for oid, o in list(self.state.orders.items()):
            if o.status == OrderStatus.PENDING and order_is_active(o, bts):
                o.status = OrderStatus.WORKING
                o.updated_at_utc = bts
                self.state.orders[oid] = o

        # v1: deterministic evaluation order:
        # - entry orders first (no parent_order_id)
        # - then exit orders, stop before target for conservative outcome
        # TRIGGERED stop-limits behave like working limit orders.
        working = [
            o
            for o in self.state.orders.values()
            if o.status in (OrderStatus.WORKING, OrderStatus.TRIGGERED) and order_is_active(o, bts)
        ]
        working.sort(key=_working_sort_key)

        for o in working:
            # bracket legs must not become effective until entry filled; we enforce by
            # setting active_from_utc when entry fills (see _on_fill()).
            px = try_fill(o, bar)
            if px is None:
                # Stop-limit may have triggered but not filled; promote to TRIGGERED so it can
                # behave as a limit order on subsequent bars.
                if o.type == OrderType.STOP_LIMIT and o.status == OrderStatus.WORKING:
                    if _stop_limit_triggered(o, bar):
                        o.status = OrderStatus.TRIGGERED
                        o.updated_at_utc = bts
                        self.state.orders[o.order_id] = o
                continue

            # v1 position rule: no flip-in-one-step. If a fill would flip, reject order.
            f_tmp = Fill(
                fill_id="__tmp__",
                order_id=o.order_id,
                symbol=o.symbol,
                side=o.side,
                qty=int(o.qty),
                price=float(px),
                ts_utc=bts,
            )
            if would_flip_position(self.state.position, f_tmp):
                o.status = OrderStatus.REJECTED
                o.updated_at_utc = bts
                self.state.orders[o.order_id] = o
                continue
            f = Fill(
                fill_id=str(uuid4()),
                order_id=o.order_id,
                symbol=o.symbol,
                side=o.side,
                qty=int(o.qty),
                price=float(px),
                ts_utc=bts,
            )
            fills.append(f)
            self._on_fill(o, f)

        self.state.fills.extend(fills)
        self.state.last_processed_utc = bts
        self._snapshot_equity(bar_close=float(bar.close), ts_utc=bts)
        return fills

    def process_bars(self, bars_1m: pd.DataFrame) -> list[Fill]:
        """
        Process a batch of 1-minute bars.

        bars_1m must include: ts_utc, open, high, low, close (UTC-aware ts_utc).
        """

        if bars_1m.empty:
            return []
        req = ["ts_utc", "open", "high", "low", "close"]
        for c in req:
            if c not in bars_1m.columns:
                raise ValueError(f"bars_1m missing column: {c}")

        df = bars_1m.copy()
        df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="raise")
        df = df.sort_values("ts_utc", ascending=True, kind="mergesort").reset_index(drop=True)

        all_fills: list[Fill] = []
        for _, r in df.iterrows():
            bar = Bar1m(
                ts_utc=r["ts_utc"],
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
                volume=r.get("volume", None),
            )
            all_fills.extend(self.process_bar(bar))
        return all_fills

    # -----------------------------
    # Helpers
    # -----------------------------

    def _get(self, order_id: str) -> Order:
        if order_id not in self.state.orders:
            raise KeyError(f"order not found: {order_id}")
        return self.state.orders[order_id]

    def _on_fill(self, order: Order, fill: Fill) -> None:
        # Mark order filled.
        order.status = OrderStatus.FILLED
        order.updated_at_utc = _as_utc(fill.ts_utc)
        self.state.orders[order.order_id] = order

        # Apply position update.
        self.state.position = apply_fill_to_position(self.state.position, fill)

        # OCO: if one fills, cancel siblings.
        if order.oco_group_id:
            self.cancel_oco_group(order.oco_group_id, keep_order_id=order.order_id, ts_utc=fill.ts_utc)

        # If this is an entry fill, arm its bracket exit legs (children).
        # We use:
        # - exit legs status stays PENDING until their active_from_utc is set to after entry fill
        # - active_from_utc is set to next 1-minute bar (no hindsight)
        if order.parent_order_id is None:
            arm_from = _minute_after(fill.ts_utc)
            for oid, o in list(self.state.orders.items()):
                if o.parent_order_id != order.order_id:
                    continue
                if o.status in (OrderStatus.CANCELED, OrderStatus.FILLED, OrderStatus.REJECTED):
                    continue
                o.active_from_utc = arm_from
                o.status = OrderStatus.PENDING
                o.updated_at_utc = _as_utc(fill.ts_utc)
                self.state.orders[oid] = o

    def _snapshot_equity(self, *, bar_close: float, ts_utc: pd.Timestamp) -> None:
        pos = self.state.position
        u = unrealized_pnl(pos, bar_close)
        equity = self.starting_equity + float(pos.realized_pnl) + float(u)
        self.state.equity.append(
            EquitySnapshot(
                ts_utc=_as_utc(ts_utc),
                symbol=pos.symbol,
                position_side=pos.side,
                position_qty=int(pos.qty),
                avg_entry=pos.avg_entry,
                last_price=float(bar_close),
                unrealized_pnl=float(u),
                realized_pnl=float(pos.realized_pnl),
                equity=float(equity),
            )
        )


def activation_from_5m_bar_close(seen_5m_bar_close_utc: pd.Timestamp) -> pd.Timestamp:
    """
    If a user places an order after seeing a completed 5-minute bar,
    make it active from the next eligible 1-minute bar.
    """

    return _minute_after(seen_5m_bar_close_utc)


def _exit_side_for_entry(entry_side: OrderSide) -> OrderSide:
    if entry_side == OrderSide.BUY:
        return OrderSide.SELL
    if entry_side == OrderSide.SELL_SHORT:
        return OrderSide.BUY_TO_COVER
    raise ValueError("Entry side must be BUY or SELL_SHORT in v1")


def _working_sort_key(o: Order) -> tuple:
    # Conservative and deterministic:
    # 1) entries first
    # 2) stops before targets within same bracket
    # 3) stable by created time then id
    is_exit = 1 if o.parent_order_id else 0
    exit_kind = 0
    if o.parent_order_id:
        if o.type == OrderType.STOP:
            exit_kind = 0
        elif o.type == OrderType.LIMIT:
            exit_kind = 1
        else:
            exit_kind = 2
    return (is_exit, exit_kind, str(o.created_at_utc), o.order_id)


def _stop_limit_triggered(o: Order, bar: Bar1m) -> bool:
    """
    Detect whether a STOP_LIMIT order is triggered on this bar (even if it didn't fill).
    """

    if o.type != OrderType.STOP_LIMIT or o.stop_price is None:
        return False
    sp = float(o.stop_price)
    if o.side in (OrderSide.BUY, OrderSide.BUY_TO_COVER):
        return float(bar.open) >= sp or float(bar.high) >= sp
    return float(bar.open) <= sp or float(bar.low) <= sp

