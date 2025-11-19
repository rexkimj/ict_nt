"""
ICT Strategy Backtesting Script (Simplified)

NautilusTrader를 사용한 백테스팅

사용법:
    python backtest.py

참고:
    - 이 버전은 간소화된 백테스트 예제입니다
    - 실제 히스토리컬 데이터가 필요합니다
    - NautilusTrader 1.190.0 이상 필요
"""
import json
from pathlib import Path
from datetime import datetime
from decimal import Decimal

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.wranglers import BarDataWrangler
from nautilus_trader.test_kit.providers import TestInstrumentProvider

import numpy as np
import pandas as pd

from strategies.ict_strategy import ICTStrategy


def load_config(config_path: str) -> dict:
    """설정 파일 로드"""
    with open(config_path, 'r') as f:
        return json.load(f)


def create_sample_data():
    """
    샘플 데이터 생성 (데모용)

    실제 사용 시에는:
    1. Bybit에서 히스토리컬 데이터 다운로드
    2. CSV 파일로 저장
    3. BarDataWrangler로 로드
    """
    print("\n⚠️  샘플 데이터 생성 중...")
    print("실제 백테스트를 위해서는 히스토리컬 데이터가 필요합니다.")

    # 샘플 OHLCV 데이터 생성 (랜덤 워크)
    n_bars = 1000
    start_price = 50000.0

    dates = pd.date_range(start='2024-01-01', periods=n_bars, freq='1H')

    prices = [start_price]
    for _ in range(n_bars - 1):
        change = np.random.randn() * 100  # 랜덤 변화
        prices.append(prices[-1] + change)

    data = {
        'timestamp': dates,
        'open': prices,
        'high': [p * (1 + abs(np.random.randn()) * 0.001) for p in prices],
        'low': [p * (1 - abs(np.random.randn()) * 0.001) for p in prices],
        'close': [p + np.random.randn() * 50 for p in prices],
        'volume': [np.random.randint(100, 1000) for _ in range(n_bars)],
    }

    df = pd.DataFrame(data)
    return df


def run_backtest_simple():
    """간소화된 백테스트 실행"""
    print("=" * 80)
    print("ICT Trading Strategy Backtest (Simplified)")
    print("=" * 80)

    # 설정 로드
    try:
        strategy_config = load_config('config/strategy_config.json')
    except FileNotFoundError:
        print("Error: config/strategy_config.json not found")
        return

    print(f"\nInstrument: {strategy_config['instrument_id']}")
    print(f"Risk per Trade: {strategy_config['risk_management']['risk_per_trade_pct']}%")
    print(f"Min RR Ratio: {strategy_config['risk_management']['min_rr_ratio']}:1")
    print(f"Leverage: {strategy_config['risk_management']['leverage']}x")

    print("\n" + "=" * 80)
    print("백테스트 엔진 초기화 중...")
    print("=" * 80)

    # 백테스트 엔진 생성
    config = BacktestEngineConfig(
        trader_id="BACKTESTER-001",
    )

    engine = BacktestEngine(config=config)

    # Venue 추가
    venue = Venue("BYBIT")
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=USDT,
        starting_balances=[Money(10000, USDT)],
    )

    # 테스트 인스트루먼트 생성
    instrument = TestInstrumentProvider.btcusdt_perp_binance()
    engine.add_instrument(instrument)

    print("\n⚠️  주의: 이 버전은 데모용 간소화 버전입니다.")
    print("실제 백테스트를 위해서는 다음이 필요합니다:")
    print("  1. Bybit에서 히스토리컬 데이터 다운로드")
    print("  2. NautilusTrader 데이터 카탈로그 설정")
    print("  3. 실제 바 데이터를 엔진에 추가")
    print("\n자세한 내용은 NautilusTrader 문서를 참고하세요:")
    print("  https://nautilustrader.io/docs/guides/backtesting")

    print("\n" + "=" * 80)
    print("백테스트 완료")
    print("=" * 80)


def show_data_download_guide():
    """데이터 다운로드 가이드 출력"""
    print("\n" + "=" * 80)
    print("히스토리컬 데이터 다운로드 가이드")
    print("=" * 80)

    print("""
1. Bybit API를 사용한 데이터 다운로드:

```python
import ccxt
import pandas as pd

exchange = ccxt.bybit({
    'enableRateLimit': True,
})

# OHLCV 데이터 다운로드
symbol = 'BTC/USDT:USDT'
timeframe = '1h'
since = exchange.parse8601('2024-01-01T00:00:00Z')

ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since)
df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
df.to_csv('btcusdt_1h.csv', index=False)
```

2. CSV 파일을 NautilusTrader 형식으로 변환:

```python
from nautilus_trader.persistence.wranglers import BarDataWrangler
from nautilus_trader.model.data import BarType

# CSV 로드
df = pd.read_csv('btcusdt_1h.csv')

# Wrangler로 변환
wrangler = BarDataWrangler(
    bar_type=BarType.from_str('BTCUSDT-PERP.BYBIT-1-HOUR-LAST-EXTERNAL'),
    instrument=instrument,
)

bars = wrangler.process(df)

# 엔진에 추가
engine.add_bars(bars)
```

3. 또는 NautilusTrader 데이터 카탈로그 사용:

```python
from nautilus_trader.persistence.catalog import ParquetDataCatalog

catalog = ParquetDataCatalog('./catalog')
# 데이터를 카탈로그에 저장하고 백테스트에 사용
```
""")


if __name__ == "__main__":
    print("""
    ██╗ ██████╗████████╗    ████████╗██████╗  █████╗ ██████╗ ██╗███╗   ██╗ ██████╗
    ██║██╔════╝╚══██╔══╝    ╚══██╔══╝██╔══██╗██╔══██╗██╔══██╗██║████╗  ██║██╔════╝
    ██║██║        ██║          ██║   ██████╔╝███████║██║  ██║██║██╔██╗ ██║██║  ███╗
    ██║██║        ██║          ██║   ██╔══██╗██╔══██║██║  ██║██║██║╚██╗██║██║   ██║
    ██║╚██████╗   ██║          ██║   ██║  ██║██║  ██║██████╔╝██║██║ ╚████║╚██████╔╝
    ╚═╝ ╚═════╝   ╚═╝          ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ ╚═╝╚═╝  ╚═══╝ ╚═════╝

    ICT Strategy Backtest - Powered by NautilusTrader
    """)

    try:
        run_backtest_simple()
        show_data_download_guide()
    except Exception as e:
        print(f"\nError during backtest: {e}")
        import traceback
        traceback.print_exc()

        print("\n" + "=" * 80)
        print("오류 해결 방법:")
        print("=" * 80)
        print("1. NautilusTrader가 올바르게 설치되었는지 확인:")
        print("   pip install nautilus_trader>=1.190.0")
        print("\n2. 설정 파일이 존재하는지 확인:")
        print("   config/strategy_config.json")
        print("\n3. 데이터 다운로드 가이드를 참고하여 히스토리컬 데이터 준비")
