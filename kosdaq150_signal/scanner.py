"""CLI: scan all KOSDAQ 150 constituents for the surge+consolidation buy
pattern, either as a live end-of-day scan or a historical backtest.

Usage:
    python -m kosdaq150_signal.scanner live
    python -m kosdaq150_signal.scanner backtest --from 20260101 --to 20260820
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta

import pandas as pd

from .config import ScanConfig
from .data_fetcher import get_kosdaq150_tickers, get_ohlcv
from .signal import BuySignal, find_signals, latest_signal


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y%m%d").date()


def run_live(config: ScanConfig, lookback_days: int, sleep_sec: float) -> list[BuySignal]:
    today = date.today()
    from_date = today - timedelta(days=lookback_days)

    tickers = get_kosdaq150_tickers(today)
    print(f"[INFO] KOSDAQ150 constituents: {len(tickers)}", file=sys.stderr)

    hits: list[BuySignal] = []
    for i, (ticker, name) in enumerate(tickers, start=1):
        try:
            df = get_ohlcv(ticker, from_date, today)
            sig = latest_signal(df, ticker, name, config)
            if sig:
                hits.append(sig)
                print(f"[SIGNAL] {name}({ticker}) -> {sig.as_dict()}", file=sys.stderr)
        except Exception as err:
            print(f"[WARN] {name}({ticker}) skipped: {err}", file=sys.stderr)
        if sleep_sec:
            time.sleep(sleep_sec)
        if i % 25 == 0:
            print(f"[INFO] scanned {i}/{len(tickers)}", file=sys.stderr)
    return hits


def run_backtest(
    config: ScanConfig, from_date: date, to_date: date, sleep_sec: float
) -> list[BuySignal]:
    tickers = get_kosdaq150_tickers(to_date)
    print(f"[INFO] KOSDAQ150 constituents: {len(tickers)}", file=sys.stderr)

    hits: list[BuySignal] = []
    for i, (ticker, name) in enumerate(tickers, start=1):
        try:
            df = get_ohlcv(ticker, from_date, to_date)
            hits.extend(find_signals(df, ticker, name, config))
        except Exception as err:
            print(f"[WARN] {name}({ticker}) skipped: {err}", file=sys.stderr)
        if sleep_sec:
            time.sleep(sleep_sec)
        if i % 25 == 0:
            print(f"[INFO] scanned {i}/{len(tickers)}", file=sys.stderr)
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    live_p = sub.add_parser("live", help="Scan today's data for a fresh buy signal.")
    live_p.add_argument("--lookback-days", type=int, default=20)
    live_p.add_argument("--sleep-sec", type=float, default=0.2, help="delay between KRX requests")
    live_p.add_argument("--out", type=str, default=None, help="optional CSV output path")

    bt_p = sub.add_parser("backtest", help="Scan a historical date range for all matches.")
    bt_p.add_argument("--from", dest="from_date", type=_parse_date, required=True)
    bt_p.add_argument("--to", dest="to_date", type=_parse_date, required=True)
    bt_p.add_argument("--sleep-sec", type=float, default=0.2)
    bt_p.add_argument("--out", type=str, default=None)

    args = parser.parse_args(argv)
    config = ScanConfig()

    if args.mode == "live":
        hits = run_live(config, args.lookback_days, args.sleep_sec)
    else:
        hits = run_backtest(config, args.from_date, args.to_date, args.sleep_sec)

    rows = [h.as_dict() for h in hits]
    result_df = pd.DataFrame(rows)
    if result_df.empty:
        print("매수 신호 없음 (no signals found).")
    else:
        print(result_df.to_string(index=False))
        if args.out:
            result_df.to_csv(args.out, index=False, encoding="utf-8-sig")
            print(f"Saved -> {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
