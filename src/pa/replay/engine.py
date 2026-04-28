from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .models import ReplayConfig, ReplayState


@dataclass
class ReplayEngine:
    """
    Minimal replay state machine.

    - Holds a full preloaded day (already filtered to the day)
    - Exposes a "visible" slice up to the current index (no future leakage)
    """

    bars: pd.DataFrame  # expected sorted ascending by ts_utc
    state: ReplayState
    cfg: ReplayConfig = ReplayConfig()

    def __post_init__(self) -> None:
        if self.bars.empty:
            raise ValueError("bars is empty")
        if "ts_utc" not in self.bars.columns:
            raise ValueError("bars missing ts_utc")
        self.bars = self.bars.copy()
        self.bars["ts_utc"] = pd.to_datetime(self.bars["ts_utc"], utc=True, errors="raise")
        self.bars = self.bars.sort_values("ts_utc", ascending=True, kind="mergesort").reset_index(drop=True)

    @property
    def max_index(self) -> int:
        return len(self.bars) - 1

    def reset(self) -> None:
        self.state.index = -1

    def step(self, n: int = 1) -> int:
        if n <= 0:
            return self.state.index
        self.state.index = min(self.max_index, self.state.index + int(n))
        return self.state.index

    def visible_bars(self) -> pd.DataFrame:
        if self.state.index < 0:
            return self.bars.iloc[0:0].copy()
        return self.bars.iloc[: self.state.index + 1].copy()

    def current_bar(self) -> pd.Series | None:
        if self.state.index < 0:
            return None
        return self.bars.iloc[self.state.index]

