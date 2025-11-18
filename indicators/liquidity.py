"""
Liquidity Detector for ICT Trading

유동성은 많은 주문(stop loss, limit orders)이 쌓여있는 가격 레벨입니다.
기관은 자신의 큰 주문을 체결하기 위해 이러한 유동성을 목표로 합니다.

주요 유동성 레벨:
- Previous Day High/Low (PDH/PDL)
- Previous Week High/Low (PWH/PWL)
- Swing High/Low
- Equal Highs/Lows
"""
from typing import List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np
from datetime import datetime, timedelta


class LiquidityType(Enum):
    """유동성 타입"""
    BUY_SIDE = "buy_side"  # 매수 유동성 (고점 위의 stop loss)
    SELL_SIDE = "sell_side"  # 매도 유동성 (저점 아래의 stop loss)


@dataclass
class LiquidityLevel:
    """유동성 레벨 데이터 구조"""
    type: LiquidityType
    price: float
    strength: int  # 유동성 강도 (터치 횟수 등)
    timestamp_idx: int
    name: str  # 레벨 이름 (예: "PDH", "Swing High")
    swept: bool = False  # 유동성이 수집되었는지

    def __repr__(self):
        return f"LiquidityLevel({self.name}, {self.type.value}, {self.price:.2f})"


class LiquidityDetector:
    """
    유동성 레벨 감지기

    기능:
    1. Swing High/Low 감지
    2. Equal Highs/Lows 감지
    3. Previous Day/Week High/Low 추적
    4. 유동성 수집(Liquidity Grab) 감지
    """

    def __init__(
        self,
        swing_lookback: int = 5,
        equal_threshold: float = 0.1,  # Equal high/low 판단 임계값 (%)
    ):
        """
        Parameters
        ----------
        swing_lookback : int
            Swing High/Low를 판단할 lookback 기간
        equal_threshold : float
            Equal High/Low로 판단할 가격 차이 임계값 (%)
        """
        self.swing_lookback = swing_lookback
        self.equal_threshold = equal_threshold
        self.liquidity_levels: List[LiquidityLevel] = []

    def detect_swing_levels(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        timestamps: Optional[np.ndarray] = None
    ) -> List[LiquidityLevel]:
        """
        Swing High/Low 감지

        Swing High: 양옆의 캔들보다 높은 고점
        Swing Low: 양옆의 캔들보다 낮은 저점

        Parameters
        ----------
        highs : np.ndarray
            고가 배열
        lows : np.ndarray
            저가 배열
        timestamps : Optional[np.ndarray]
            타임스탬프 배열

        Returns
        -------
        List[LiquidityLevel]
            감지된 Swing 레벨
        """
        levels = []
        n = len(highs)

        if n < self.swing_lookback * 2 + 1:
            return levels

        for i in range(self.swing_lookback, n - self.swing_lookback):
            # Swing High 확인
            is_swing_high = True
            for j in range(i - self.swing_lookback, i + self.swing_lookback + 1):
                if j != i and highs[j] >= highs[i]:
                    is_swing_high = False
                    break

            if is_swing_high:
                level = LiquidityLevel(
                    type=LiquidityType.BUY_SIDE,
                    price=highs[i],
                    strength=1,
                    timestamp_idx=i,
                    name="Swing High",
                    swept=False
                )
                levels.append(level)

            # Swing Low 확인
            is_swing_low = True
            for j in range(i - self.swing_lookback, i + self.swing_lookback + 1):
                if j != i and lows[j] <= lows[i]:
                    is_swing_low = False
                    break

            if is_swing_low:
                level = LiquidityLevel(
                    type=LiquidityType.SELL_SIDE,
                    price=lows[i],
                    strength=1,
                    timestamp_idx=i,
                    name="Swing Low",
                    swept=False
                )
                levels.append(level)

        return levels

    def detect_equal_levels(
        self,
        swing_levels: List[LiquidityLevel]
    ) -> List[LiquidityLevel]:
        """
        Equal Highs/Lows 감지

        가격이 거의 동일한 여러 개의 Swing High/Low는
        더 강한 유동성 레벨을 형성합니다.

        Parameters
        ----------
        swing_levels : List[LiquidityLevel]
            Swing 레벨 리스트

        Returns
        -------
        List[LiquidityLevel]
            Equal 레벨 (강화된 유동성)
        """
        equal_levels = []

        # Buy Side (Swing Highs) 그룹화
        buy_side = [lv for lv in swing_levels if lv.type == LiquidityType.BUY_SIDE]
        buy_groups = self._group_equal_prices(buy_side)

        for group in buy_groups:
            if len(group) >= 2:  # 2개 이상이면 Equal High
                avg_price = np.mean([lv.price for lv in group])
                max_idx = max([lv.timestamp_idx for lv in group])
                equal_level = LiquidityLevel(
                    type=LiquidityType.BUY_SIDE,
                    price=avg_price,
                    strength=len(group),
                    timestamp_idx=max_idx,
                    name=f"Equal High (x{len(group)})",
                    swept=False
                )
                equal_levels.append(equal_level)

        # Sell Side (Swing Lows) 그룹화
        sell_side = [lv for lv in swing_levels if lv.type == LiquidityType.SELL_SIDE]
        sell_groups = self._group_equal_prices(sell_side)

        for group in sell_groups:
            if len(group) >= 2:  # 2개 이상이면 Equal Low
                avg_price = np.mean([lv.price for lv in group])
                max_idx = max([lv.timestamp_idx for lv in group])
                equal_level = LiquidityLevel(
                    type=LiquidityType.SELL_SIDE,
                    price=avg_price,
                    strength=len(group),
                    timestamp_idx=max_idx,
                    name=f"Equal Low (x{len(group)})",
                    swept=False
                )
                equal_levels.append(equal_level)

        return equal_levels

    def _group_equal_prices(
        self,
        levels: List[LiquidityLevel]
    ) -> List[List[LiquidityLevel]]:
        """비슷한 가격의 레벨들을 그룹화"""
        if not levels:
            return []

        # 가격순 정렬
        sorted_levels = sorted(levels, key=lambda x: x.price)
        groups = []
        current_group = [sorted_levels[0]]

        for i in range(1, len(sorted_levels)):
            prev_price = current_group[-1].price
            curr_price = sorted_levels[i].price

            # 가격 차이가 임계값 이내면 같은 그룹
            price_diff_pct = abs((curr_price - prev_price) / prev_price * 100)

            if price_diff_pct <= self.equal_threshold:
                current_group.append(sorted_levels[i])
            else:
                if len(current_group) > 0:
                    groups.append(current_group)
                current_group = [sorted_levels[i]]

        if len(current_group) > 0:
            groups.append(current_group)

        return groups

    def get_previous_day_levels(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        timestamps: np.ndarray
    ) -> Tuple[Optional[LiquidityLevel], Optional[LiquidityLevel]]:
        """
        전일 고점/저점 (PDH/PDL) 반환

        Parameters
        ----------
        highs : np.ndarray
            고가 배열
        lows : np.ndarray
            저가 배열
        timestamps : np.ndarray
            타임스탬프 배열 (Unix timestamp)

        Returns
        -------
        Tuple[Optional[LiquidityLevel], Optional[LiquidityLevel]]
            (PDH, PDL)
        """
        if len(timestamps) < 2:
            return None, None

        # 현재 시간과 전일 시간 계산
        current_time = timestamps[-1]
        one_day_ago = current_time - 86400  # 86400초 = 1일

        # 전일 데이터 필터링
        prev_day_mask = (timestamps >= one_day_ago) & (timestamps < current_time)

        if not np.any(prev_day_mask):
            return None, None

        prev_day_highs = highs[prev_day_mask]
        prev_day_lows = lows[prev_day_mask]
        prev_day_indices = np.where(prev_day_mask)[0]

        if len(prev_day_highs) == 0:
            return None, None

        # PDH
        pdh_value = np.max(prev_day_highs)
        pdh_idx = prev_day_indices[np.argmax(prev_day_highs)]
        pdh = LiquidityLevel(
            type=LiquidityType.BUY_SIDE,
            price=pdh_value,
            strength=3,  # 높은 강도
            timestamp_idx=pdh_idx,
            name="PDH",
            swept=False
        )

        # PDL
        pdl_value = np.min(prev_day_lows)
        pdl_idx = prev_day_indices[np.argmin(prev_day_lows)]
        pdl = LiquidityLevel(
            type=LiquidityType.SELL_SIDE,
            price=pdl_value,
            strength=3,  # 높은 강도
            timestamp_idx=pdl_idx,
            name="PDL",
            swept=False
        )

        return pdh, pdl

    def detect_liquidity_grab(
        self,
        levels: List[LiquidityLevel],
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        sweep_threshold: float = 0.1  # 유동성 스윕으로 판단할 침투 거리 (%)
    ) -> List[LiquidityLevel]:
        """
        유동성 수집(Liquidity Grab/Sweep) 감지

        가격이 유동성 레벨을 약간 넘어갔다가 빠르게 반대 방향으로
        움직이면 유동성을 수집한 것으로 판단

        Parameters
        ----------
        levels : List[LiquidityLevel]
            유동성 레벨 리스트
        highs : np.ndarray
            고가 배열
        lows : np.ndarray
            저가 배열
        closes : np.ndarray
            종가 배열
        sweep_threshold : float
            스윕으로 판단할 침투 비율 (%)

        Returns
        -------
        List[LiquidityLevel]
            스윕된 레벨 리스트
        """
        swept_levels = []
        current_idx = len(closes) - 1

        for level in levels:
            if level.swept or level.timestamp_idx >= current_idx:
                continue

            # Buy Side Liquidity (위쪽) 스윕 확인
            if level.type == LiquidityType.BUY_SIDE:
                # 고가가 레벨을 넘었는지 확인
                for i in range(level.timestamp_idx + 1, current_idx + 1):
                    if highs[i] > level.price:
                        # 침투 거리 확인
                        penetration = (highs[i] - level.price) / level.price * 100

                        # 종가가 다시 레벨 아래로 닫혔는지 확인
                        if closes[i] < level.price and penetration <= sweep_threshold:
                            level.swept = True
                            swept_levels.append(level)
                            break

            # Sell Side Liquidity (아래쪽) 스윕 확인
            else:
                # 저가가 레벨을 넘었는지 확인
                for i in range(level.timestamp_idx + 1, current_idx + 1):
                    if lows[i] < level.price:
                        # 침투 거리 확인
                        penetration = abs((lows[i] - level.price) / level.price * 100)

                        # 종가가 다시 레벨 위로 닫혔는지 확인
                        if closes[i] > level.price and penetration <= sweep_threshold:
                            level.swept = True
                            swept_levels.append(level)
                            break

        return swept_levels

    def get_nearest_liquidity(
        self,
        levels: List[LiquidityLevel],
        current_price: float,
        liquidity_type: Optional[LiquidityType] = None,
        only_unswept: bool = True
    ) -> Optional[LiquidityLevel]:
        """
        현재 가격에서 가장 가까운 유동성 레벨 반환

        Parameters
        ----------
        levels : List[LiquidityLevel]
            유동성 레벨 리스트
        current_price : float
            현재 가격
        liquidity_type : Optional[LiquidityType]
            필터링할 타입
        only_unswept : bool
            스윕되지 않은 레벨만 고려할지

        Returns
        -------
        Optional[LiquidityLevel]
            가장 가까운 유동성 레벨
        """
        filtered = levels

        if liquidity_type:
            filtered = [lv for lv in filtered if lv.type == liquidity_type]

        if only_unswept:
            filtered = [lv for lv in filtered if not lv.swept]

        if not filtered:
            return None

        nearest = min(filtered, key=lambda lv: abs(lv.price - current_price))
        return nearest
