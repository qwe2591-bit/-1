"""Tunable parameters for the signal scan.

All thresholds live here so the pattern can be adjusted without touching
detection logic.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ScanConfig:
    # 급등 캔들 조건: 전일 종가 대비 종가 등락률(%) 최소치, 양봉(종가>시가) 여부
    surge_min_pct: float = 15.0
    require_bullish_surge_candle: bool = True

    # 눌림목 조건: 급등 다음 거래일들의 전일 종가 대비 등락률(%) 허용 범위
    pullback_min_pct: float = -5.0
    pullback_max_pct: float = 3.0

    # 눌림목 캔들이 이 범위 내에서 연속으로 나와야 하는 최소/최대 거래일 수
    pullback_min_days: int = 2
    pullback_max_days: int = 3

    # 눌림목 구간 중 하루라도 이 범위를 벗어나면(상한 돌파 또는 하한 이탈)
    # 패턴이 깨진 것으로 간주하고 그 지점에서 카운트를 종료한다.
    break_ends_pattern: bool = True
