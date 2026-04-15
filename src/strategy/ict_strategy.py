"""
ICT Strategy Engine.

Combines Market Structure, Order Blocks, FVGs, and Liquidity into
actionable trade setups with confluence scoring and risk/reward calculation.

Optimal Trade Entry (OTE) Logic:
1. Identify HTF bias (bullish/bearish) via market structure
2. Wait for liquidity sweep in the direction of the bias
3. Confirm BOS or CHoCH on LTF
4. Find OB or FVG in the premium/discount zone
5. Score confluence and calculate R:R
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

from src.analysis.market_structure import MarketStructureAnalyzer, MarketStructureResult
from src.analysis.order_block import OrderBlockDetector, OrderBlockResult, OrderBlock
from src.analysis.fvg import FVGDetector, FVGResult, FairValueGap
from src.analysis.liquidity import LiquidityAnalyzer, LiquidityResult


@dataclass
class TradeSetup:
    symbol: str
    timeframe: str
    direction: str            # 'long' or 'short'
    bias: str                 # HTF bias: 'bullish' / 'bearish'
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    confluence_score: int
    confluence_reasons: list[str]

    # Key levels
    ob: Optional[OrderBlock] = None
    fvg: Optional[FairValueGap] = None
    liquidity_target: Optional[float] = None
    invalidation_price: Optional[float] = None

    @property
    def risk_pct(self) -> float:
        return abs(self.entry_price - self.stop_loss) / self.entry_price * 100

    @property
    def reward_pct(self) -> float:
        return abs(self.take_profit - self.entry_price) / self.entry_price * 100

    def summary(self) -> str:
        direction_icon = "LONG" if self.direction == "long" else "SHORT"
        return (
            f"[{direction_icon}] {self.symbol} @ {self.entry_price:.4f} | "
            f"SL: {self.stop_loss:.4f} | TP: {self.take_profit:.4f} | "
            f"R:R {self.risk_reward:.2f} | Score: {self.confluence_score}"
        )


@dataclass
class MarketAnalysisSnapshot:
    symbol: str
    current_price: float
    htf_trend: str
    mtf_trend: str
    ltf_trend: str
    session_info: dict
    htf_structure: MarketStructureResult
    ltf_structure: MarketStructureResult
    ob_result: OrderBlockResult
    fvg_result: FVGResult
    liquidity_result: LiquidityResult
    setups: list[TradeSetup] = field(default_factory=list)
    premium_discount: str = "equilibrium"  # 'premium', 'discount', 'equilibrium'


class ICTStrategy:
    """
    Full ICT analysis engine.
    Orchestrates all sub-analyzers and generates scored trade setups.
    """

    def __init__(self, settings: dict):
        self.settings = settings
        self.ms_analyzer = MarketStructureAnalyzer(settings)
        self.ob_detector = OrderBlockDetector(settings)
        self.fvg_detector = FVGDetector(settings)
        self.liq_analyzer = LiquidityAnalyzer(settings)
        self.min_score = settings["strategy"].get("confluence_min_score", 3)
        self.min_rr = settings["strategy"].get("risk_reward_min", 2.0)
        self.htf_bias_required = settings["strategy"].get("htf_bias_required", True)

    # ------------------------------------------------------------------
    # Premium / Discount Zone
    # ------------------------------------------------------------------
    def _get_premium_discount(self, df: pd.DataFrame, ms: MarketStructureResult) -> str:
        """
        Determine if price is in premium (above 50% of range) or discount zone.
        Uses the most recent swing high/low pair.
        """
        if not ms.swing_highs or not ms.swing_lows:
            return "equilibrium"

        recent_high = ms.swing_highs[-1].price
        recent_low = ms.swing_lows[-1].price
        current = df["close"].iloc[-1]
        midpoint = (recent_high + recent_low) / 2

        if current > midpoint * 1.001:
            return "premium"
        if current < midpoint * 0.999:
            return "discount"
        return "equilibrium"

    # ------------------------------------------------------------------
    # Confluence Scoring
    # ------------------------------------------------------------------
    def _score_long_setup(
        self,
        current_price: float,
        htf_ms: MarketStructureResult,
        ltf_ms: MarketStructureResult,
        ob_result: OrderBlockResult,
        fvg_result: FVGResult,
        liq_result: LiquidityResult,
        premium_discount: str,
    ) -> tuple[int, list[str]]:
        score = 0
        reasons = []

        # 1. HTF bullish bias
        if htf_ms.trend == "bullish":
            score += 2
            reasons.append("HTF bullish trend")

        # 2. LTF CHoCH or BOS bullish confirmation
        if ltf_ms.last_choch and ltf_ms.last_choch.event_type == "CHoCH_bull":
            score += 2
            reasons.append("LTF CHoCH bullish confirmed")
        elif ltf_ms.last_bos and ltf_ms.last_bos.event_type == "BOS_bull":
            score += 1
            reasons.append("LTF BOS bullish")

        # 3. SSL sweep (sell-side liquidity taken → reversal likely)
        if liq_result.recent_sweep_kind == "ssl":
            score += 2
            reasons.append("Recent SSL sweep (liquidity taken)")

        # 4. Bullish Order Block nearby
        if ob_result.nearest_bullish_ob:
            ob = ob_result.nearest_bullish_ob
            dist_pct = (current_price - ob.top) / current_price * 100
            if dist_pct < 0.5:
                score += 2
                reasons.append(f"In bullish OB zone ({ob.bottom:.4f}–{ob.top:.4f})")
            elif dist_pct < 2.0:
                score += 1
                reasons.append(f"Near bullish OB ({ob.bottom:.4f}–{ob.top:.4f})")

        # 5. Bullish FVG nearby
        if fvg_result.nearest_bullish_fvg:
            fvg = fvg_result.nearest_bullish_fvg
            dist_pct = (current_price - fvg.top) / current_price * 100
            if dist_pct < 0.5:
                score += 2
                reasons.append(f"In bullish FVG ({fvg.bottom:.4f}–{fvg.top:.4f})")
            elif dist_pct < 2.0:
                score += 1
                reasons.append(f"Near bullish FVG ({fvg.bottom:.4f}–{fvg.top:.4f})")

        # 6. OB + FVG confluence
        if ob_result.nearest_bullish_ob and fvg_result.nearest_bullish_fvg:
            ob = ob_result.nearest_bullish_ob
            fvg = fvg_result.nearest_bullish_fvg
            if not (ob.top < fvg.bottom or fvg.top < ob.bottom):
                score += 1
                reasons.append("OB + FVG confluence overlap")

        # 7. Discount zone for longs
        if premium_discount == "discount":
            score += 1
            reasons.append("Price in discount zone")

        # 8. BSL target exists (take-profit destination)
        if liq_result.nearest_bsl:
            score += 1
            reasons.append(f"BSL target at {liq_result.nearest_bsl.price:.4f}")

        return score, reasons

    def _score_short_setup(
        self,
        current_price: float,
        htf_ms: MarketStructureResult,
        ltf_ms: MarketStructureResult,
        ob_result: OrderBlockResult,
        fvg_result: FVGResult,
        liq_result: LiquidityResult,
        premium_discount: str,
    ) -> tuple[int, list[str]]:
        score = 0
        reasons = []

        if htf_ms.trend == "bearish":
            score += 2
            reasons.append("HTF bearish trend")

        if ltf_ms.last_choch and ltf_ms.last_choch.event_type == "CHoCH_bear":
            score += 2
            reasons.append("LTF CHoCH bearish confirmed")
        elif ltf_ms.last_bos and ltf_ms.last_bos.event_type == "BOS_bear":
            score += 1
            reasons.append("LTF BOS bearish")

        if liq_result.recent_sweep_kind == "bsl":
            score += 2
            reasons.append("Recent BSL sweep (liquidity taken)")

        if ob_result.nearest_bearish_ob:
            ob = ob_result.nearest_bearish_ob
            dist_pct = (ob.bottom - current_price) / current_price * 100
            if dist_pct < 0.5:
                score += 2
                reasons.append(f"In bearish OB zone ({ob.bottom:.4f}–{ob.top:.4f})")
            elif dist_pct < 2.0:
                score += 1
                reasons.append(f"Near bearish OB ({ob.bottom:.4f}–{ob.top:.4f})")

        if fvg_result.nearest_bearish_fvg:
            fvg = fvg_result.nearest_bearish_fvg
            dist_pct = (fvg.bottom - current_price) / current_price * 100
            if dist_pct < 0.5:
                score += 2
                reasons.append(f"In bearish FVG ({fvg.bottom:.4f}–{fvg.top:.4f})")
            elif dist_pct < 2.0:
                score += 1
                reasons.append(f"Near bearish FVG ({fvg.bottom:.4f}–{fvg.top:.4f})")

        if ob_result.nearest_bearish_ob and fvg_result.nearest_bearish_fvg:
            ob = ob_result.nearest_bearish_ob
            fvg = fvg_result.nearest_bearish_fvg
            if not (ob.top < fvg.bottom or fvg.top < ob.bottom):
                score += 1
                reasons.append("OB + FVG confluence overlap")

        if premium_discount == "premium":
            score += 1
            reasons.append("Price in premium zone")

        if liq_result.nearest_ssl:
            score += 1
            reasons.append(f"SSL target at {liq_result.nearest_ssl.price:.4f}")

        return score, reasons

    # ------------------------------------------------------------------
    # Setup Builder
    # ------------------------------------------------------------------
    def _build_long_setup(
        self,
        symbol: str,
        timeframe: str,
        current_price: float,
        htf_ms: MarketStructureResult,
        ob_result: OrderBlockResult,
        fvg_result: FVGResult,
        liq_result: LiquidityResult,
        score: int,
        reasons: list[str],
    ) -> Optional[TradeSetup]:
        """Build a long trade setup with entry, SL, TP."""
        # Entry: midpoint of nearest OB or FVG (whichever is closer)
        entry = current_price
        ob = ob_result.nearest_bullish_ob
        fvg = fvg_result.nearest_bullish_fvg

        if ob and fvg:
            entry = max(ob.midpoint, fvg.midpoint)
        elif ob:
            entry = ob.midpoint
        elif fvg:
            entry = fvg.midpoint
        else:
            return None

        # Stop Loss: below OB bottom or FVG bottom (with small buffer)
        sl_candidates = []
        if ob:
            sl_candidates.append(ob.bottom * 0.999)
        if fvg:
            sl_candidates.append(fvg.bottom * 0.999)
        stop_loss = min(sl_candidates) if sl_candidates else entry * 0.99

        # Take Profit: nearest BSL or next swing high
        if liq_result.nearest_bsl and liq_result.nearest_bsl.price > entry:
            take_profit = liq_result.nearest_bsl.price
        elif htf_ms.last_hh:
            take_profit = htf_ms.last_hh.price
        else:
            take_profit = entry * (1 + (entry - stop_loss) / entry * self.min_rr)

        risk = entry - stop_loss
        if risk <= 0:
            return None
        reward = take_profit - entry
        rr = reward / risk

        if rr < self.min_rr:
            return None

        return TradeSetup(
            symbol=symbol,
            timeframe=timeframe,
            direction="long",
            bias=htf_ms.trend,
            entry_price=round(entry, 6),
            stop_loss=round(stop_loss, 6),
            take_profit=round(take_profit, 6),
            risk_reward=round(rr, 2),
            confluence_score=score,
            confluence_reasons=reasons,
            ob=ob,
            fvg=fvg,
            liquidity_target=liq_result.nearest_bsl.price if liq_result.nearest_bsl else None,
            invalidation_price=round(stop_loss, 6),
        )

    def _build_short_setup(
        self,
        symbol: str,
        timeframe: str,
        current_price: float,
        htf_ms: MarketStructureResult,
        ob_result: OrderBlockResult,
        fvg_result: FVGResult,
        liq_result: LiquidityResult,
        score: int,
        reasons: list[str],
    ) -> Optional[TradeSetup]:
        """Build a short trade setup with entry, SL, TP."""
        entry = current_price
        ob = ob_result.nearest_bearish_ob
        fvg = fvg_result.nearest_bearish_fvg

        if ob and fvg:
            entry = min(ob.midpoint, fvg.midpoint)
        elif ob:
            entry = ob.midpoint
        elif fvg:
            entry = fvg.midpoint
        else:
            return None

        sl_candidates = []
        if ob:
            sl_candidates.append(ob.top * 1.001)
        if fvg:
            sl_candidates.append(fvg.top * 1.001)
        stop_loss = max(sl_candidates) if sl_candidates else entry * 1.01

        if liq_result.nearest_ssl and liq_result.nearest_ssl.price < entry:
            take_profit = liq_result.nearest_ssl.price
        elif htf_ms.last_ll:
            take_profit = htf_ms.last_ll.price
        else:
            take_profit = entry * (1 - (stop_loss - entry) / entry * self.min_rr)

        risk = stop_loss - entry
        if risk <= 0:
            return None
        reward = entry - take_profit
        rr = reward / risk

        if rr < self.min_rr:
            return None

        return TradeSetup(
            symbol=symbol,
            timeframe=timeframe,
            direction="short",
            bias=htf_ms.trend,
            entry_price=round(entry, 6),
            stop_loss=round(stop_loss, 6),
            take_profit=round(take_profit, 6),
            risk_reward=round(rr, 2),
            confluence_score=score,
            confluence_reasons=reasons,
            ob=ob,
            fvg=fvg,
            liquidity_target=liq_result.nearest_ssl.price if liq_result.nearest_ssl else None,
            invalidation_price=round(stop_loss, 6),
        )

    # ------------------------------------------------------------------
    # Main Analysis Entry Point
    # ------------------------------------------------------------------
    def analyze(
        self,
        symbol: str,
        htf_df: pd.DataFrame,
        ltf_df: pd.DataFrame,
        current_price: float,
        session_info: dict,
    ) -> MarketAnalysisSnapshot:
        """
        Run full ICT analysis across HTF and LTF.

        Args:
            symbol: Trading pair (e.g. 'BTC/USDT')
            htf_df: Higher timeframe DataFrame (e.g. 4h)
            ltf_df: Lower timeframe DataFrame (e.g. 15m)
            current_price: Live price
            session_info: Session activity dict
        """
        # 1. Market Structure
        htf_ms = self.ms_analyzer.analyze(htf_df)
        ltf_ms = self.ms_analyzer.analyze(ltf_df)

        # 2. Order Blocks (on LTF for precision entry)
        ob_result = self.ob_detector.detect(ltf_df)

        # 3. FVG (on LTF)
        fvg_result = self.fvg_detector.detect(ltf_df)

        # 4. Liquidity (HTF for macro levels, LTF for entry)
        liq_result = self.liq_analyzer.analyze(htf_df)

        # 5. Premium / Discount
        pd_zone = self._get_premium_discount(ltf_df, htf_ms)

        # 6. Score setups
        setups: list[TradeSetup] = []
        ltf_tf = self.settings["market"]["timeframes"].get("ltf", "15m")

        # Session filter
        if self.settings["strategy"]["session_filter"]["enabled"]:
            allowed = self.settings["strategy"]["session_filter"]["sessions"]
            active = session_info.get("active_sessions", [])
            if not any(s in active for s in allowed):
                # Outside kill zone — report but skip setup generation
                return MarketAnalysisSnapshot(
                    symbol=symbol,
                    current_price=current_price,
                    htf_trend=htf_ms.trend,
                    mtf_trend=htf_ms.trend,
                    ltf_trend=ltf_ms.trend,
                    session_info=session_info,
                    htf_structure=htf_ms,
                    ltf_structure=ltf_ms,
                    ob_result=ob_result,
                    fvg_result=fvg_result,
                    liquidity_result=liq_result,
                    setups=[],
                    premium_discount=pd_zone,
                )

        # Long setup
        long_score, long_reasons = self._score_long_setup(
            current_price, htf_ms, ltf_ms, ob_result, fvg_result, liq_result, pd_zone
        )
        if long_score >= self.min_score:
            if not self.htf_bias_required or htf_ms.trend == "bullish":
                long_setup = self._build_long_setup(
                    symbol, ltf_tf, current_price,
                    htf_ms, ob_result, fvg_result, liq_result,
                    long_score, long_reasons,
                )
                if long_setup:
                    setups.append(long_setup)

        # Short setup
        short_score, short_reasons = self._score_short_setup(
            current_price, htf_ms, ltf_ms, ob_result, fvg_result, liq_result, pd_zone
        )
        if short_score >= self.min_score:
            if not self.htf_bias_required or htf_ms.trend == "bearish":
                short_setup = self._build_short_setup(
                    symbol, ltf_tf, current_price,
                    htf_ms, ob_result, fvg_result, liq_result,
                    short_score, short_reasons,
                )
                if short_setup:
                    setups.append(short_setup)

        # Sort by score descending
        setups.sort(key=lambda s: (s.confluence_score, s.risk_reward), reverse=True)

        return MarketAnalysisSnapshot(
            symbol=symbol,
            current_price=current_price,
            htf_trend=htf_ms.trend,
            mtf_trend=htf_ms.trend,
            ltf_trend=ltf_ms.trend,
            session_info=session_info,
            htf_structure=htf_ms,
            ltf_structure=ltf_ms,
            ob_result=ob_result,
            fvg_result=fvg_result,
            liquidity_result=liq_result,
            setups=setups,
            premium_discount=pd_zone,
        )
