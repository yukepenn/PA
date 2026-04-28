from __future__ import annotations

import pandas as pd


def resample_1min_to_5min(df_1min: pd.DataFrame) -> pd.DataFrame:
    """
    Resample 1-minute canonical bars to 5-minute bars.

    Output `ts_utc` is the 5-min bar timestamp (right label / bar close time).
    This is suitable for replay where each step reveals one completed 5-min bar.
    """
    if df_1min.empty:
        return df_1min.copy()

    df = df_1min.copy()
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="raise")

    required = {"ts_utc", "symbol", "open", "high", "low", "close", "volume"}
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns for resampling: {missing}")

    symbol = str(df["symbol"].iloc[0])
    rth_only = bool(df["rth_only"].iloc[0]) if "rth_only" in df.columns else True

    df = df.sort_values("ts_utc", ascending=True, kind="mergesort")
    df = df.set_index("ts_utc")

    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    ohlcv = df.resample("5min", label="right", closed="right").agg(agg).dropna(subset=["open", "close"])

    out = ohlcv.reset_index()
    out.insert(1, "symbol", symbol)
    out["bar_size"] = "5min"
    out["source"] = "derived"
    out["rth_only"] = rth_only
    return out

