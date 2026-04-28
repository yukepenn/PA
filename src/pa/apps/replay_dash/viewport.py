"""Session-time viewport helpers for the replay chart (display only; no sim/replay semantics)."""

from __future__ import annotations

import pandas as pd


def rth_session_x_range_utc(date_et: str) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """
    Full regular-hours session on the ET calendar day: 09:30–16:00 America/New_York, as UTC.
    Used for default x-axis range so bars sit at true session-time positions.
    """
    try:
        et = "America/New_York"
        open_et = pd.Timestamp(f"{date_et} 09:30:00").tz_localize(et).tz_convert("UTC")
        close_et = pd.Timestamp(f"{date_et} 16:00:00").tz_localize(et).tz_convert("UTC")
        return open_et, close_et
    except Exception:
        return None
