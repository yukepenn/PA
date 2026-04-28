from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from dash import Dash

from .replay_dash.callbacks import register
from .replay_dash.layout import build_layout
from ..data.ibkr_raw_ingest import RAW_BASE_DEFAULT, RAW_REL


def _suggest_default_date_et(symbol: str) -> str:
    """
    Pick a sensible default date (ET) that likely exists locally.
    Falls back to today's ET date if no local data found.
    """
    try:
        root = Path(RAW_BASE_DEFAULT) / RAW_REL / f"symbol={symbol.upper()}"
        if root.exists():
            files = sorted(root.rglob("data.parquet"))
            if files:
                df = pd.read_parquet(files[-1], columns=["ts_utc"])
                if not df.empty:
                    ts = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce").dropna()
                    if not ts.empty:
                        return str(ts.max().tz_convert("America/New_York").date())
    except Exception:
        pass
    return str(pd.Timestamp.now(tz="UTC").tz_convert("America/New_York").date())


def create_app() -> Dash:
    app = Dash(__name__, title="PA Replay Trainer (MVP)", suppress_callback_exceptions=True)
    app.server.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

    @app.server.after_request
    def _no_cache(resp):  # type: ignore[no-redef]
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    app.layout = build_layout(_suggest_default_date_et("SPY"))
    register(app)
    return app


def main() -> None:
    app = create_app()
    port = int(os.getenv("PA_DASH_PORT", "8050"))
    app.run(debug=False, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()

