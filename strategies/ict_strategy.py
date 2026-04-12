"""
ICT Trading Strategy for NautilusTrader

기관의 기회 포착을 위한 ICT 트레이딩 전략

진입 원칙:
1. Higher TimeFrame(HTF)의 추세 확인
2. Lower TimeFrame(LTF)에서 POI(Order Block, FVG) 확인
3. 유동성 수집(Liquidity Grab) 후 진입
4. Market Structure와 7가지 요소 종합 고려

청산 원칙:
1. 유동성 레벨(PDH, PDL 등)을 Take Profit으로 설정
2. Stop Loss는 유동성 수집 지점 뒤에 배치
3. Risk-Reward 비율 최소 1:2 유지
4. 1-2% 리스크 원칙 준수
"""
from typing import Optional
from decimal import Decimal

from nautilus_trader.trading.strategy import Strategy
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.orders import MarketOrder, LimitOrder
from nautilus_trader.model.position import Position
from nautilus_trader.core.message import Event

import numpy as np

from indicators.order_block import OrderBlockDetector, OrderBlockType
from indicators.fvg import FVGDetector, FVGType
from indicators.liquidity import LiquidityDetector, LiquidityType
from indicators.market_structure import MarketStructureAnalyzer, MarketTrend
from utils.risk_manager import RiskManager


class ICTStrategy(Strategy):
    """
    ICT Trading Strategy

    다중 타임프레임 분석:
    - HTF (Higher TimeFrame): 전체 추세 및 방향 파악
    - LTF (Lower TimeFrame): 정확한 진입점 포착

    7가지 필수 요소:
    1. Liquidity (유동성)
    2. Market Structure (시장 구조)
    3. Order Block (오더 블록)
    4. FVG/Imbalance (공정가치 갭)
    5. Discount/Premium (할인/프리미엄 존)
    6. Timeframe (타임프레임)
    7. Time (시간대 - 킬존 등)
    """

    def __init__(self, config: dict):
        """
        Parameters
        ----------
        config : dict
            전략 설정
            {
                'instrument_id': 거래 상품 ID,
                'htf_bar_type': Higher TimeFrame bar type (예: '1-HOUR'),
                'ltf_bar_type': Lower TimeFrame bar type (예: '5-MINUTE'),
                'risk_per_trade_pct': 거래당 리스크 (기본 1%),
                'min_rr_ratio': 최소 RR 비율 (기본 2.0),
                'leverage': 레버리지 (기본 1),
                'order_block_params': Order Block 파라미터,
                'fvg_params': FVG 파라미터,
                'liquidity_params': Liquidity 파라미터,
                'market_structure_params': Market Structure 파라미터,
            }
        """
        # StrategyConfig 생성
        from nautilus_trader.config import StrategyConfig

        strategy_config = StrategyConfig()
        super().__init__(strategy_config)

        # 기본 설정
        self.instrument_id = InstrumentId.from_str(config['instrument_id'])
        self.htf_bar_type = BarType.from_str(config.get('htf_bar_type', '1-HOUR-LAST'))
        self.ltf_bar_type = BarType.from_str(config.get('ltf_bar_type', '5-MINUTE-LAST'))

        # 리스크 관리
        risk_pct = config.get('risk_per_trade_pct', 1.0)
        min_rr = config.get('min_rr_ratio', 2.0)
        self.risk_manager = RiskManager(
            max_risk_per_trade_pct=risk_pct,
            min_risk_reward_ratio=min_rr
        )
        self.leverage = config.get('leverage', 1)

        # ICT 인디케이터 초기화
        ob_params = config.get('order_block_params', {})
        self.order_block_detector = OrderBlockDetector(
            min_impulse_bars=ob_params.get('min_impulse_bars', 3),
            min_impulse_size=ob_params.get('min_impulse_size', 0.5),
            lookback_period=ob_params.get('lookback_period', 50)
        )

        fvg_params = config.get('fvg_params', {})
        self.fvg_detector = FVGDetector(
            min_gap_size=fvg_params.get('min_gap_size', 0.1),
            fill_threshold=fvg_params.get('fill_threshold', 0.5),
            lookback_period=fvg_params.get('lookback_period', 100)
        )

        liq_params = config.get('liquidity_params', {})
        self.liquidity_detector = LiquidityDetector(
            swing_lookback=liq_params.get('swing_lookback', 5),
            equal_threshold=liq_params.get('equal_threshold', 0.1)
        )

        ms_params = config.get('market_structure_params', {})
        self.market_structure = MarketStructureAnalyzer(
            swing_lookback=ms_params.get('swing_lookback', 5),
            structure_lookback=ms_params.get('structure_lookback', 20)
        )

        # 데이터 버퍼
        self.htf_bars = []
        self.ltf_bars = []
        self.max_bars = 500  # 메모리 관리

        # 상태 추적
        self.htf_trend = MarketTrend.RANGING
        self.liquidity_swept = False
        self.setup_valid = False

    def on_start(self):
        """전략 시작 시 호출"""
        self.log.info(f"ICT Strategy starting for {self.instrument_id}")

        # 데이터 구독
        self.subscribe_bars(self.htf_bar_type)
        self.subscribe_bars(self.ltf_bar_type)

    def on_stop(self):
        """전략 종료 시 호출"""
        self.log.info("ICT Strategy stopping")
        self.close_all_positions(self.instrument_id)

    def on_bar(self, bar: Bar):
        """
        새로운 바 데이터 수신 시 호출

        Parameters
        ----------
        bar : Bar
            수신된 바 데이터
        """
        # HTF 바 처리
        if bar.bar_type == self.htf_bar_type:
            self._process_htf_bar(bar)

        # LTF 바 처리
        elif bar.bar_type == self.ltf_bar_type:
            self._process_ltf_bar(bar)

    def _process_htf_bar(self, bar: Bar):
        """
        Higher TimeFrame 바 처리

        목적: 전체 시장 추세와 주요 구조 파악

        Parameters
        ----------
        bar : Bar
            HTF 바 데이터
        """
        # 바 저장
        self.htf_bars.append(bar)
        if len(self.htf_bars) > self.max_bars:
            self.htf_bars.pop(0)

        if len(self.htf_bars) < 50:
            return

        # numpy 배열로 변환
        highs = np.array([b.high.as_double() for b in self.htf_bars])
        lows = np.array([b.low.as_double() for b in self.htf_bars])
        closes = np.array([b.close.as_double() for b in self.htf_bars])
        opens = np.array([b.open.as_double() for b in self.htf_bars])

        # Market Structure 분석
        swing_points = self.market_structure.detect_swing_points(highs, lows)
        self.htf_trend = self.market_structure.determine_trend(swing_points)

        self.log.info(f"HTF Trend: {self.htf_trend.value}")

        # BOS/CHoCH 감지
        structure_breaks = self.market_structure.detect_bos_choch(
            highs, lows, closes, swing_points
        )
        if structure_breaks:
            latest_break = structure_breaks[-1]
            self.log.info(f"HTF Structure Break: {latest_break}")

    def _process_ltf_bar(self, bar: Bar):
        """
        Lower TimeFrame 바 처리

        목적: 정확한 진입점 포착

        Parameters
        ----------
        bar : Bar
            LTF 바 데이터
        """
        # 바 저장
        self.ltf_bars.append(bar)
        if len(self.ltf_bars) > self.max_bars:
            self.ltf_bars.pop(0)

        if len(self.ltf_bars) < 50:
            return

        # numpy 배열로 변환
        highs = np.array([b.high.as_double() for b in self.ltf_bars])
        lows = np.array([b.low.as_double() for b in self.ltf_bars])
        closes = np.array([b.close.as_double() for b in self.ltf_bars])
        opens = np.array([b.open.as_double() for b in self.ltf_bars])
        timestamps = np.array([b.ts_init for b in self.ltf_bars])

        current_price = closes[-1]

        # 포지션이 있으면 진입 로직 스킵
        if self.portfolio.is_flat(self.instrument_id):
            # 진입 시그널 확인
            self._check_entry_signals(
                highs, lows, closes, opens, timestamps, current_price
            )
        else:
            # 청산 관리
            self._manage_position(current_price)

    def _check_entry_signals(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        opens: np.ndarray,
        timestamps: np.ndarray,
        current_price: float
    ):
        """
        진입 시그널 확인

        7가지 요소 종합 고려:
        1. HTF 추세와 일치하는지
        2. 유동성이 수집되었는지
        3. Order Block 또는 FVG가 있는지
        4. Discount/Premium 존인지
        5. Market Structure 확인

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
        timestamps : np.ndarray
            타임스탬프 배열
        current_price : float
            현재 가격
        """
        # 1. HTF 추세 확인
        if self.htf_trend == MarketTrend.RANGING:
            return

        # 2. Order Block 감지
        order_blocks = self.order_block_detector.detect(highs, lows, closes, opens)

        # 3. FVG 감지
        fvgs = self.fvg_detector.detect(highs, lows, closes)

        # 4. 유동성 레벨 감지
        swing_levels = self.liquidity_detector.detect_swing_levels(
            highs, lows, timestamps
        )
        equal_levels = self.liquidity_detector.detect_equal_levels(swing_levels)
        all_liquidity = swing_levels + equal_levels

        # PDH/PDL 추가
        pdh, pdl = self.liquidity_detector.get_previous_day_levels(
            highs, lows, timestamps
        )
        if pdh:
            all_liquidity.append(pdh)
        if pdl:
            all_liquidity.append(pdl)

        # 5. 유동성 수집(Liquidity Grab) 확인
        swept_levels = self.liquidity_detector.detect_liquidity_grab(
            all_liquidity, highs, lows, closes
        )

        # 6. Discount/Premium 레벨 계산
        discount, equilibrium, premium = \
            self.market_structure.get_discount_premium_levels()

        # === 롱 진입 조건 ===
        if self.htf_trend == MarketTrend.BULLISH:
            self._check_long_entry(
                current_price, order_blocks, fvgs, swept_levels,
                discount, equilibrium
            )

        # === 숏 진입 조건 ===
        elif self.htf_trend == MarketTrend.BEARISH:
            self._check_short_entry(
                current_price, order_blocks, fvgs, swept_levels,
                premium, equilibrium
            )

    def _check_long_entry(
        self,
        current_price: float,
        order_blocks: list,
        fvgs: list,
        swept_levels: list,
        discount_level: float,
        equilibrium: float
    ):
        """
        롱 진입 조건 확인

        조건:
        1. HTF가 상승 추세
        2. 가격이 Discount 존 (0.5 이하)
        3. Sell Side 유동성이 수집됨
        4. Bullish Order Block 또는 FVG 존재
        """
        # Discount 존 확인
        if current_price > equilibrium:
            return

        # Sell Side 유동성 수집 확인
        sell_side_swept = any(
            lv.type == LiquidityType.SELL_SIDE
            for lv in swept_levels
        )
        if not sell_side_swept:
            return

        # Bullish Order Block 찾기
        active_ob = self.order_block_detector.get_active_order_blocks(
            order_blocks, OrderBlockType.BULLISH
        )

        # Bullish FVG 찾기
        unfilled_fvg = self.fvg_detector.get_unfilled_fvgs(
            fvgs, FVGType.BULLISH
        )

        # POI (Point of Interest) 확인
        if not active_ob and not unfilled_fvg:
            return

        # 가장 가까운 POI 찾기
        nearest_ob = None
        if active_ob:
            nearest_ob = min(
                active_ob,
                key=lambda ob: abs(ob.midpoint - current_price)
            )

        nearest_fvg = None
        if unfilled_fvg:
            nearest_fvg = self.fvg_detector.get_nearest_fvg(
                fvgs, current_price, FVGType.BULLISH
            )

        # Order Block 우선
        poi_level = nearest_ob.low if nearest_ob else (
            nearest_fvg.gap_low if nearest_fvg else None
        )

        if poi_level is None:
            return

        # 가격이 POI에 근접했는지 확인 (1% 이내)
        distance_pct = abs(current_price - poi_level) / current_price * 100
        if distance_pct > 1.0:
            return

        # 진입 실행
        self._execute_long_entry(current_price, poi_level, swept_levels)

    def _check_short_entry(
        self,
        current_price: float,
        order_blocks: list,
        fvgs: list,
        swept_levels: list,
        premium_level: float,
        equilibrium: float
    ):
        """
        숏 진입 조건 확인

        조건:
        1. HTF가 하락 추세
        2. 가격이 Premium 존 (0.5 이상)
        3. Buy Side 유동성이 수집됨
        4. Bearish Order Block 또는 FVG 존재
        """
        # Premium 존 확인
        if current_price < equilibrium:
            return

        # Buy Side 유동성 수집 확인
        buy_side_swept = any(
            lv.type == LiquidityType.BUY_SIDE
            for lv in swept_levels
        )
        if not buy_side_swept:
            return

        # Bearish Order Block 찾기
        active_ob = self.order_block_detector.get_active_order_blocks(
            order_blocks, OrderBlockType.BEARISH
        )

        # Bearish FVG 찾기
        unfilled_fvg = self.fvg_detector.get_unfilled_fvgs(
            fvgs, FVGType.BEARISH
        )

        # POI 확인
        if not active_ob and not unfilled_fvg:
            return

        # 가장 가까운 POI 찾기
        nearest_ob = None
        if active_ob:
            nearest_ob = min(
                active_ob,
                key=lambda ob: abs(ob.midpoint - current_price)
            )

        nearest_fvg = None
        if unfilled_fvg:
            nearest_fvg = self.fvg_detector.get_nearest_fvg(
                fvgs, current_price, FVGType.BEARISH
            )

        # Order Block 우선
        poi_level = nearest_ob.high if nearest_ob else (
            nearest_fvg.gap_high if nearest_fvg else None
        )

        if poi_level is None:
            return

        # 가격이 POI에 근접했는지 확인
        distance_pct = abs(current_price - poi_level) / current_price * 100
        if distance_pct > 1.0:
            return

        # 진입 실행
        self._execute_short_entry(current_price, poi_level, swept_levels)

    def _execute_long_entry(
        self,
        entry_price: float,
        poi_level: float,
        swept_levels: list
    ):
        """롱 포지션 진입"""
        # Stop Loss: 유동성 수집 지점 아래
        sell_side_swept = [
            lv for lv in swept_levels
            if lv.type == LiquidityType.SELL_SIDE and lv.swept
        ]

        if sell_side_swept:
            # 가장 최근 스윕된 레벨 사용
            latest_swept = max(sell_side_swept, key=lambda lv: lv.timestamp_idx)
            sl_reference = latest_swept.price
        else:
            sl_reference = poi_level

        stop_loss = self.risk_manager.calculate_stop_loss(
            entry_price=entry_price,
            order_block_level=sl_reference,
            is_long=True,
            buffer_pct=0.1
        )

        # Take Profit: 위쪽 유동성 레벨
        buy_side_liquidity = [
            lv for lv in self.liquidity_detector.liquidity_levels
            if lv.type == LiquidityType.BUY_SIDE and not lv.swept
        ]

        target_liq = None
        if buy_side_liquidity:
            # 가장 가까운 위쪽 유동성
            above_price = [lv for lv in buy_side_liquidity if lv.price > entry_price]
            if above_price:
                target_liq = min(above_price, key=lambda lv: lv.price).price

        take_profit = self.risk_manager.calculate_take_profit(
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_liquidity=target_liq,
            is_long=True
        )

        # 거래 유효성 검증
        is_valid, message = self.risk_manager.validate_trade(
            entry_price, stop_loss, take_profit, is_long=True
        )

        if not is_valid:
            self.log.warning(f"Long trade invalid: {message}")
            return

        # 포지션 사이즈 계산
        account_balance = self.portfolio.account(self.venue).balance_total().as_double()
        position_size, risk_amount = self.risk_manager.calculate_position_size(
            account_balance=account_balance,
            entry_price=entry_price,
            stop_loss=stop_loss,
            leverage=self.leverage
        )

        self.log.info(
            f"LONG Entry: Price={entry_price:.2f}, "
            f"SL={stop_loss:.2f}, TP={take_profit:.2f}, "
            f"Size={position_size:.4f}, Risk=${risk_amount:.2f}, "
            f"{message}"
        )

        # 주문 제출 (실제 구현 시 주문 생성 로직 추가)
        # self.submit_order(...)

    def _execute_short_entry(
        self,
        entry_price: float,
        poi_level: float,
        swept_levels: list
    ):
        """숏 포지션 진입"""
        # Stop Loss: 유동성 수집 지점 위
        buy_side_swept = [
            lv for lv in swept_levels
            if lv.type == LiquidityType.BUY_SIDE and lv.swept
        ]

        if buy_side_swept:
            latest_swept = max(buy_side_swept, key=lambda lv: lv.timestamp_idx)
            sl_reference = latest_swept.price
        else:
            sl_reference = poi_level

        stop_loss = self.risk_manager.calculate_stop_loss(
            entry_price=entry_price,
            order_block_level=sl_reference,
            is_long=False,
            buffer_pct=0.1
        )

        # Take Profit: 아래쪽 유동성 레벨
        sell_side_liquidity = [
            lv for lv in self.liquidity_detector.liquidity_levels
            if lv.type == LiquidityType.SELL_SIDE and not lv.swept
        ]

        target_liq = None
        if sell_side_liquidity:
            below_price = [lv for lv in sell_side_liquidity if lv.price < entry_price]
            if below_price:
                target_liq = max(below_price, key=lambda lv: lv.price).price

        take_profit = self.risk_manager.calculate_take_profit(
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_liquidity=target_liq,
            is_long=False
        )

        # 거래 유효성 검증
        is_valid, message = self.risk_manager.validate_trade(
            entry_price, stop_loss, take_profit, is_long=False
        )

        if not is_valid:
            self.log.warning(f"Short trade invalid: {message}")
            return

        # 포지션 사이즈 계산
        account_balance = self.portfolio.account(self.venue).balance_total().as_double()
        position_size, risk_amount = self.risk_manager.calculate_position_size(
            account_balance=account_balance,
            entry_price=entry_price,
            stop_loss=stop_loss,
            leverage=self.leverage
        )

        self.log.info(
            f"SHORT Entry: Price={entry_price:.2f}, "
            f"SL={stop_loss:.2f}, TP={take_profit:.2f}, "
            f"Size={position_size:.4f}, Risk=${risk_amount:.2f}, "
            f"{message}"
        )

        # 주문 제출 (실제 구현 시 주문 생성 로직 추가)
        # self.submit_order(...)

    def _manage_position(self, current_price: float):
        """
        포지션 관리 (청산 로직)

        Parameters
        ----------
        current_price : float
            현재 가격
        """
        # 실제 구현 시 포지션 관리 로직 추가
        # - Trailing Stop
        # - Partial Exit
        # - Break Even 이동
        pass

    def on_event(self, event: Event):
        """이벤트 처리"""
        pass
