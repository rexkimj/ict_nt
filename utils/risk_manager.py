"""
Risk Manager for ICT Trading

리스크 관리는 장기적인 생존과 안정적인 수익을 위한 핵심 요소입니다.

주요 기능:
1. 포지션 사이징 (1-2% 리스크 원칙)
2. Stop Loss 계산
3. Take Profit 계산
4. Risk-Reward 비율 검증
"""
from typing import Optional, Tuple
from decimal import Decimal
import numpy as np


class RiskManager:
    """
    리스크 관리자

    ICT 원칙:
    - 각 거래당 자본의 1-2%만 리스크
    - 논리적인 Stop Loss 배치 (유동성 수집 지점 뒤)
    - Risk-Reward 비율 최소 1:2
    """

    def __init__(
        self,
        max_risk_per_trade_pct: float = 1.0,  # 거래당 최대 리스크 (%)
        min_risk_reward_ratio: float = 2.0,   # 최소 RR 비율
        max_position_size_pct: float = 10.0,  # 최대 포지션 크기 (%)
    ):
        """
        Parameters
        ----------
        max_risk_per_trade_pct : float
            거래당 최대 리스크 비율 (자본 대비 %)
        min_risk_reward_ratio : float
            최소 Risk-Reward 비율
        max_position_size_pct : float
            최대 포지션 크기 (자본 대비 %)
        """
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.min_risk_reward_ratio = min_risk_reward_ratio
        self.max_position_size_pct = max_position_size_pct

    def calculate_position_size(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss: float,
        leverage: int = 1
    ) -> Tuple[float, float]:
        """
        포지션 사이즈 계산

        Parameters
        ----------
        account_balance : float
            계좌 잔고
        entry_price : float
            진입 가격
        stop_loss : float
            손절가
        leverage : int
            레버리지

        Returns
        -------
        Tuple[float, float]
            (포지션 크기, 리스크 금액)
        """
        # 리스크 금액 계산 (계좌의 1-2%)
        risk_amount = account_balance * (self.max_risk_per_trade_pct / 100)

        # Stop Loss까지의 거리 (%)
        sl_distance_pct = abs((stop_loss - entry_price) / entry_price)

        # 포지션 크기 계산
        # risk_amount = position_size * sl_distance_pct
        position_size = risk_amount / sl_distance_pct

        # 레버리지 적용
        position_size = position_size * leverage

        # 최대 포지션 크기 제한
        max_position = account_balance * (self.max_position_size_pct / 100) * leverage
        position_size = min(position_size, max_position)

        return position_size, risk_amount

    def calculate_stop_loss(
        self,
        entry_price: float,
        order_block_level: Optional[float] = None,
        liquidity_level: Optional[float] = None,
        is_long: bool = True,
        buffer_pct: float = 0.1  # 버퍼 (%)
    ) -> float:
        """
        Stop Loss 계산

        ICT 원칙:
        - Order Block이나 유동성 레벨 뒤에 배치
        - 약간의 버퍼를 추가하여 위그(wick)에 의한 조기 청산 방지

        Parameters
        ----------
        entry_price : float
            진입 가격
        order_block_level : Optional[float]
            Order Block 레벨 (있는 경우)
        liquidity_level : Optional[float]
            유동성 레벨 (있는 경우)
        is_long : bool
            롱 포지션 여부
        buffer_pct : float
            버퍼 비율 (%)

        Returns
        -------
        float
            Stop Loss 가격
        """
        # 우선순위: Order Block > Liquidity Level
        reference_level = order_block_level if order_block_level else liquidity_level

        if reference_level is None:
            # 기본값: 진입가 대비 2%
            default_distance = entry_price * 0.02
            if is_long:
                return entry_price - default_distance
            else:
                return entry_price + default_distance

        # 버퍼 적용
        buffer = reference_level * (buffer_pct / 100)

        if is_long:
            # 롱 포지션: 레벨 아래에 SL 배치
            stop_loss = reference_level - buffer
        else:
            # 숏 포지션: 레벨 위에 SL 배치
            stop_loss = reference_level + buffer

        return stop_loss

    def calculate_take_profit(
        self,
        entry_price: float,
        stop_loss: float,
        target_liquidity: Optional[float] = None,
        risk_reward_ratio: Optional[float] = None,
        is_long: bool = True
    ) -> float:
        """
        Take Profit 계산

        ICT 원칙:
        - 우선적으로 유동성 레벨을 목표로 설정
        - 유동성 레벨이 없으면 Risk-Reward 비율 기반

        Parameters
        ----------
        entry_price : float
            진입 가격
        stop_loss : float
            손절가
        target_liquidity : Optional[float]
            목표 유동성 레벨 (PDH, PDL 등)
        risk_reward_ratio : Optional[float]
            Risk-Reward 비율 (None이면 기본값 사용)
        is_long : bool
            롱 포지션 여부

        Returns
        -------
        float
            Take Profit 가격
        """
        # 유동성 레벨이 있으면 우선 사용
        if target_liquidity is not None:
            # RR 비율 확인
            risk = abs(entry_price - stop_loss)
            reward = abs(target_liquidity - entry_price)
            rr_ratio = reward / risk if risk > 0 else 0

            # 최소 RR 비율 충족하면 사용
            if rr_ratio >= self.min_risk_reward_ratio:
                return target_liquidity

        # Risk-Reward 비율 기반 계산
        if risk_reward_ratio is None:
            risk_reward_ratio = self.min_risk_reward_ratio

        risk = abs(entry_price - stop_loss)
        reward = risk * risk_reward_ratio

        if is_long:
            take_profit = entry_price + reward
        else:
            take_profit = entry_price - reward

        return take_profit

    def validate_trade(
        self,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        is_long: bool = True
    ) -> Tuple[bool, str]:
        """
        거래 유효성 검증

        Parameters
        ----------
        entry_price : float
            진입 가격
        stop_loss : float
            손절가
        take_profit : float
            익절가
        is_long : bool
            롱 포지션 여부

        Returns
        -------
        Tuple[bool, str]
            (유효 여부, 메시지)
        """
        # 1. Stop Loss 위치 확인
        if is_long:
            if stop_loss >= entry_price:
                return False, "Stop Loss must be below entry price for long positions"
            if take_profit <= entry_price:
                return False, "Take Profit must be above entry price for long positions"
        else:
            if stop_loss <= entry_price:
                return False, "Stop Loss must be above entry price for short positions"
            if take_profit >= entry_price:
                return False, "Take Profit must be below entry price for short positions"

        # 2. Risk-Reward 비율 확인
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        rr_ratio = reward / risk if risk > 0 else 0

        if rr_ratio < self.min_risk_reward_ratio:
            return False, f"Risk-Reward ratio ({rr_ratio:.2f}) below minimum ({self.min_risk_reward_ratio})"

        # 3. 리스크가 너무 크지 않은지 확인
        risk_pct = (risk / entry_price) * 100
        if risk_pct > 5.0:  # 5% 이상 리스크는 위험
            return False, f"Risk per trade ({risk_pct:.2f}%) too high"

        return True, f"Valid trade setup (RR: {rr_ratio:.2f}:1)"

    def calculate_partial_exits(
        self,
        entry_price: float,
        take_profit: float,
        num_partials: int = 3
    ) -> list[float]:
        """
        부분 익절 레벨 계산

        Parameters
        ----------
        entry_price : float
            진입 가격
        take_profit : float
            최종 익절가
        num_partials : int
            부분 익절 횟수

        Returns
        -------
        list[float]
            부분 익절 가격 리스트
        """
        distance = take_profit - entry_price
        partial_levels = []

        for i in range(1, num_partials + 1):
            level = entry_price + (distance * i / num_partials)
            partial_levels.append(level)

        return partial_levels

    def adjust_for_volatility(
        self,
        stop_loss: float,
        entry_price: float,
        atr_value: float,
        atr_multiplier: float = 1.5
    ) -> float:
        """
        변동성을 고려한 Stop Loss 조정

        ATR(Average True Range) 기반으로 SL을 조정하여
        정상적인 시장 노이즈로 인한 조기 청산을 방지

        Parameters
        ----------
        stop_loss : float
            원래 Stop Loss
        entry_price : float
            진입 가격
        atr_value : float
            ATR 값
        atr_multiplier : float
            ATR 배수

        Returns
        -------
        float
            조정된 Stop Loss
        """
        # 현재 SL 거리
        current_distance = abs(entry_price - stop_loss)

        # ATR 기반 최소 거리
        min_distance = atr_value * atr_multiplier

        # SL이 너무 가까우면 조정
        if current_distance < min_distance:
            if stop_loss < entry_price:
                # 롱 포지션
                adjusted_sl = entry_price - min_distance
            else:
                # 숏 포지션
                adjusted_sl = entry_price + min_distance

            return adjusted_sl

        return stop_loss

    def calculate_max_drawdown_allowed(
        self,
        account_balance: float,
        max_drawdown_pct: float = 20.0
    ) -> float:
        """
        허용 가능한 최대 손실(Drawdown) 계산

        Parameters
        ----------
        account_balance : float
            계좌 잔고
        max_drawdown_pct : float
            최대 손실 비율 (%)

        Returns
        -------
        float
            허용 가능한 최대 손실 금액
        """
        return account_balance * (max_drawdown_pct / 100)

    def should_reduce_position_size(
        self,
        current_balance: float,
        peak_balance: float,
        threshold_pct: float = 10.0
    ) -> bool:
        """
        포지션 크기를 줄여야 하는지 판단

        연속 손실 시 리스크를 줄이기 위한 메커니즘

        Parameters
        ----------
        current_balance : float
            현재 잔고
        peak_balance : float
            최고 잔고
        threshold_pct : float
            포지션 축소 임계값 (%)

        Returns
        -------
        bool
            포지션 축소 필요 여부
        """
        drawdown_pct = ((peak_balance - current_balance) / peak_balance) * 100
        return drawdown_pct >= threshold_pct
