from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4

import pandas as pd


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    SELL_SHORT = "SELL_SHORT"
    BUY_TO_COVER = "BUY_TO_COVER"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"  # accepted, but not active yet (activation time in future)
    WORKING = "WORKING"  # active and eligible to trigger/fill
    TRIGGERED = "TRIGGERED"  # stop-limit triggered; now behaves like a working limit order
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"


class TimeInForce(str, Enum):
    DAY = "DAY"
    GTC = "GTC"


@dataclass(frozen=True)
class Bar1m:
    ts_utc: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float | int | None = None


@dataclass
class Order:
    order_id: str
    symbol: str
    side: OrderSide
    type: OrderType
    qty: int
    tif: TimeInForce = TimeInForce.DAY

    # Prices (depending on type)
    limit_price: float | None = None
    stop_price: float | None = None

    # Activation semantics (no hindsight fills)
    placed_at_utc: pd.Timestamp | None = None
    active_from_utc: pd.Timestamp | None = None

    status: OrderStatus = OrderStatus.PENDING
    parent_order_id: str | None = None  # for bracket legs
    oco_group_id: str | None = None

    created_at_utc: pd.Timestamp = field(default_factory=lambda: pd.Timestamp.now(tz="UTC"))
    updated_at_utc: pd.Timestamp = field(default_factory=lambda: pd.Timestamp.now(tz="UTC"))

    @staticmethod
    def new_id() -> str:
        return str(uuid4())


@dataclass
class Fill:
    fill_id: str
    order_id: str
    symbol: str
    side: OrderSide
    qty: int
    price: float
    ts_utc: pd.Timestamp

    created_at_utc: pd.Timestamp = field(default_factory=lambda: pd.Timestamp.now(tz="UTC"))

    @staticmethod
    def new_id() -> str:
        return str(uuid4())


class PositionSide(str, Enum):
    FLAT = "FLAT"
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class Position:
    symbol: str
    side: PositionSide = PositionSide.FLAT
    qty: int = 0
    avg_entry: float | None = None
    realized_pnl: float = 0.0


@dataclass
class EquitySnapshot:
    ts_utc: pd.Timestamp
    symbol: str
    position_side: PositionSide
    position_qty: int
    avg_entry: float | None
    last_price: float
    unrealized_pnl: float
    realized_pnl: float
    equity: float


@dataclass
class BracketSpec:
    """
    Optional stop/target attached to an entry order.

    v1 constraints:
    - single symbol
    - single position
    - no partial fills
    """

    stop_loss: float | None = None
    take_profit: float | None = None


@dataclass
class SimSessionMeta:
    session_id: str
    symbol: str
    date_et: str
    created_at_utc: pd.Timestamp = field(default_factory=lambda: pd.Timestamp.now(tz="UTC"))
    notes: str = ""

    @staticmethod
    def new(symbol: str, date_et: str) -> "SimSessionMeta":
        return SimSessionMeta(session_id=str(uuid4()), symbol=symbol.upper().strip(), date_et=str(date_et))


@dataclass
class SimState:
    meta: SimSessionMeta
    position: Position
    orders: dict[str, Order] = field(default_factory=dict)
    fills: list[Fill] = field(default_factory=list)
    equity: list[EquitySnapshot] = field(default_factory=list)

    # Deterministic replay pointer for sim execution (1-minute bars)
    last_processed_utc: pd.Timestamp | None = None

