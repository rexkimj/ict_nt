"""
Fair Value Gap (FVG) / Imbalance Detector for ICT Trading

FVG는 3개의 연속된 캔들에서 발생하는 가격 공백(갭)으로,
시장이 불균형 상태로 빠르게 이동했음을 나타냅니다.
가격은 보통 FVG를 다시 채우러 돌아오는 경향이 있습니다.
"""
from typing import List, Optional
from dataclasses import dataclass
from enum import Enum
import numpy as np


class FVGType(Enum):
    """FVG 타입"""
    BULLISH = "bullish"  # 상승 FVG (매수 기회)
    BEARISH = "bearish"  # 하락 FVG (매도 기회)


@dataclass
class FairValueGap:
    """Fair Value Gap 데이터 구조"""
    type: FVGType
    start_idx: int  # FVG 시작 캔들 인덱스
    gap_high: float  # 갭의 상단
    gap_low: float  # 갭의 하단
    filled_percentage: float = 0.0  # 채워진 비율 (0-100%)
    is_filled: bool = False  # 50% 이상 채워졌는지

    @property
    def midpoint(self) -> float:
        """FVG 중간값 (0.5 레벨)"""
        return (self.gap_high + self.gap_low) / 2

    @property
    def size(self) -> float:
        """FVG 크기"""
        return self.gap_high - self.gap_low


class FVGDetector:
    """
    Fair Value Gap (Imbalance) 감지기

    알고리즘:
    - Bullish FVG: 캔들1의 고가 < 캔들3의 저가
    - Bearish FVG: 캔들1의 저가 > 캔들3의 고가
    - 3개 캔들 패턴으로 구성
    """

    def __init__(
        self,
        min_gap_size: float = 0.1,  # 최소 갭 크기 (% of price)
        fill_threshold: float = 0.5,  # FVG가 채워졌다고 판단하는 비율
        lookback_period: int = 100
    ):
        """
        Parameters
        ----------
        min_gap_size : float
            FVG로 인정할 최소 갭 크기 (가격 대비 %)
        fill_threshold : float
            FVG가 채워졌다고 판단하는 비율 (0-1)
        lookback_period : int
            FVG를 탐색할 캔들 수
        """
        self.min_gap_size = min_gap_size
        self.fill_threshold = fill_threshold
        self.lookback_period = lookback_period

    def detect(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray
    ) -> List[FairValueGap]:
        """
        Fair Value Gap 감지

        Parameters
        ----------
        highs : np.ndarray
            고가 배열
        lows : np.ndarray
            저가 배열
        closes : np.ndarray
            종가 배열

        Returns
        -------
        List[FairValueGap]
            감지된 FVG 리스트
        """
        fvgs = []
        n = len(closes)

        if n < 3:
            return fvgs

        # 최근 lookback_period만큼만 분석
        start_idx = max(2, n - self.lookback_period)

        for i in range(start_idx, n):
            # 3캔들 패턴: i-2, i-1, i
            candle1_high = highs[i - 2]
            candle1_low = lows[i - 2]
            candle3_high = highs[i]
            candle3_low = lows[i]
            mid_price = closes[i - 1]

            # Bullish FVG 감지
            if candle1_high < candle3_low:
                gap_size = candle3_low - candle1_high
                gap_pct = (gap_size / mid_price) * 100

                if gap_pct >= self.min_gap_size:
                    fvg = FairValueGap(
                        type=FVGType.BULLISH,
                        start_idx=i - 2,
                        gap_high=candle3_low,
                        gap_low=candle1_high,
                        filled_percentage=0.0,
                        is_filled=False
                    )
                    fvgs.append(fvg)

            # Bearish FVG 감지
            elif candle1_low > candle3_high:
                gap_size = candle1_low - candle3_high
                gap_pct = (gap_size / mid_price) * 100

                if gap_pct >= self.min_gap_size:
                    fvg = FairValueGap(
                        type=FVGType.BEARISH,
                        start_idx=i - 2,
                        gap_high=candle1_low,
                        gap_low=candle3_high,
                        filled_percentage=0.0,
                        is_filled=False
                    )
                    fvgs.append(fvg)

        # FVG 채워짐 상태 업데이트
        self._update_fvg_fills(fvgs, highs, lows, closes)

        return fvgs

    def _update_fvg_fills(
        self,
        fvgs: List[FairValueGap],
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray
    ):
        """FVG가 얼마나 채워졌는지 업데이트"""
        current_idx = len(closes) - 1

        for fvg in fvgs:
            # FVG 생성 이후의 가격 움직임만 확인
            if fvg.start_idx >= current_idx:
                continue

            # 현재 가격이 FVG 범위에 있는지 확인
            current_high = highs[current_idx]
            current_low = lows[current_idx]

            if fvg.type == FVGType.BULLISH:
                # 상승 FVG는 위에서 아래로 채워짐
                if current_low <= fvg.gap_high:
                    # FVG 내부로 진입
                    fill_level = min(current_low, fvg.gap_high)
                    filled_amount = fvg.gap_high - fill_level
                    fvg.filled_percentage = (filled_amount / fvg.size) * 100

                    if fvg.filled_percentage >= (self.fill_threshold * 100):
                        fvg.is_filled = True

            else:  # BEARISH
                # 하락 FVG는 아래에서 위로 채워짐
                if current_high >= fvg.gap_low:
                    # FVG 내부로 진입
                    fill_level = max(current_high, fvg.gap_low)
                    filled_amount = fill_level - fvg.gap_low
                    fvg.filled_percentage = (filled_amount / fvg.size) * 100

                    if fvg.filled_percentage >= (self.fill_threshold * 100):
                        fvg.is_filled = True

    def get_unfilled_fvgs(
        self,
        fvgs: List[FairValueGap],
        fvg_type: Optional[FVGType] = None
    ) -> List[FairValueGap]:
        """
        미채워진 FVG 반환

        Parameters
        ----------
        fvgs : List[FairValueGap]
            전체 FVG 리스트
        fvg_type : Optional[FVGType]
            필터링할 타입 (None이면 전체)

        Returns
        -------
        List[FairValueGap]
            미채워진 FVG 리스트
        """
        unfilled = [fvg for fvg in fvgs if not fvg.is_filled]

        if fvg_type:
            unfilled = [fvg for fvg in unfilled if fvg.type == fvg_type]

        return unfilled

    def get_nearest_fvg(
        self,
        fvgs: List[FairValueGap],
        current_price: float,
        fvg_type: Optional[FVGType] = None
    ) -> Optional[FairValueGap]:
        """
        현재 가격에서 가장 가까운 FVG 반환

        Parameters
        ----------
        fvgs : List[FairValueGap]
            FVG 리스트
        current_price : float
            현재 가격
        fvg_type : Optional[FVGType]
            필터링할 타입

        Returns
        -------
        Optional[FairValueGap]
            가장 가까운 FVG (없으면 None)
        """
        unfilled = self.get_unfilled_fvgs(fvgs, fvg_type)

        if not unfilled:
            return None

        # 거리 계산
        nearest = min(
            unfilled,
            key=lambda fvg: abs(fvg.midpoint - current_price)
        )

        return nearest

    def filter_fvgs_by_fibonacci(
        self,
        fvgs: List[FairValueGap],
        range_high: float,
        range_low: float,
        fib_level: float = 0.5
    ) -> List[FairValueGap]:
        """
        피보나치 레벨 근처의 FVG만 필터링

        Parameters
        ----------
        fvgs : List[FairValueGap]
            FVG 리스트
        range_high : float
            레인지 고점
        range_low : float
            레인지 저점
        fib_level : float
            피보나치 레벨 (0-1)

        Returns
        -------
        List[FairValueGap]
            피보나치 레벨 근처의 FVG
        """
        fib_price = range_low + (range_high - range_low) * fib_level
        tolerance = (range_high - range_low) * 0.05  # 5% 허용 오차

        filtered = []
        for fvg in fvgs:
            if abs(fvg.midpoint - fib_price) <= tolerance:
                filtered.append(fvg)

        return filtered
