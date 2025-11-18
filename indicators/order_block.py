"""
Order Block Detector for ICT Trading

Order Block은 기관이 큰 포지션을 채우는 구간으로,
가격이 급격히 움직이기 전의 마지막 반대 방향 캔들을 의미합니다.
"""
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum
import numpy as np


class OrderBlockType(Enum):
    """Order Block 타입"""
    BULLISH = "bullish"  # 상승 오더블록 (매수 기관 관심구간)
    BEARISH = "bearish"  # 하락 오더블록 (매도 기관 관심구간)


@dataclass
class OrderBlock:
    """Order Block 데이터 구조"""
    type: OrderBlockType
    start_idx: int
    end_idx: int
    high: float
    low: float
    close: float
    open: float
    strength: float  # 오더블록 강도 (이후 이동거리 기반)
    touched: bool = False  # 테스트 여부
    mitigated: bool = False  # 무효화 여부

    @property
    def midpoint(self) -> float:
        """오더블록 중간값 (0.5 레벨)"""
        return (self.high + self.low) / 2

    @property
    def premium_zone(self) -> float:
        """프리미엄 존 (0.75 레벨)"""
        return self.low + (self.high - self.low) * 0.75

    @property
    def discount_zone(self) -> float:
        """디스카운트 존 (0.25 레벨)"""
        return self.low + (self.high - self.low) * 0.25


class OrderBlockDetector:
    """
    Order Block 감지기

    알고리즘:
    1. 강한 이동(impulse move)을 감지
    2. 이동 전 마지막 반대방향 캔들을 Order Block으로 식별
    3. 강도는 이후 이동거리로 계산
    """

    def __init__(
        self,
        min_impulse_bars: int = 3,
        min_impulse_size: float = 0.5,  # % 변화
        lookback_period: int = 50
    ):
        """
        Parameters
        ----------
        min_impulse_bars : int
            임펄스로 인정할 최소 연속 캔들 수
        min_impulse_size : float
            임펄스로 인정할 최소 가격 변화 (%)
        lookback_period : int
            오더블록을 탐색할 캔들 수
        """
        self.min_impulse_bars = min_impulse_bars
        self.min_impulse_size = min_impulse_size
        self.lookback_period = lookback_period
        self.order_blocks: List[OrderBlock] = []

    def detect(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        opens: np.ndarray
    ) -> List[OrderBlock]:
        """
        Order Block 감지

        Parameters
        ----------
        highs : np.ndarray
            고가 배열
        lows : np.ndarray
            저가 배열
        closes : np.ndarray
            종가 배열
        opens : np.ndarray
            시가 배열

        Returns
        -------
        List[OrderBlock]
            감지된 Order Block 리스트
        """
        order_blocks = []
        n = len(closes)

        if n < self.min_impulse_bars + 1:
            return order_blocks

        # 최근 lookback_period만큼만 분석
        start_idx = max(0, n - self.lookback_period)

        for i in range(start_idx + self.min_impulse_bars, n):
            # Bullish Order Block 감지 (하락 후 강한 상승)
            bullish_ob = self._detect_bullish_ob(
                i, highs, lows, closes, opens
            )
            if bullish_ob:
                order_blocks.append(bullish_ob)

            # Bearish Order Block 감지 (상승 후 강한 하락)
            bearish_ob = self._detect_bearish_ob(
                i, highs, lows, closes, opens
            )
            if bearish_ob:
                order_blocks.append(bearish_ob)

        # 기존 Order Block 상태 업데이트
        self._update_order_blocks(order_blocks, highs, lows, closes)

        return order_blocks

    def _detect_bullish_ob(
        self,
        idx: int,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        opens: np.ndarray
    ) -> Optional[OrderBlock]:
        """
        Bullish Order Block 감지

        로직:
        1. 현재 위치에서 역으로 강한 상승 임펄스 확인
        2. 임펄스 직전의 하락(또는 횡보) 캔들이 Order Block
        """
        # 임펄스 시작점 찾기
        impulse_start = idx - self.min_impulse_bars

        # 임펄스 확인: 연속 상승 캔들
        is_impulse = True
        for j in range(impulse_start, idx):
            if closes[j] <= opens[j]:  # 하락 캔들이면 임펄스 아님
                is_impulse = False
                break

        if not is_impulse:
            return None

        # 임펄스 크기 확인
        impulse_move = (closes[idx - 1] - opens[impulse_start]) / opens[impulse_start] * 100
        if impulse_move < self.min_impulse_size:
            return None

        # Order Block은 임펄스 직전 캔들
        ob_idx = impulse_start - 1
        if ob_idx < 0:
            return None

        # 하락 또는 횡보 캔들이어야 함
        if closes[ob_idx] > opens[ob_idx]:
            return None

        return OrderBlock(
            type=OrderBlockType.BULLISH,
            start_idx=ob_idx,
            end_idx=ob_idx,
            high=highs[ob_idx],
            low=lows[ob_idx],
            close=closes[ob_idx],
            open=opens[ob_idx],
            strength=impulse_move,
            touched=False,
            mitigated=False
        )

    def _detect_bearish_ob(
        self,
        idx: int,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        opens: np.ndarray
    ) -> Optional[OrderBlock]:
        """
        Bearish Order Block 감지

        로직:
        1. 현재 위치에서 역으로 강한 하락 임펄스 확인
        2. 임펄스 직전의 상승(또는 횡보) 캔들이 Order Block
        """
        # 임펄스 시작점 찾기
        impulse_start = idx - self.min_impulse_bars

        # 임펄스 확인: 연속 하락 캔들
        is_impulse = True
        for j in range(impulse_start, idx):
            if closes[j] >= opens[j]:  # 상승 캔들이면 임펄스 아님
                is_impulse = False
                break

        if not is_impulse:
            return None

        # 임펄스 크기 확인
        impulse_move = abs((closes[idx - 1] - opens[impulse_start]) / opens[impulse_start] * 100)
        if impulse_move < self.min_impulse_size:
            return None

        # Order Block은 임펄스 직전 캔들
        ob_idx = impulse_start - 1
        if ob_idx < 0:
            return None

        # 상승 또는 횡보 캔들이어야 함
        if closes[ob_idx] < opens[ob_idx]:
            return None

        return OrderBlock(
            type=OrderBlockType.BEARISH,
            start_idx=ob_idx,
            end_idx=ob_idx,
            high=highs[ob_idx],
            low=lows[ob_idx],
            close=closes[ob_idx],
            open=opens[ob_idx],
            strength=impulse_move,
            touched=False,
            mitigated=False
        )

    def _update_order_blocks(
        self,
        order_blocks: List[OrderBlock],
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray
    ):
        """Order Block 상태 업데이트 (터치 여부, 무효화 여부)"""
        current_idx = len(closes) - 1
        current_price = closes[current_idx]

        for ob in order_blocks:
            # 터치 확인
            if not ob.touched:
                if ob.type == OrderBlockType.BULLISH:
                    # 가격이 Order Block 범위에 들어왔는지
                    if lows[current_idx] <= ob.high and highs[current_idx] >= ob.low:
                        ob.touched = True
                else:  # BEARISH
                    if lows[current_idx] <= ob.high and highs[current_idx] >= ob.low:
                        ob.touched = True

            # 무효화 확인
            if not ob.mitigated:
                if ob.type == OrderBlockType.BULLISH:
                    # 가격이 Order Block 아래로 완전히 닫히면 무효화
                    if closes[current_idx] < ob.low:
                        ob.mitigated = True
                else:  # BEARISH
                    # 가격이 Order Block 위로 완전히 닫히면 무효화
                    if closes[current_idx] > ob.high:
                        ob.mitigated = True

    def get_active_order_blocks(
        self,
        order_blocks: List[OrderBlock],
        ob_type: Optional[OrderBlockType] = None
    ) -> List[OrderBlock]:
        """
        활성 Order Block 반환 (무효화되지 않은 것만)

        Parameters
        ----------
        order_blocks : List[OrderBlock]
            전체 Order Block 리스트
        ob_type : Optional[OrderBlockType]
            필터링할 타입 (None이면 전체)

        Returns
        -------
        List[OrderBlock]
            활성 Order Block 리스트
        """
        active = [ob for ob in order_blocks if not ob.mitigated]

        if ob_type:
            active = [ob for ob in active if ob.type == ob_type]

        return active
