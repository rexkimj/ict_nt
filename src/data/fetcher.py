"""
Market data fetcher using ccxt.
Supports multiple exchanges and timeframes.
"""

import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from typing import Optional
import json
import os


def load_settings() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "../../config/settings.json")
    with open(config_path, "r") as f:
        return json.load(f)


class MarketDataFetcher:
    """Fetches OHLCV data from exchanges via ccxt."""

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or load_settings()
        ex_cfg = self.settings["exchange"]
        exchange_cls = getattr(ccxt, ex_cfg["name"])
        self.exchange = exchange_cls({
            "enableRateLimit": ex_cfg.get("rate_limit", True),
        })
        if ex_cfg.get("testnet", False):
            self.exchange.set_sandbox_mode(True)

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        """Fetch OHLCV candles and return as DataFrame."""
        raw = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)
        df = df.astype(float)
        df["body"] = abs(df["close"] - df["open"])
        df["upper_wick"] = df["high"] - df[["open", "close"]].max(axis=1)
        df["lower_wick"] = df[["open", "close"]].min(axis=1) - df["low"]
        df["range"] = df["high"] - df["low"]
        df["bullish"] = df["close"] > df["open"]
        df["bearish"] = df["close"] < df["open"]
        return df

    def fetch_multi_timeframe(self, symbol: str, limit: int = 300) -> dict[str, pd.DataFrame]:
        """Fetch data for all configured timeframes."""
        tfs = self.settings["market"]["timeframes"]
        result = {}
        for label, tf in tfs.items():
            result[label] = self.fetch_ohlcv(symbol, tf, limit=limit)
        return result

    def get_current_price(self, symbol: str) -> float:
        ticker = self.exchange.fetch_ticker(symbol)
        return float(ticker["last"])

    def get_session_info(self) -> dict:
        """Return which trading session is currently active (UTC)."""
        now_utc = datetime.now(tz=timezone.utc)
        hour = now_utc.hour
        minute = now_utc.minute
        total_min = hour * 60 + minute

        sessions_cfg = self.settings["strategy"]["session_filter"]
        def to_min(t):
            h, m = map(int, t.split(":"))
            return h * 60 + m

        london_open = to_min(sessions_cfg["london_open_utc"])
        london_close = to_min(sessions_cfg["london_close_utc"])
        ny_open = to_min(sessions_cfg["ny_open_utc"])
        ny_close = to_min(sessions_cfg["ny_close_utc"])
        asia_open = to_min("00:00")
        asia_close = to_min("07:00")

        active = []
        if london_open <= total_min < london_close:
            active.append("london")
        if ny_open <= total_min < ny_close:
            active.append("new_york")
        if total_min < asia_close or total_min >= (24 * 60 - 60):
            active.append("asia")

        return {
            "current_utc": now_utc.strftime("%Y-%m-%d %H:%M UTC"),
            "active_sessions": active,
            "is_kill_zone": bool(active),
        }
