import pandas as pd
import pytest

from kosdaq150_signal.config import ScanConfig
from kosdaq150_signal.signal import find_signals, latest_signal


def make_df(closes, opens=None):
    """Build a minimal OHLC frame from a list of closes.

    opens defaults to slightly below each close so every day is bullish;
    pass explicit opens to make a specific day bearish (close < open).
    """
    n = len(closes)
    dates = pd.date_range("2026-01-01", periods=n, freq="B")
    if opens is None:
        opens = [c * 0.99 for c in closes]
    highs = [max(o, c) * 1.001 for o, c in zip(opens, closes)]
    lows = [min(o, c) * 0.999 for o, c in zip(opens, closes)]
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes}, index=dates
    )


def test_surge_plus_2day_consolidation_triggers_signal():
    # base 1000 -> surge +20% (bullish) -> two days within -5%..+3%
    closes = [1000, 1200, 1210, 1180]  # +20%, +0.83%, -2.48%
    df = make_df(closes)
    signals = find_signals(df, "999999", "테스트종목")
    assert len(signals) == 1
    sig = signals[0]
    assert sig.consolidation_days == 2
    assert sig.surge_pct == pytest.approx(20.0)


def test_surge_plus_3day_consolidation_triggers_signal_on_day2_and_day3():
    closes = [1000, 1180, 1190, 1170, 1160]  # +18%, +0.85%, -1.68%, -0.85%
    df = make_df(closes)
    signals = find_signals(df, "999999", "테스트종목")
    # Fires once the streak hits 2 days, and again as it extends to 3 --
    # both are valid, actionable signal days within the 2~3 day window.
    assert [s.consolidation_days for s in signals] == [2, 3]


def test_only_1day_consolidation_does_not_trigger():
    closes = [1000, 1180, 1190, 1300]  # day after surge ok, then breaks +3% cap
    df = make_df(closes)
    signals = find_signals(df, "999999", "테스트종목")
    assert signals == []


def test_streak_extending_past_3days_only_fires_on_days_2_and_3():
    # day1 after surge (idx2) alone: too early (1 day).
    # day2 after surge (idx3): 2-day streak -> fires.
    # day3 after surge (idx4): 3-day streak -> fires.
    # day4 after surge (idx5): streak now 4 days -> window closed, no fire
    #   on that specific day (the earlier signals on idx3/idx4 already
    #   happened and are not retroactively cancelled).
    closes = [1000, 1180, 1190, 1180, 1170, 1160]
    df = make_df(closes)
    signals = find_signals(df, "999999", "테스트종목")
    assert [s.consolidation_days for s in signals] == [2, 3]


def test_bearish_surge_candle_excluded_by_default():
    # close is +20% vs prior close, but candle itself is bearish (close < open)
    closes = [1000, 1200, 1210, 1180]
    opens = [990, 1250, 1215, 1185]  # 2nd day open > close -> bearish
    df = make_df(closes, opens=opens)
    signals = find_signals(df, "999999", "테스트종목")
    assert signals == []


def test_surge_below_threshold_ignored():
    closes = [1000, 1100, 1105, 1090]  # only +10%
    df = make_df(closes)
    signals = find_signals(df, "999999", "테스트종목")
    assert signals == []


def test_pullback_breaking_lower_bound_ends_pattern():
    closes = [1000, 1200, 900, 890]  # -25% day breaks the -5% floor
    df = make_df(closes)
    signals = find_signals(df, "999999", "테스트종목")
    assert signals == []


def test_latest_signal_fires_on_2nd_consolidation_day():
    closes = [1000, 1200, 1210, 1220]  # today (idx3) is the 2nd consolidation day
    df = make_df(closes)
    sig = latest_signal(df, "999999", "테스트종목")
    assert sig is not None
    assert sig.consolidation_days == 2


def test_latest_signal_none_when_today_breaks_range():
    closes = [1000, 1200, 1300]  # today's +8.3% breaks the +3% cap
    df = make_df(closes)
    sig = latest_signal(df, "999999", "테스트종목")
    assert sig is None


def test_latest_signal_none_before_minimum_days_met():
    closes = [1000, 1200]  # only the surge day exists so far
    df = make_df(closes)
    sig = latest_signal(df, "999999", "테스트종목")
    assert sig is None


def test_custom_config_thresholds():
    cfg = ScanConfig(surge_min_pct=10.0, pullback_min_days=1, pullback_max_days=1)
    closes = [1000, 1100, 1105]
    df = make_df(closes)
    signals = find_signals(df, "999999", "테스트종목", cfg)
    assert len(signals) == 1
    assert signals[0].consolidation_days == 1
