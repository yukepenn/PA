from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from ib_insync import IB, Stock, util


@dataclass(frozen=True)
class IbkrConfig:
    host: str = "127.0.0.1"
    port: int = 4002
    client_id: int = 19


def _repo_root() -> Path:
    """
    Resolve repo root from this file location:
    <repo>/src/pa/data/ibkr_raw_ingest.py -> parents[3] == <repo>
    """
    return Path(__file__).resolve().parents[3]


def resolve_tradingdata_base() -> Path:
    """
    Choose a sensible default base directory for maintained data.

    Priority:
    1) Explicit override via env var `PA_TRADINGDATA_BASE`
    2) `<repo>/TradingData` if it exists (portable across machines/drives)
    3) `./TradingData` relative to current working directory if it exists
    4) Fallback to `D:\\TradingData` (legacy default)
    """
    env = (os.getenv("PA_TRADINGDATA_BASE") or "").strip()
    if env:
        return Path(env)

    repo_td = _repo_root() / "TradingData"
    if repo_td.exists():
        return repo_td

    cwd_td = Path.cwd() / "TradingData"
    if cwd_td.exists():
        return cwd_td

    return Path(r"D:\TradingData")


RAW_BASE_DEFAULT = resolve_tradingdata_base()
RAW_REL = Path(r"raw\ibkr\bars_1min")
BAR_SIZE_1MIN_CANONICAL = "1min"


def connect_ib(cfg: IbkrConfig) -> IB:
    last_err: Exception | None = None
    for off in range(0, 20):
        ib = IB()
        client_id = int(cfg.client_id) + off
        try:
            ib.connect(cfg.host, cfg.port, clientId=client_id, readonly=True)
            if ib.isConnected():
                return ib
            last_err = RuntimeError("connect() returned but isConnected() is False")
        except Exception as e:  # noqa: BLE001
            last_err = e
        try:
            ib.disconnect()
        except Exception:  # noqa: BLE001
            pass

    raise RuntimeError(
        "Failed to connect to IBKR after trying multiple client_id values. "
        "Is IB Gateway/TWS running with API enabled, and are client IDs free?"
    ) from last_err


def fetch_bars_1min(
    ib: IB,
    *,
    symbol: str,
    duration: str = "2 D",
    what: str = "TRADES",
    rth_only: bool = True,
    end_utc: pd.Timestamp | None = None,
) -> pd.DataFrame:
    sym = symbol.upper().strip()

    # Stocks/ETFs only for now (keeps scope tight and predictable)
    contract = Stock(sym, "SMART", "USD")
    qualified = ib.qualifyContracts(contract)
    if not qualified:
        raise RuntimeError(f"Failed to qualify contract for symbol={sym!r}.")
    contract = qualified[0]
    if not isinstance(contract, Stock):
        raise RuntimeError("Only stocks/ETFs are supported (Stock contract expected).")

    end_dt = ""
    if end_utc is not None:
        end_ts = pd.Timestamp(end_utc)
        if end_ts.tzinfo is None:
            raise ValueError("end_utc must be timezone-aware UTC.")
        end_ts = end_ts.tz_convert("UTC")
        end_dt = end_ts.to_pydatetime()

    bars = ib.reqHistoricalData(
        contract=contract,
        endDateTime=end_dt,
        durationStr=duration,
        barSizeSetting="1 min",
        whatToShow=what,
        useRTH=bool(rth_only),
        keepUpToDate=False,
        formatDate=2,
    )
    if not bars:
        raise RuntimeError("No bars returned (subscription / permissions / pacing / time range).")

    df = util.df(bars)
    if df is None or df.empty:
        raise RuntimeError("Bars returned but parsed DataFrame is empty.")
    return df


CANONICAL_COLS = [
    "ts_utc",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "bar_size",
    "source",
    "rth_only",
]


def to_canonical_bars_1min(
    df_ib: pd.DataFrame,
    *,
    symbol: str,
    rth_only: bool = True,
) -> pd.DataFrame:
    if "date" not in df_ib.columns:
        raise ValueError("IBKR bars DataFrame missing expected 'date' column.")

    ts = pd.to_datetime(df_ib["date"], utc=True, errors="raise")
    out = pd.DataFrame(
        {
            "ts_utc": ts,
            "symbol": symbol.upper().strip(),
            "open": pd.to_numeric(df_ib["open"], errors="coerce"),
            "high": pd.to_numeric(df_ib["high"], errors="coerce"),
            "low": pd.to_numeric(df_ib["low"], errors="coerce"),
            "close": pd.to_numeric(df_ib["close"], errors="coerce"),
            "volume": pd.to_numeric(df_ib.get("volume", 0), errors="coerce").fillna(0).astype("int64"),
            "bar_size": BAR_SIZE_1MIN_CANONICAL,
            "source": "ibkr",
            "rth_only": bool(rth_only),
        }
    )

    out = out.dropna(subset=["ts_utc"]).copy()
    out = out[CANONICAL_COLS]

    if out["ts_utc"].dt.tz is None:
        out["ts_utc"] = out["ts_utc"].dt.tz_localize("UTC")
    else:
        out["ts_utc"] = out["ts_utc"].dt.tz_convert("UTC")

    return out


def validate_canonical_bars_1min(df: pd.DataFrame) -> None:
    missing = [c for c in CANONICAL_COLS if c not in df.columns]
    extra = [c for c in df.columns if c not in CANONICAL_COLS]
    if missing or extra:
        raise ValueError(f"Canonical schema mismatch. missing={missing} extra={extra}")

    if df.empty:
        return

    ts = pd.to_datetime(df["ts_utc"], utc=True, errors="raise")
    if ts.dt.tz is None or str(ts.dt.tz) != "UTC":
        raise ValueError("ts_utc must be timezone-aware UTC.")

    if df["symbol"].isna().any() or (df["symbol"].astype(str).str.strip() == "").any():
        raise ValueError("symbol must be non-empty.")

    if (df["bar_size"] != BAR_SIZE_1MIN_CANONICAL).any():
        raise ValueError(f"bar_size must be exactly {BAR_SIZE_1MIN_CANONICAL!r}.")

    if (df["source"] != "ibkr").any():
        raise ValueError("source must be exactly 'ibkr'.")

    if df["rth_only"].isna().any():
        raise ValueError("rth_only must be non-null boolean.")


def monthly_partition_path(base_dir: Path, *, symbol: str, year: int, month: int) -> Path:
    sym = symbol.upper().strip()
    return (
        Path(base_dir)
        / RAW_REL
        / f"symbol={sym}"
        / f"year={year:04d}"
        / f"month={month:02d}"
        / "data.parquet"
    )


def _atomic_write_parquet(df: pd.DataFrame, dest: Path) -> None:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(prefix=dest.name + ".", suffix=".tmp", dir=str(dest.parent))
    os.close(fd)
    tmp = Path(tmp_path)
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def upsert_monthly_parquet(base_dir: Path, canonical_df: pd.DataFrame) -> list[Path]:
    if canonical_df.empty:
        return []

    df = canonical_df.copy()
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="raise")
    validate_canonical_bars_1min(df[CANONICAL_COLS])

    df["_year"] = df["ts_utc"].dt.year.astype("int64")
    df["_month"] = df["ts_utc"].dt.month.astype("int64")

    written: list[Path] = []
    for (sym, year, month), part in df.groupby(["symbol", "_year", "_month"], sort=False):
        dest = monthly_partition_path(Path(base_dir), symbol=sym, year=int(year), month=int(month))

        part = part.drop(columns=["_year", "_month"])
        part = part[CANONICAL_COLS]

        if dest.exists():
            existing = pd.read_parquet(dest)
            existing["ts_utc"] = pd.to_datetime(existing["ts_utc"], utc=True, errors="raise")
            merged = pd.concat([existing, part], ignore_index=True)
        else:
            merged = part

        merged = merged.drop_duplicates(subset=["symbol", "ts_utc"], keep="last")
        merged = merged.sort_values(["ts_utc"], ascending=True, kind="mergesort").reset_index(drop=True)
        merged = merged[CANONICAL_COLS]
        validate_canonical_bars_1min(merged)

        _atomic_write_parquet(merged, dest)
        written.append(dest)

    return written

