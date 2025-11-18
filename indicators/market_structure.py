"""
Market Structure Analyzer for ICT Trading

시장 구조(Market Structure)는 가격이 만드는 고점(High)과 저점(Low)의 패턴으로
추세의 방향과 강도를 파악합니다.

주요 개념:
- Higher High (HH), Higher Low (HL): 상승 추세
- Lower High (LH), Lower Low (LL): 하락 추세
- Break of Structure (BOS): 추세 지속 신호
- Change of Character (CHoCH): 추세 전환 신호
"""
from typing import List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np


class MarketTrend(Enum):
    """시장 추세"""
    BULLISH = "bullish"  # 상승 추세
    BEARISH = "bearish"  # 하락 추세
    RANGING = "ranging"  # 횡보


class StructureType(Enum):
    """구조 변화 타입"""
    BOS = "bos"  # Break of Structure (추세 지속)
    CHOCH = "choch"  # Change of Character (추세 전환)


@dataclass
class SwingPoint:
    """스윙 포인트 (고점 또는 저점)"""
    idx: int
    price: float
    is_high: bool  # True면 고점, False면 저점

    def __repr__(self):
        point_type = "High" if self.is_high else "Low"
        return f"SwingPoint({point_type}, {self.price:.2f} at idx {self.idx})"


@dataclass
class StructureBreak:
    """구조 변화 이벤트"""
    type: StructureType
    trend: MarketTrend
    idx: int
    price: float
    broken_level: float  # 돌파된 레벨

    def __repr__(self):
        return f"{self.type.value.upper()} ({self.trend.value}) at {self.price:.2f}"


class MarketStructureAnalyzer:
    """
    시장 구조 분석기

    기능:
    1. Swing High/Low 식별
    2. 시장 추세 판단
    3. BOS/CHoCH 감지
    4. Higher High, Lower Low 등의 패턴 인식
    """

    def __init__(
        self,
        swing_lookback: int = 5,
        structure_lookback: int = 20
    ):
        """
        Parameters
        ----------
        swing_lookback : int
            스윙 포인트를 판단할 lookback 기간
        structure_lookback : int
            시장 구조를 분석할 lookback 기간
        """
        self.swing_lookback = swing_lookback
        self.structure_lookback = structure_lookback
        self.swing_points: List[SwingPoint] = []
        self.structure_breaks: List[StructureBreak] = []

    def detect_swing_points(
        self,
        highs: np.ndarray,
        lows: np.ndarray
    ) -> List[SwingPoint]:
        """
        스윙 고점/저점 감지

        Parameters
        ----------
        highs : np.ndarray
            고가 배열
        lows : np.ndarray
            저가 배열

        Returns
        -------
        List[SwingPoint]
            감지된 스윙 포인트
        """
        swing_points = []
        n = len(highs)

        if n < self.swing_lookback * 2 + 1:
            return swing_points

        for i in range(self.swing_lookback, n - self.swing_lookback):
            # Swing High 확인
            is_swing_high = True
            for j in range(i - self.swing_lookback, i + self.swing_lookback + 1):
                if j != i and highs[j] >= highs[i]:
                    is_swing_high = False
                    break

            if is_swing_high:
                swing_points.append(SwingPoint(
                    idx=i,
                    price=highs[i],
                    is_high=True
                ))

            # Swing Low 확인
            is_swing_low = True
            for j in range(i - self.swing_lookback, i + self.swing_lookback + 1):
                if j != i and lows[j] <= lows[i]:
                    is_swing_low = False
                    break

            if is_swing_low:
                swing_points.append(SwingPoint(
                    idx=i,
                    price=lows[i],
                    is_high=False
                ))

        # 인덱스순 정렬
        swing_points.sort(key=lambda x: x.idx)
        self.swing_points = swing_points

        return swing_points

    def determine_trend(
        self,
        swing_points: Optional[List[SwingPoint]] = None,
        lookback: Optional[int] = None
    ) -> MarketTrend:
        """
        현재 시장 추세 판단

        로직:
        - Higher Highs + Higher Lows = Bullish
        - Lower Highs + Lower Lows = Bearish
        - 그 외 = Ranging

        Parameters
        ----------
        swing_points : Optional[List[SwingPoint]]
            스윙 포인트 리스트 (None이면 내부 저장된 것 사용)
        lookback : Optional[int]
            분석할 스윙 포인트 개수

        Returns
        -------
        MarketTrend
            현재 추세
        """
        if swing_points is None:
            swing_points = self.swing_points

        if lookback is None:
            lookback = self.structure_lookback

        if len(swing_points) < 4:
            return MarketTrend.RANGING

        # 최근 swing points만 분석
        recent_swings = swing_points[-lookback:] if len(swing_points) > lookback else swing_points

        # 고점과 저점 분리
        highs = [sp for sp in recent_swings if sp.is_high]
        lows = [sp for sp in recent_swings if not sp.is_high]

        if len(highs) < 2 or len(lows) < 2:
            return MarketTrend.RANGING

        # Higher Highs 확인
        higher_highs = all(
            highs[i].price > highs[i - 1].price
            for i in range(1, len(highs))
        )

        # Higher Lows 확인
        higher_lows = all(
            lows[i].price > lows[i - 1].price
            for i in range(1, len(lows))
        )

        # Lower Highs 확인
        lower_highs = all(
            highs[i].price < highs[i - 1].price
            for i in range(1, len(highs))
        )

        # Lower Lows 확인
        lower_lows = all(
            lows[i].price < lows[i - 1].price
            for i in range(1, len(lows))
        )

        # 추세 판단
        if higher_highs and higher_lows:
            return MarketTrend.BULLISH
        elif lower_highs and lower_lows:
            return MarketTrend.BEARISH
        else:
            return MarketTrend.RANGING

    def detect_bos_choch(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        swing_points: Optional[List[SwingPoint]] = None
    ) -> List[StructureBreak]:
        """
        BOS (Break of Structure) 및 CHoCH (Change of Character) 감지

        BOS: 추세 방향으로 이전 스윙 포인트 돌파 (추세 지속)
        CHoCH: 추세 반대 방향으로 이전 스윙 포인트 돌파 (추세 전환 가능)

        Parameters
        ----------
        highs : np.ndarray
            고가 배열
        lows : np.ndarray
            저가 배열
        closes : np.ndarray
            종가 배열
        swing_points : Optional[List[SwingPoint]]
            스윙 포인트 리스트

        Returns
        -------
        List[StructureBreak]
            감지된 구조 변화
        """
        if swing_points is None:
            swing_points = self.swing_points

        if len(swing_points) < 3:
            return []

        structure_breaks = []
        current_trend = self.determine_trend(swing_points)

        # 최근 스윙 포인트들 분석
        for i in range(len(swing_points) - 1):
            swing = swing_points[i]
            next_swing = swing_points[i + 1]

            # 스윙 포인트 이후의 가격 움직임 확인
            for idx in range(swing.idx + 1, len(closes)):
                # Bullish BOS: 상승 추세에서 이전 고점 돌파
                if (current_trend == MarketTrend.BULLISH and
                    swing.is_high and
                    closes[idx] > swing.price):

                    structure_breaks.append(StructureBreak(
                        type=StructureType.BOS,
                        trend=MarketTrend.BULLISH,
                        idx=idx,
                        price=closes[idx],
                        broken_level=swing.price
                    ))
                    break

                # Bearish BOS: 하락 추세에서 이전 저점 하향 돌파
                elif (current_trend == MarketTrend.BEARISH and
                      not swing.is_high and
                      closes[idx] < swing.price):

                    structure_breaks.append(StructureBreak(
                        type=StructureType.BOS,
                        trend=MarketTrend.BEARISH,
                        idx=idx,
                        price=closes[idx],
                        broken_level=swing.price
                    ))
                    break

                # Bullish CHoCH: 하락 추세에서 이전 고점 돌파 (추세 전환 신호)
                elif (current_trend == MarketTrend.BEARISH and
                      swing.is_high and
                      closes[idx] > swing.price):

                    structure_breaks.append(StructureBreak(
                        type=StructureType.CHOCH,
                        trend=MarketTrend.BULLISH,
                        idx=idx,
                        price=closes[idx],
                        broken_level=swing.price
                    ))
                    # CHoCH 발생 시 추세 전환
                    current_trend = MarketTrend.BULLISH
                    break

                # Bearish CHoCH: 상승 추세에서 이전 저점 하향 돌파 (추세 전환 신호)
                elif (current_trend == MarketTrend.BULLISH and
                      not swing.is_high and
                      closes[idx] < swing.price):

                    structure_breaks.append(StructureBreak(
                        type=StructureType.CHOCH,
                        trend=MarketTrend.BEARISH,
                        idx=idx,
                        price=closes[idx],
                        broken_level=swing.price
                    ))
                    # CHoCH 발생 시 추세 전환
                    current_trend = MarketTrend.BEARISH
                    break

        self.structure_breaks = structure_breaks
        return structure_breaks

    def get_latest_structure_break(self) -> Optional[StructureBreak]:
        """가장 최근 구조 변화 반환"""
        if not self.structure_breaks:
            return None
        return self.structure_breaks[-1]

    def is_bullish_structure(self) -> bool:
        """현재 상승 구조인지 확인"""
        return self.determine_trend() == MarketTrend.BULLISH

    def is_bearish_structure(self) -> bool:
        """현재 하락 구조인지 확인"""
        return self.determine_trend() == MarketTrend.BEARISH

    def get_key_levels(
        self,
        swing_points: Optional[List[SwingPoint]] = None
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        주요 레벨 (최근 스윙 고점/저점) 반환

        Returns
        -------
        Tuple[Optional[float], Optional[float]]
            (최근 스윙 고점, 최근 스윙 저점)
        """
        if swing_points is None:
            swing_points = self.swing_points

        if not swing_points:
            return None, None

        # 최근 고점
        recent_highs = [sp for sp in swing_points if sp.is_high]
        recent_high = recent_highs[-1].price if recent_highs else None

        # 최근 저점
        recent_lows = [sp for sp in swing_points if not sp.is_high]
        recent_low = recent_lows[-1].price if recent_lows else None

        return recent_high, recent_low

    def get_discount_premium_levels(
        self,
        swing_points: Optional[List[SwingPoint]] = None
    ) -> Tuple[float, float, float]:
        """
        디스카운트/프리미엄 레벨 계산

        최근 스윙 레인지의:
        - 0.25: 디스카운트 존
        - 0.5: 평형
        - 0.75: 프리미엄 존

        Returns
        -------
        Tuple[float, float, float]
            (디스카운트 레벨, 평형 레벨, 프리미엄 레벨)
        """
        recent_high, recent_low = self.get_key_levels(swing_points)

        if recent_high is None or recent_low is None:
            return 0.0, 0.0, 0.0

        range_size = recent_high - recent_low
        discount_level = recent_low + range_size * 0.25
        equilibrium = recent_low + range_size * 0.5
        premium_level = recent_low + range_size * 0.75

        return discount_level, equilibrium, premium_level
