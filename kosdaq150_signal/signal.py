"""Pattern detection: surge candle followed by a short consolidation.

Pattern definition (as specified by the user):
  1) A daily candle closes up >= surge_min_pct vs the previous close, and is
     bullish (close > open) -- a strong breakout day.
  2) Over the trading days *immediately following* it, each day's close-vs-
     prior-close return stays inside [pullback_min_pct, pullback_max_pct]
     (default -5% ~ +3%), i.e. a shallow pullback/consolidation.
  3) As soon as that consolidation streak has lasted 2 or 3 trading days
     (inclusive range from config), a BUY signal fires -- the stock held
     its breakout gains through a brief digestion phase.

The core check only ever looks *backward* from a given day, exactly what a
live scanner running after each day's close can do -- it never assumes
knowledge of days that haven't happened yet. ``find_signals`` (used for
backtesting) simply replays that same check on every historical day, so a
backtest reproduces exactly what the live scanner would have flagged on
each day at the time. If the streak keeps extending in-range past
``pullback_max_days``, that day itself stops qualifying (the window
already closed), but earlier days in the same streak that legitimately
fired are not retroactively erased -- that mirrors reality, where a buy
signal from two days ago already happened by the time day four rolls
around.

The detector is data-source agnostic: it operates on a plain pandas
DataFrame indexed by date with 'open', 'high', 'low', 'close' columns
(English, lower-case). Adapters for specific data sources (e.g. pykrx,
which returns Korean column names) live in data_fetcher.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from .config import ScanConfig


@dataclass(frozen=True)
class BuySignal:
    ticker: str
    name: str
    surge_date: date
    surge_pct: float
    consolidation_start: date
    consolidation_end: date
    consolidation_days: int
    signal_date: date

    def as_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "surge_date": self.surge_date.isoformat(),
            "surge_pct": round(self.surge_pct, 2),
            "consolidation_start": self.consolidation_start.isoformat(),
            "consolidation_end": self.consolidation_end.isoformat(),
            "consolidation_days": self.consolidation_days,
            "signal_date": self.signal_date.isoformat(),
        }


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    required = {"open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"OHLC dataframe missing columns: {sorted(missing)}")
    out = df.sort_index().copy()
    out["prev_close"] = out["close"].shift(1)
    out["pct_change"] = (out["close"] / out["prev_close"] - 1.0) * 100.0
    out["is_bullish"] = out["close"] > out["open"]
    return out


def _to_date(value) -> date:
    if isinstance(value, date):
        return value
    return pd.Timestamp(value).date()


def _signal_as_of(
    df: pd.DataFrame,
    pos: int,
    ticker: str,
    name: str,
    cfg: ScanConfig,
) -> BuySignal | None:
    """Check whether ``pos`` (row index into the prepped df) is a valid
    signal day: today is in-range, and walking backward the consolidation
    streak is 2~3 days long, immediately preceded by a qualifying surge."""
    if pos < 1:
        return None

    today_pct = df.iloc[pos]["pct_change"]
    if pd.isna(today_pct) or not (cfg.pullback_min_pct <= today_pct <= cfg.pullback_max_pct):
        return None

    consol_days = 0
    j = pos
    while j >= 1:
        pct = df.iloc[j]["pct_change"]
        if pd.isna(pct) or not (cfg.pullback_min_pct <= pct <= cfg.pullback_max_pct):
            break
        consol_days += 1
        j -= 1
        if consol_days > cfg.pullback_max_days:
            return None  # streak already ran past the valid window

    if not (cfg.pullback_min_days <= consol_days <= cfg.pullback_max_days):
        return None

    surge_row_pos = j
    if surge_row_pos < 0:
        return None
    surge_row = df.iloc[surge_row_pos]
    surge_pct = surge_row["pct_change"]
    is_surge = (
        pd.notna(surge_pct)
        and surge_pct >= cfg.surge_min_pct
        and (surge_row["is_bullish"] if cfg.require_bullish_surge_candle else True)
    )
    if not is_surge:
        return None

    idx = df.index
    return BuySignal(
        ticker=ticker,
        name=name,
        surge_date=_to_date(idx[surge_row_pos]),
        surge_pct=float(surge_pct),
        consolidation_start=_to_date(idx[surge_row_pos + 1]),
        consolidation_end=_to_date(idx[pos]),
        consolidation_days=consol_days,
        signal_date=_to_date(idx[pos]),
    )


def latest_signal(
    ohlc: pd.DataFrame,
    ticker: str,
    name: str = "",
    config: ScanConfig | None = None,
) -> BuySignal | None:
    """Live-scan variant: is *today* (the last row in ``ohlc``) the close of
    a qualifying 2~3 day consolidation that just followed a surge candle?

    Intended to run once per trading day after the close. Returns a
    ``BuySignal`` (buy candidate for the next session) or ``None``.
    """
    cfg = config or ScanConfig()
    df = _prep(ohlc)
    if len(df) < 2:
        return None
    return _signal_as_of(df, len(df) - 1, ticker, name, cfg)


def find_signals(
    ohlc: pd.DataFrame,
    ticker: str,
    name: str = "",
    config: ScanConfig | None = None,
) -> list[BuySignal]:
    """Backtest variant: replay the live check on every historical day and
    return every day that would have fired a signal.

    ``ohlc`` must be indexed by trading date (ascending or not -- it is
    sorted internally) with columns: open, high, low, close.
    """
    cfg = config or ScanConfig()
    df = _prep(ohlc)
    signals: list[BuySignal] = []
    for pos in range(1, len(df)):
        sig = _signal_as_of(df, pos, ticker, name, cfg)
        if sig is not None:
            signals.append(sig)
    return signals
