"""
Order Block (OB) Detection.

ICT Concepts:
- Bullish OB: Last bearish candle before a strong bullish displacement that breaks structure.
             Price is expected to return to this zone and react bullishly.
- Bearish OB: Last bullish candle before a strong bearish displacement that breaks structure.
             Price is expected to return to this zone and react bearishly.
- Breaker Block: An OB that has been mitigated (price returned and closed through it),
                 then becomes an opposing OB.
- Mitigation: When price returns to the OB zone (top/bottom 50% acts as entry).
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OrderBlock:
    index: int
    timestamp: pd.Timestamp
    kind: str              # 'bullish' or 'bearish'
    top: float
    bottom: float
    origin_candle_open: float
    origin_candle_close: float
    displacement_pct: float   # strength of move after OB
    body_ratio: float          # body / range of the OB candle
    is_breaker: bool = False
    is_mitigated: bool = False
    mitigation_price: Optional[float] = None
    mitigation_timestamp: Optional[pd.Timestamp] = None
    confluence_fvg: bool = False

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
class OrderBlockResult:
    bullish_obs: list[OrderBlock] = field(default_factory=list)
    bearish_obs: list[OrderBlock] = field(default_factory=list)
    breaker_blocks: list[OrderBlock] = field(default_factory=list)
    nearest_bullish_ob: Optional[OrderBlock] = None
    nearest_bearish_ob: Optional[OrderBlock] = None

    @property
    def all_active(self) -> list[OrderBlock]:
        return [ob for ob in self.bullish_obs + self.bearish_obs if not ob.is_mitigated]


class OrderBlockDetector:
    """Detects bullish and bearish Order Blocks from OHLCV data."""

    def __init__(self, settings: dict):
        cfg = settings["order_block"]
        self.min_displacement_pct = cfg.get("min_displacement_pct", 0.3)
        self.min_body_ratio = cfg.get("min_body_ratio", 0.4)
        self.max_lookback = cfg.get("max_lookback", 50)
        self.mitigation_threshold = cfg.get("mitigation_threshold", 0.5)
        self.valid_candles_min = cfg.get("valid_candles_min", 3)
        self.breaker_block = cfg.get("breaker_block", True)

    def _calc_displacement(self, df: pd.DataFrame, start_idx: int, direction: str) -> float:
        """Measure displacement % from a candle forward."""
        if start_idx >= len(df) - 1:
            return 0.0
        origin_price = df["close"].iloc[start_idx]
        future_slice = df.iloc[start_idx + 1: start_idx + self.valid_candles_min + 3]
        if future_slice.empty:
            return 0.0
        if direction == "up":
            peak = future_slice["high"].max()
            return (peak - origin_price) / origin_price * 100
        else:
            trough = future_slice["low"].min()
            return (origin_price - trough) / origin_price * 100

    def _check_mitigation(
        self,
        ob: OrderBlock,
        df: pd.DataFrame,
    ) -> OrderBlock:
        """Check whether price has returned to mitigate the OB."""
        future = df.iloc[ob.index + 1:]
        for ts, row in future.iterrows():
            if ob.kind == "bullish":
                # Mitigated when price trades into the OB (touches top down to midpoint)
                if row["low"] <= ob.top:
                    ob.mitigation_timestamp = ts
                    ob.mitigation_price = row["low"]
                    # Full mitigation: close below bottom
                    if row["close"] < ob.bottom:
                        ob.is_mitigated = True
                    break
            else:  # bearish
                if row["high"] >= ob.bottom:
                    ob.mitigation_timestamp = ts
                    ob.mitigation_price = row["high"]
                    if row["close"] > ob.top:
                        ob.is_mitigated = True
                    break
        return ob

    def detect(self, df: pd.DataFrame) -> OrderBlockResult:
        """Run Order Block detection on full DataFrame."""
        bullish_obs: list[OrderBlock] = []
        bearish_obs: list[OrderBlock] = []

        n = len(df)
        lookback_start = max(0, n - self.max_lookback)

        for i in range(lookback_start, n - self.valid_candles_min):
            row = df.iloc[i]
            body_ratio = row["body"] / row["range"] if row["range"] > 0 else 0

            # --- Bullish OB: bearish candle before bullish displacement ---
            if row["bearish"] and body_ratio >= self.min_body_ratio:
                displacement = self._calc_displacement(df, i, "up")
                if displacement >= self.min_displacement_pct:
                    # Confirm the following candles are bullish (displacement)
                    next_candles = df.iloc[i + 1: i + self.valid_candles_min + 1]
                    bullish_count = next_candles["bullish"].sum()
                    if bullish_count >= max(1, self.valid_candles_min // 2):
                        ob = OrderBlock(
                            index=i,
                            timestamp=df.index[i],
                            kind="bullish",
                            top=row["open"],        # bearish candle: open > close
                            bottom=row["close"],
                            origin_candle_open=row["open"],
                            origin_candle_close=row["close"],
                            displacement_pct=displacement,
                            body_ratio=body_ratio,
                        )
                        ob = self._check_mitigation(ob, df)
                        bullish_obs.append(ob)

            # --- Bearish OB: bullish candle before bearish displacement ---
            if row["bullish"] and body_ratio >= self.min_body_ratio:
                displacement = self._calc_displacement(df, i, "down")
                if displacement >= self.min_displacement_pct:
                    next_candles = df.iloc[i + 1: i + self.valid_candles_min + 1]
                    bearish_count = next_candles["bearish"].sum()
                    if bearish_count >= max(1, self.valid_candles_min // 2):
                        ob = OrderBlock(
                            index=i,
                            timestamp=df.index[i],
                            kind="bearish",
                            top=row["close"],       # bullish candle: close > open
                            bottom=row["open"],
                            origin_candle_open=row["open"],
                            origin_candle_close=row["close"],
                            displacement_pct=displacement,
                            body_ratio=body_ratio,
                        )
                        ob = self._check_mitigation(ob, df)
                        bearish_obs.append(ob)

        # --- Breaker Blocks: mitigated OBs that flip polarity ---
        breaker_blocks: list[OrderBlock] = []
        if self.breaker_block:
            for ob in bullish_obs + bearish_obs:
                if ob.is_mitigated:
                    breaker = OrderBlock(
                        index=ob.index,
                        timestamp=ob.timestamp,
                        kind="bearish" if ob.kind == "bullish" else "bullish",
                        top=ob.top,
                        bottom=ob.bottom,
                        origin_candle_open=ob.origin_candle_open,
                        origin_candle_close=ob.origin_candle_close,
                        displacement_pct=ob.displacement_pct,
                        body_ratio=ob.body_ratio,
                        is_breaker=True,
                    )
                    breaker_blocks.append(breaker)

        # Find nearest active OBs to current price
        current_price = df["close"].iloc[-1]
        active_bull = [ob for ob in bullish_obs if not ob.is_mitigated]
        active_bear = [ob for ob in bearish_obs if not ob.is_mitigated]

        nearest_bull = None
        if active_bull:
            below_price = [ob for ob in active_bull if ob.top < current_price]
            if below_price:
                nearest_bull = max(below_price, key=lambda ob: ob.top)

        nearest_bear = None
        if active_bear:
            above_price = [ob for ob in active_bear if ob.bottom > current_price]
            if above_price:
                nearest_bear = min(above_price, key=lambda ob: ob.bottom)

        return OrderBlockResult(
            bullish_obs=bullish_obs,
            bearish_obs=bearish_obs,
            breaker_blocks=breaker_blocks,
            nearest_bullish_ob=nearest_bull,
            nearest_bearish_ob=nearest_bear,
        )
