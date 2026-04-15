"""
Market Structure Analysis: Swing Highs/Lows, BOS, CHoCH, Trend Bias.

ICT Concepts:
- Swing High / Swing Low identification
- Break of Structure (BOS): confirms trend continuation
- Change of Character (CHoCH): first sign of trend reversal
- Higher High (HH), Higher Low (HL), Lower High (LH), Lower Low (LL)
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SwingPoint:
    index: int
    timestamp: pd.Timestamp
    price: float
    kind: str          # 'high' or 'low'
    strength: int      # number of candles on each side confirming it


@dataclass
class StructureEvent:
    index: int
    timestamp: pd.Timestamp
    price: float
    event_type: str    # 'BOS_bull', 'BOS_bear', 'CHoCH_bull', 'CHoCH_bear'
    broken_swing: SwingPoint
    confirmed: bool = True


@dataclass
class MarketStructureResult:
    trend: str                            # 'bullish', 'bearish', 'ranging'
    swing_highs: list[SwingPoint] = field(default_factory=list)
    swing_lows: list[SwingPoint] = field(default_factory=list)
    bos_events: list[StructureEvent] = field(default_factory=list)
    choch_events: list[StructureEvent] = field(default_factory=list)
    last_bos: Optional[StructureEvent] = None
    last_choch: Optional[StructureEvent] = None
    last_hh: Optional[SwingPoint] = None
    last_hl: Optional[SwingPoint] = None
    last_lh: Optional[SwingPoint] = None
    last_ll: Optional[SwingPoint] = None


class MarketStructureAnalyzer:
    """Identifies swing points, BOS, and CHoCH from OHLCV data."""

    def __init__(self, settings: dict):
        cfg = settings["market_structure"]
        self.swing_strength = cfg.get("swing_strength", 5)
        self.bos_confirmation = cfg.get("bos_confirmation", True)
        self.choch_detection = cfg.get("choch_detection", True)
        self.trend_lookback = cfg.get("trend_lookback", 20)

    def _find_swings(self, df: pd.DataFrame) -> tuple[list[SwingPoint], list[SwingPoint]]:
        """Detect swing highs and lows using pivot point method."""
        highs: list[SwingPoint] = []
        lows: list[SwingPoint] = []
        n = len(df)
        s = self.swing_strength

        for i in range(s, n - s):
            window_high = df["high"].iloc[i - s: i + s + 1]
            window_low = df["low"].iloc[i - s: i + s + 1]
            current_high = df["high"].iloc[i]
            current_low = df["low"].iloc[i]

            if current_high == window_high.max():
                highs.append(SwingPoint(
                    index=i,
                    timestamp=df.index[i],
                    price=current_high,
                    kind="high",
                    strength=s,
                ))

            if current_low == window_low.min():
                lows.append(SwingPoint(
                    index=i,
                    timestamp=df.index[i],
                    price=current_low,
                    kind="low",
                    strength=s,
                ))

        return highs, lows

    def _classify_swings(
        self,
        swing_highs: list[SwingPoint],
        swing_lows: list[SwingPoint],
    ) -> tuple[list[str], list[str]]:
        """Label each swing as HH/LH and HL/LL."""
        high_labels = []
        for i, sh in enumerate(swing_highs):
            if i == 0:
                high_labels.append("SH")
            else:
                high_labels.append("HH" if sh.price > swing_highs[i - 1].price else "LH")

        low_labels = []
        for i, sl in enumerate(swing_lows):
            if i == 0:
                low_labels.append("SL")
            else:
                low_labels.append("HL" if sl.price > swing_lows[i - 1].price else "LL")

        return high_labels, low_labels

    def _detect_bos_choch(
        self,
        df: pd.DataFrame,
        swing_highs: list[SwingPoint],
        swing_lows: list[SwingPoint],
        high_labels: list[str],
        low_labels: list[str],
    ) -> tuple[list[StructureEvent], list[StructureEvent]]:
        """Detect BOS and CHoCH events."""
        bos_events: list[StructureEvent] = []
        choch_events: list[StructureEvent] = []

        # Track trend state: +1 = bullish, -1 = bearish, 0 = unknown
        trend_state = 0
        last_hh_idx = -1
        last_ll_idx = -1

        all_swings = sorted(
            [(sh, "high", high_labels[i]) for i, sh in enumerate(swing_highs)] +
            [(sl, "low", low_labels[i]) for i, sl in enumerate(swing_lows)],
            key=lambda x: x[0].index
        )

        for sp, kind, label in all_swings:
            # Look for candles after this swing that break it
            start_idx = sp.index + 1
            if start_idx >= len(df):
                continue

            future = df.iloc[start_idx:]

            if kind == "high":
                # Check if future price breaks above this swing high
                broken_at = future[future["close"] > sp.price]
                if broken_at.empty:
                    continue
                break_idx = broken_at.index[0]
                break_i = df.index.get_loc(break_idx)

                if trend_state <= 0:
                    # Was bearish/neutral -> breaking above = CHoCH bullish
                    if self.choch_detection and label in ("LH", "SH"):
                        choch_events.append(StructureEvent(
                            index=break_i,
                            timestamp=break_idx,
                            price=sp.price,
                            event_type="CHoCH_bull",
                            broken_swing=sp,
                        ))
                        trend_state = 1
                else:
                    # Already bullish -> breaking above = BOS bullish
                    if label == "HH":
                        bos_events.append(StructureEvent(
                            index=break_i,
                            timestamp=break_idx,
                            price=sp.price,
                            event_type="BOS_bull",
                            broken_swing=sp,
                        ))
                        last_hh_idx = break_i

            elif kind == "low":
                # Check if future price breaks below this swing low
                broken_at = future[future["close"] < sp.price]
                if broken_at.empty:
                    continue
                break_idx = broken_at.index[0]
                break_i = df.index.get_loc(break_idx)

                if trend_state >= 0:
                    # Was bullish/neutral -> breaking below = CHoCH bearish
                    if self.choch_detection and label in ("HL", "SL"):
                        choch_events.append(StructureEvent(
                            index=break_i,
                            timestamp=break_idx,
                            price=sp.price,
                            event_type="CHoCH_bear",
                            broken_swing=sp,
                        ))
                        trend_state = -1
                else:
                    # Already bearish -> breaking below = BOS bearish
                    if label == "LL":
                        bos_events.append(StructureEvent(
                            index=break_i,
                            timestamp=break_idx,
                            price=sp.price,
                            event_type="BOS_bear",
                            broken_swing=sp,
                        ))
                        last_ll_idx = break_i

        return bos_events, choch_events

    def _determine_trend(
        self,
        df: pd.DataFrame,
        swing_highs: list[SwingPoint],
        swing_lows: list[SwingPoint],
        bos_events: list[StructureEvent],
        choch_events: list[StructureEvent],
    ) -> str:
        """Determine current market trend from recent structure."""
        all_events = sorted(bos_events + choch_events, key=lambda e: e.index)
        if not all_events:
            # Fallback: use simple HH/HL or LH/LL over lookback
            recent_highs = [sh.price for sh in swing_highs[-self.trend_lookback:]]
            recent_lows = [sl.price for sl in swing_lows[-self.trend_lookback:]]
            if len(recent_highs) >= 2 and len(recent_lows) >= 2:
                if recent_highs[-1] > recent_highs[-2] and recent_lows[-1] > recent_lows[-2]:
                    return "bullish"
                if recent_highs[-1] < recent_highs[-2] and recent_lows[-1] < recent_lows[-2]:
                    return "bearish"
            return "ranging"

        last_event = all_events[-1]
        if last_event.event_type in ("BOS_bull", "CHoCH_bull"):
            return "bullish"
        if last_event.event_type in ("BOS_bear", "CHoCH_bear"):
            return "bearish"
        return "ranging"

    def analyze(self, df: pd.DataFrame) -> MarketStructureResult:
        """Run full market structure analysis on a DataFrame."""
        swing_highs, swing_lows = self._find_swings(df)
        high_labels, low_labels = self._classify_swings(swing_highs, swing_lows)
        bos_events, choch_events = self._detect_bos_choch(
            df, swing_highs, swing_lows, high_labels, low_labels
        )
        trend = self._determine_trend(df, swing_highs, swing_lows, bos_events, choch_events)

        # Find labeled HH/HL/LH/LL
        hh_list = [sh for sh, lbl in zip(swing_highs, high_labels) if lbl == "HH"]
        hl_list = [sl for sl, lbl in zip(swing_lows, low_labels) if lbl == "HL"]
        lh_list = [sh for sh, lbl in zip(swing_highs, high_labels) if lbl == "LH"]
        ll_list = [sl for sl, lbl in zip(swing_lows, low_labels) if lbl == "LL"]

        return MarketStructureResult(
            trend=trend,
            swing_highs=swing_highs,
            swing_lows=swing_lows,
            bos_events=bos_events,
            choch_events=choch_events,
            last_bos=bos_events[-1] if bos_events else None,
            last_choch=choch_events[-1] if choch_events else None,
            last_hh=hh_list[-1] if hh_list else None,
            last_hl=hl_list[-1] if hl_list else None,
            last_lh=lh_list[-1] if lh_list else None,
            last_ll=ll_list[-1] if ll_list else None,
        )
