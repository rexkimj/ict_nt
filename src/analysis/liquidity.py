"""
Liquidity Analysis.

ICT Concepts:
- Buy-Side Liquidity (BSL): Resting stops above swing highs. Smart money targets
  these levels to sell into (short entry after BSL sweep).
- Sell-Side Liquidity (SSL): Resting stops below swing lows. Smart money targets
  these levels to buy into (long entry after SSL sweep).
- Equal Highs (EQH) / Equal Lows (EQL): Multiple touches at same level → liquidity pool.
- Liquidity Sweep: Price briefly trades beyond a liquidity level then reverses.
- Inducement: A smaller liquidity level engineered to trap retail traders before
  the real move to the larger liquidity pool.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LiquidityLevel:
    index: int
    timestamp: pd.Timestamp
    price: float
    kind: str              # 'bsl' (buy-side) or 'ssl' (sell-side)
    strength: int          # how many touches / equal levels
    is_swept: bool = False
    sweep_timestamp: Optional[pd.Timestamp] = None
    sweep_price: Optional[float] = None
    is_inducement: bool = False

    def is_near(self, price: float, tolerance_pct: float = 0.001) -> bool:
        tol = self.price * tolerance_pct
        return abs(price - self.price) <= tol


@dataclass
class SwingLiquidityPool:
    """A cluster of equal highs or equal lows forming a liquidity pool."""
    kind: str              # 'eqh' or 'eql'
    price: float
    touches: int
    first_timestamp: pd.Timestamp
    last_timestamp: pd.Timestamp
    is_swept: bool = False


@dataclass
class LiquidityResult:
    bsl_levels: list[LiquidityLevel] = field(default_factory=list)
    ssl_levels: list[LiquidityLevel] = field(default_factory=list)
    liquidity_pools: list[SwingLiquidityPool] = field(default_factory=list)
    swept_bsl: list[LiquidityLevel] = field(default_factory=list)
    swept_ssl: list[LiquidityLevel] = field(default_factory=list)
    inducements: list[LiquidityLevel] = field(default_factory=list)
    nearest_bsl: Optional[LiquidityLevel] = None
    nearest_ssl: Optional[LiquidityLevel] = None
    recent_sweep_kind: Optional[str] = None   # 'bsl' or 'ssl' – most recent sweep


class LiquidityAnalyzer:
    """Detects BSL, SSL, liquidity pools, and sweeps."""

    def __init__(self, settings: dict):
        cfg = settings["liquidity"]
        self.swing_lookback = cfg.get("swing_lookback", 10)
        self.eq_tolerance_pct = cfg.get("equal_level_tolerance_pct", 0.02) / 100
        self.sweep_confirm_pct = cfg.get("sweep_confirmation_pct", 0.1) / 100
        self.bsl_ssl_lookback = cfg.get("bsl_ssl_lookback", 50)
        self.inducement_detection = cfg.get("inducement_detection", True)

    def _find_swing_highs_lows(self, df: pd.DataFrame) -> tuple[list, list]:
        """Identify pivot swing highs and lows."""
        highs, lows = [], []
        n = len(df)
        s = self.swing_lookback

        for i in range(s, n - s):
            h_window = df["high"].iloc[i - s: i + s + 1]
            l_window = df["low"].iloc[i - s: i + s + 1]

            if df["high"].iloc[i] == h_window.max():
                highs.append((i, df.index[i], df["high"].iloc[i]))
            if df["low"].iloc[i] == l_window.min():
                lows.append((i, df.index[i], df["low"].iloc[i]))

        return highs, lows

    def _find_equal_levels(
        self, levels: list[tuple], kind: str
    ) -> list[SwingLiquidityPool]:
        """Group nearby levels into equal high/low pools."""
        pools: list[SwingLiquidityPool] = []
        used = set()

        for i, (idx_i, ts_i, price_i) in enumerate(levels):
            if i in used:
                continue
            group = [j for j, (_, _, p) in enumerate(levels)
                     if abs(p - price_i) / price_i <= self.eq_tolerance_pct]
            if len(group) >= 2:
                for j in group:
                    used.add(j)
                avg_price = np.mean([levels[j][2] for j in group])
                pools.append(SwingLiquidityPool(
                    kind=kind,
                    price=avg_price,
                    touches=len(group),
                    first_timestamp=levels[min(group)][1],
                    last_timestamp=levels[max(group)][1],
                ))

        return pools

    def _check_sweep(
        self,
        level: LiquidityLevel,
        df: pd.DataFrame,
    ) -> LiquidityLevel:
        """Detect if price has swept through this liquidity level and reversed."""
        future = df.iloc[level.index + 1:]

        for ts, row in future.iterrows():
            if level.kind == "bsl":
                # Sweep: wick above the level, close back below
                if row["high"] > level.price * (1 + self.sweep_confirm_pct):
                    if row["close"] < level.price:
                        level.is_swept = True
                        level.sweep_timestamp = ts
                        level.sweep_price = row["high"]
                        break
            else:  # ssl
                if row["low"] < level.price * (1 - self.sweep_confirm_pct):
                    if row["close"] > level.price:
                        level.is_swept = True
                        level.sweep_timestamp = ts
                        level.sweep_price = row["low"]
                        break
        return level

    def _detect_inducements(
        self,
        bsl_levels: list[LiquidityLevel],
        ssl_levels: list[LiquidityLevel],
        df: pd.DataFrame,
    ) -> list[LiquidityLevel]:
        """
        Inducements: smaller liquidity levels between price and the main target.
        A swept level that is followed by a larger unswept level beyond it.
        """
        inducements = []
        all_bsl = sorted(bsl_levels, key=lambda l: l.price)
        all_ssl = sorted(ssl_levels, key=lambda l: l.price, reverse=True)
        current_price = df["close"].iloc[-1]

        # For BSL: swept smaller level below a larger unswept level
        bsl_above = [l for l in all_bsl if l.price > current_price]
        for i in range(len(bsl_above) - 1):
            small = bsl_above[i]
            large = bsl_above[i + 1]
            if small.is_swept and not large.is_swept:
                small.is_inducement = True
                inducements.append(small)

        # For SSL: swept smaller level above a larger unswept level
        ssl_below = [l for l in all_ssl if l.price < current_price]
        for i in range(len(ssl_below) - 1):
            small = ssl_below[i]
            large = ssl_below[i + 1]
            if small.is_swept and not large.is_swept:
                small.is_inducement = True
                inducements.append(small)

        return inducements

    def analyze(self, df: pd.DataFrame) -> LiquidityResult:
        """Run full liquidity analysis."""
        swing_highs, swing_lows = self._find_swing_highs_lows(df)

        # Build BSL from swing highs, SSL from swing lows
        lookback_start = max(0, len(df) - self.bsl_ssl_lookback)
        bsl_levels: list[LiquidityLevel] = []
        ssl_levels: list[LiquidityLevel] = []

        for idx, ts, price in swing_highs:
            if idx < lookback_start:
                continue
            lvl = LiquidityLevel(index=idx, timestamp=ts, price=price, kind="bsl", strength=1)
            lvl = self._check_sweep(lvl, df)
            bsl_levels.append(lvl)

        for idx, ts, price in swing_lows:
            if idx < lookback_start:
                continue
            lvl = LiquidityLevel(index=idx, timestamp=ts, price=price, kind="ssl", strength=1)
            lvl = self._check_sweep(lvl, df)
            ssl_levels.append(lvl)

        # Equal highs / equal lows pools
        eq_high_pools = self._find_equal_levels(swing_highs, "eqh")
        eq_low_pools = self._find_equal_levels(swing_lows, "eql")

        # Boost strength for levels near equal pools
        for pool in eq_high_pools:
            for lvl in bsl_levels:
                if abs(lvl.price - pool.price) / pool.price <= self.eq_tolerance_pct:
                    lvl.strength = pool.touches

        for pool in eq_low_pools:
            for lvl in ssl_levels:
                if abs(lvl.price - pool.price) / pool.price <= self.eq_tolerance_pct:
                    lvl.strength = pool.touches

        swept_bsl = [l for l in bsl_levels if l.is_swept]
        swept_ssl = [l for l in ssl_levels if l.is_swept]

        # Inducements
        inducements = []
        if self.inducement_detection:
            inducements = self._detect_inducements(bsl_levels, ssl_levels, df)

        # Nearest unswept levels
        current_price = df["close"].iloc[-1]
        active_bsl = [l for l in bsl_levels if not l.is_swept and l.price > current_price]
        active_ssl = [l for l in ssl_levels if not l.is_swept and l.price < current_price]

        nearest_bsl = min(active_bsl, key=lambda l: l.price) if active_bsl else None
        nearest_ssl = max(active_ssl, key=lambda l: l.price) if active_ssl else None

        # Most recent sweep
        recent_sweeps = sorted(
            [(l, l.sweep_timestamp) for l in swept_bsl + swept_ssl if l.sweep_timestamp],
            key=lambda x: x[1],
        )
        recent_sweep_kind = recent_sweeps[-1][0].kind if recent_sweeps else None

        return LiquidityResult(
            bsl_levels=bsl_levels,
            ssl_levels=ssl_levels,
            liquidity_pools=eq_high_pools + eq_low_pools,
            swept_bsl=swept_bsl,
            swept_ssl=swept_ssl,
            inducements=inducements,
            nearest_bsl=nearest_bsl,
            nearest_ssl=nearest_ssl,
            recent_sweep_kind=recent_sweep_kind,
        )
