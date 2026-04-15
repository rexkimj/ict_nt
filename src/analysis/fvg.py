"""
Fair Value Gap (FVG) Detection.

ICT Concepts:
- Bullish FVG: candle[i-2].high < candle[i].low
  The gap between candle 1's high and candle 3's low represents an imbalance.
  Price tends to return to fill this gap.

- Bearish FVG: candle[i-2].low > candle[i].high
  The gap between candle 1's low and candle 3's high represents an imbalance.

- Inverse FVG (IFVG): An FVG that has been fully filled becomes an opposing signal zone.

- Partial Fill: When price enters but doesn't fully close the FVG.
- Full Fill: When price completely closes through the FVG.

- FVG + OB confluence: When an FVG overlaps with an Order Block, significantly
  increases the probability of a reaction.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FairValueGap:
    index: int                 # index of the middle (displacement) candle
    timestamp: pd.Timestamp
    kind: str                  # 'bullish' or 'bearish'
    top: float
    bottom: float
    gap_pct: float             # gap size as % of price
    is_filled: bool = False
    fill_pct: float = 0.0      # 0–100 how much has been filled
    is_inverse: bool = False   # became IFVG after full fill
    fill_timestamp: Optional[pd.Timestamp] = None
    confluence_ob: bool = False

    @property
    def midpoint(self) -> float:
        return (self.top + self.bottom) / 2

    @property
    def size(self) -> float:
        return self.top - self.bottom

    def contains_price(self, price: float) -> bool:
        return self.bottom <= price <= self.top

    def is_near(self, price: float, tolerance_pct: float = 0.001) -> bool:
        tol = self.size * tolerance_pct * 100
        return (self.bottom - tol) <= price <= (self.top + tol)


@dataclass
class FVGResult:
    bullish_fvgs: list[FairValueGap] = field(default_factory=list)
    bearish_fvgs: list[FairValueGap] = field(default_factory=list)
    inverse_fvgs: list[FairValueGap] = field(default_factory=list)
    nearest_bullish_fvg: Optional[FairValueGap] = None
    nearest_bearish_fvg: Optional[FairValueGap] = None

    @property
    def all_active(self) -> list[FairValueGap]:
        return [fvg for fvg in self.bullish_fvgs + self.bearish_fvgs if not fvg.is_filled]


class FVGDetector:
    """Detects Fair Value Gaps (FVGs) and Inverse FVGs from OHLCV data."""

    def __init__(self, settings: dict):
        cfg = settings["fvg"]
        self.min_gap_pct = cfg.get("min_gap_pct", 0.05)
        self.max_lookback = cfg.get("max_lookback", 100)
        self.partial_fill_pct = cfg.get("partial_fill_pct", 0.5)
        self.detect_inverse = cfg.get("inverse_fvg", True)
        self.confluence_ob_flag = cfg.get("confluence_ob", True)

    def _check_fill(self, fvg: FairValueGap, df: pd.DataFrame) -> FairValueGap:
        """Check how much of the FVG has been filled by subsequent price action."""
        future = df.iloc[fvg.index + 2:]  # skip middle + candle 3

        for ts, row in future.iterrows():
            if fvg.kind == "bullish":
                # Price enters FVG from above (retrace down)
                if row["low"] <= fvg.top:
                    penetration = fvg.top - max(row["low"], fvg.bottom)
                    fvg.fill_pct = min(100.0, penetration / fvg.size * 100)
                    if row["close"] <= fvg.bottom:
                        fvg.is_filled = True
                        fvg.fill_timestamp = ts
                        break
            else:  # bearish
                # Price enters FVG from below (retrace up)
                if row["high"] >= fvg.bottom:
                    penetration = min(row["high"], fvg.top) - fvg.bottom
                    fvg.fill_pct = min(100.0, penetration / fvg.size * 100)
                    if row["close"] >= fvg.top:
                        fvg.is_filled = True
                        fvg.fill_timestamp = ts
                        break
        return fvg

    def detect(self, df: pd.DataFrame) -> FVGResult:
        """Run FVG detection on full DataFrame."""
        bullish_fvgs: list[FairValueGap] = []
        bearish_fvgs: list[FairValueGap] = []
        inverse_fvgs: list[FairValueGap] = []

        n = len(df)
        lookback_start = max(0, n - self.max_lookback)

        for i in range(lookback_start + 1, n - 1):
            c1 = df.iloc[i - 1]   # first candle
            c2 = df.iloc[i]       # middle / displacement candle
            c3 = df.iloc[i + 1]   # third candle

            # --- Bullish FVG: gap between c1.high and c3.low ---
            if c3["low"] > c1["high"]:
                gap_size = c3["low"] - c1["high"]
                gap_pct = gap_size / c1["high"] * 100
                if gap_pct >= self.min_gap_pct:
                    fvg = FairValueGap(
                        index=i,
                        timestamp=df.index[i],
                        kind="bullish",
                        top=c3["low"],
                        bottom=c1["high"],
                        gap_pct=gap_pct,
                    )
                    fvg = self._check_fill(fvg, df)
                    bullish_fvgs.append(fvg)

                    # IFVG: fully filled bullish FVG → becomes bearish signal
                    if self.detect_inverse and fvg.is_filled:
                        ifvg = FairValueGap(
                            index=fvg.index,
                            timestamp=fvg.timestamp,
                            kind="bearish",
                            top=fvg.top,
                            bottom=fvg.bottom,
                            gap_pct=fvg.gap_pct,
                            is_inverse=True,
                        )
                        inverse_fvgs.append(ifvg)

            # --- Bearish FVG: gap between c1.low and c3.high ---
            if c3["high"] < c1["low"]:
                gap_size = c1["low"] - c3["high"]
                gap_pct = gap_size / c1["low"] * 100
                if gap_pct >= self.min_gap_pct:
                    fvg = FairValueGap(
                        index=i,
                        timestamp=df.index[i],
                        kind="bearish",
                        top=c1["low"],
                        bottom=c3["high"],
                        gap_pct=gap_pct,
                    )
                    fvg = self._check_fill(fvg, df)
                    bearish_fvgs.append(fvg)

                    # IFVG: fully filled bearish FVG → becomes bullish signal
                    if self.detect_inverse and fvg.is_filled:
                        ifvg = FairValueGap(
                            index=fvg.index,
                            timestamp=fvg.timestamp,
                            kind="bullish",
                            top=fvg.top,
                            bottom=fvg.bottom,
                            gap_pct=fvg.gap_pct,
                            is_inverse=True,
                        )
                        inverse_fvgs.append(ifvg)

        # Find nearest active FVGs to current price
        current_price = df["close"].iloc[-1]
        active_bull = [f for f in bullish_fvgs if not f.is_filled]
        active_bear = [f for f in bearish_fvgs if not f.is_filled]

        nearest_bull = None
        if active_bull:
            below = [f for f in active_bull if f.top < current_price]
            if below:
                nearest_bull = max(below, key=lambda f: f.top)

        nearest_bear = None
        if active_bear:
            above = [f for f in active_bear if f.bottom > current_price]
            if above:
                nearest_bear = min(above, key=lambda f: f.bottom)

        return FVGResult(
            bullish_fvgs=bullish_fvgs,
            bearish_fvgs=bearish_fvgs,
            inverse_fvgs=inverse_fvgs,
            nearest_bullish_fvg=nearest_bull,
            nearest_bearish_fvg=nearest_bear,
        )
