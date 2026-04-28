from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Action(str, Enum):
    LONG = "Long"
    SHORT = "Short"
    PASS = "Pass"


@dataclass(frozen=True)
class ReplayConfig:
    timeframe: str = "5min"


@dataclass
class ReplayState:
    symbol: str
    date_et: str  # YYYY-mm-dd
    index: int = -1  # last revealed bar index

