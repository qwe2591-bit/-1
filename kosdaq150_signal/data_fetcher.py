"""KRX data access via pykrx.

Isolated in its own module so the detection logic (signal.py) stays
independent of the data source and is easy to unit-test with synthetic
DataFrames.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta

import pandas as pd

try:
    from pykrx import stock
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "pykrx is required. Install with: pip install -r requirements.txt"
    ) from exc

_KOSDAQ150_NAME_HINT = "코스닥 150"


def _fmt(d: date) -> str:
    return d.strftime("%Y%m%d")


def resolve_kosdaq150_index_ticker(as_of: date) -> str:
    """Find the KOSDAQ 150 index ticker code (defaults to '2203' but is
    looked up by name so this keeps working if KRX ever renumbers it)."""
    for ticker in stock.get_index_ticker_list(_fmt(as_of), market="KOSDAQ"):
        try:
            name = stock.get_index_ticker_name(ticker)
        except Exception:
            continue
        if "150" in name and "코스닥" in name:
            return ticker
    return "2203"  # known KOSDAQ 150 index code as of 2026


def get_kosdaq150_tickers(as_of: date | None = None) -> list[tuple[str, str]]:
    """Return [(ticker, name), ...] for current KOSDAQ 150 constituents."""
    as_of = as_of or date.today()
    index_ticker = resolve_kosdaq150_index_ticker(as_of)

    d = as_of
    tickers: list[str] = []
    # Constituent snapshots are only published for trading days; walk
    # backwards a few days in case as_of is a weekend/holiday.
    for _ in range(10):
        tickers = stock.get_index_portfolio_deposit_file(_fmt(d), index_ticker)
        if tickers:
            break
        d -= timedelta(days=1)

    result = []
    for t in tickers:
        try:
            name = stock.get_market_ticker_name(t)
        except Exception:
            name = ""
        result.append((t, name))
    return result


_COLUMN_MAP = {
    "시가": "open",
    "고가": "high",
    "저가": "low",
    "종가": "close",
    "거래량": "volume",
}


def get_ohlcv(
    ticker: str,
    from_date: date,
    to_date: date,
    retries: int = 3,
    retry_delay_sec: float = 1.5,
) -> pd.DataFrame:
    """Fetch daily OHLCV for one ticker, English lower-case columns,
    indexed by trading date ascending."""
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            df = stock.get_market_ohlcv(_fmt(from_date), _fmt(to_date), ticker)
            break
        except Exception as err:  # network hiccups / KRX throttling
            last_err = err
            time.sleep(retry_delay_sec * (attempt + 1))
    else:
        raise RuntimeError(f"Failed to fetch OHLCV for {ticker}") from last_err

    df = df.rename(columns=_COLUMN_MAP)
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    df = df[keep].sort_index()
    df.index.name = "date"
    return df
