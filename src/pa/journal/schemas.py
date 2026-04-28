from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from ..replay.models import Action


@dataclass(frozen=True)
class DecisionRecord:
    decision_id: str
    ts_utc: pd.Timestamp
    symbol: str
    date_et: str  # YYYY-mm-dd
    timeframe: str  # e.g. "5min"
    action: Action  # Long/Short/Pass
    bar_index: int
    phase: str = "before"  # "before" or "after"

    # Lightweight training fields (keep optional and compact)
    setup: str = ""
    confidence: int | None = None  # 1-5
    quality: int | None = None  # 1-5 (post-review)
    planned_entry: float | None = None
    planned_stop: float | None = None
    planned_target: float | None = None
    pass_reason: str = ""
    notes: str = ""  # freeform (before or after)

    def to_row(self) -> dict:
        d = asdict(self)
        ts = pd.Timestamp(self.ts_utc)
        d["ts_utc"] = ts.tz_convert("UTC") if ts.tzinfo else ts.tz_localize("UTC")
        d["action"] = str(self.action.value)
        return d

