from __future__ import annotations

import io

import pandas as pd


def df_from_store_split_json(data: str | None) -> pd.DataFrame:
    """
    Dash `dcc.Store` holds DataFrames encoded by `to_json(orient="split")`.

    Pandas is deprecating passing literal JSON strings directly to `read_json`,
    so we wrap the string in a file-like object.
    """
    if not data:
        return pd.DataFrame()
    return pd.read_json(io.StringIO(data), orient="split")

