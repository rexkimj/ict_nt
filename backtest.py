"""
ICT Strategy Backtesting Script (완전 자동화 버전)

데이터 다운로드부터 백테스트까지 원클릭으로 실행

사용법:
    python backtest.py
"""
import json
from pathlib import Path
from datetime import datetime
from decimal import Decimal
import time

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import AccountType, OmsType, AssetClass, BarAggregation
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.model.instruments import CryptoFuture
from nautilus_trader.model.data import BarType, Bar, BarSpecification
from nautilus_trader.core.datetime import unix_nanos_to_dt

import numpy as np
import pandas as pd

try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False

from strategies.ict_strategy import ICTStrategy


def load_config(config_path: str) -> dict:
    """설정 파일 로드"""
    with open(config_path, 'r') as f:
        return json.load(f)


def download_bybit_data(
    symbol: str = 'BTC/USDT:USDT',
    timeframe: str = '1h',
    start_date: str = '2024-01-01',
    days: int = 90
):
    """
    Bybit에서 데이터 다운로드

    Parameters
    ----------
    symbol : str
        거래 심볼
    timeframe : str
        타임프레임
    start_date : str
        시작 날짜
    days : int
        다운로드할 일수

    Returns
    -------
    pd.DataFrame
        OHLCV 데이터
    """
    if not CCXT_AVAILABLE:
        print("⚠️  ccxt가 설치되지 않았습니다.")
        print("설치: pip install ccxt")
        return create_sample_data(days * 24 if timeframe == '1h' else days * 288)

    print(f"\n📥 Bybit에서 {symbol} {timeframe} 데이터 다운로드 중...")

    exchange = ccxt.bybit({
        'enableRateLimit': True,
        'options': {'defaultType': 'linear'}
    })

    start_ts = exchange.parse8601(f"{start_date}T00:00:00Z")
    all_ohlcv = []

    timeframe_ms = {
        '1m': 60 * 1000,
        '5m': 5 * 60 * 1000,
        '1h': 60 * 60 * 1000,
    }

    target_bars = days * 24 if timeframe == '1h' else days * 288
    current_ts = start_ts

    try:
        while len(all_ohlcv) < target_bars:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=current_ts, limit=1000)

            if not ohlcv:
                break

            all_ohlcv.extend(ohlcv)
            last_ts = ohlcv[-1][0]
            current_ts = last_ts + timeframe_ms.get(timeframe, 60 * 60 * 1000)

            print(f"  {len(all_ohlcv)} 캔들 다운로드됨...", end='\r')
            time.sleep(0.1)

            if len(all_ohlcv) >= target_bars:
                break

        print(f"\n✅ {len(all_ohlcv)} 캔들 다운로드 완료!")

        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.drop_duplicates(subset=['timestamp']).sort_values('timestamp')

        return df

    except Exception as e:
        print(f"⚠️  다운로드 실패: {e}")
        print("샘플 데이터로 대체합니다...")
        return create_sample_data(target_bars)


def create_sample_data(n_bars: int = 2000):
    """
    샘플 데이터 생성 (랜덤 워크)

    Parameters
    ----------
    n_bars : int
        생성할 캔들 수

    Returns
    -------
    pd.DataFrame
        샘플 OHLCV 데이터
    """
    print(f"\n📊 샘플 데이터 생성 중 ({n_bars} 캔들)...")

    start_price = 50000.0
    dates = pd.date_range(start='2024-01-01', periods=n_bars, freq='h')

    # OHLC 데이터 생성
    opens = []
    highs = []
    lows = []
    closes = []
    volumes = []

    current_price = start_price

    for _ in range(n_bars):
        # Open
        open_price = current_price

        # Close (랜덤 워크)
        change = np.random.randn() * 200
        close_price = max(open_price + change, 10000)

        # High: open과 close 중 큰 값 + 약간의 위크
        max_oc = max(open_price, close_price)
        high_wick = abs(np.random.randn()) * max_oc * 0.005  # 0.5%
        high_price = max_oc + high_wick

        # Low: open과 close 중 작은 값 - 약간의 위크
        min_oc = min(open_price, close_price)
        low_wick = abs(np.random.randn()) * min_oc * 0.005  # 0.5%
        low_price = max(min_oc - low_wick, 1000)  # 최소가 보장

        opens.append(open_price)
        highs.append(high_price)
        lows.append(low_price)
        closes.append(close_price)
        volumes.append(np.random.randint(100, 1000))

        current_price = close_price

    data = {
        'timestamp': dates,
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes,
    }

    df = pd.DataFrame(data)
    print("✅ 샘플 데이터 생성 완료!")
    return df


def create_test_instrument():
    """테스트용 BTC/USDT 선물 인스트루먼트 생성"""
    from nautilus_trader.test_kit.providers import TestInstrumentProvider

    # TestInstrumentProvider의 기본 인스트루먼트 사용
    # venue는 BINANCE이지만 테스트 목적으로는 충분함
    return TestInstrumentProvider.btcusdt_perp_binance()


def df_to_bars(df: pd.DataFrame, instrument_id: InstrumentId, bar_type: BarType) -> list:
    """
    DataFrame을 NautilusTrader Bar 객체 리스트로 변환

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV 데이터
    instrument_id : InstrumentId
        인스트루먼트 ID
    bar_type : BarType
        바 타입

    Returns
    -------
    list[Bar]
        Bar 객체 리스트
    """
    bars = []

    for _, row in df.iterrows():
        ts_event = int(row['timestamp'].timestamp() * 1_000_000_000)  # 나노초
        ts_init = ts_event

        bar = Bar(
            bar_type=bar_type,
            open=Price.from_str(f"{row['open']:.1f}"),
            high=Price.from_str(f"{row['high']:.1f}"),
            low=Price.from_str(f"{row['low']:.1f}"),
            close=Price.from_str(f"{row['close']:.1f}"),
            volume=Quantity.from_str(f"{row['volume']:.3f}"),
            ts_event=ts_event,
            ts_init=ts_init,
        )
        bars.append(bar)

    return bars


def run_backtest():
    """백테스트 실행"""
    print("=" * 80)
    print("ICT Trading Strategy Backtest")
    print("=" * 80)

    # 설정 로드
    try:
        strategy_config = load_config('config/strategy_config.json')
    except FileNotFoundError:
        print("❌ config/strategy_config.json을 찾을 수 없습니다.")
        return

    print(f"\n⚙️  전략 설정:")
    print(f"  Risk per Trade: {strategy_config['risk_management']['risk_per_trade_pct']}%")
    print(f"  Min RR Ratio: {strategy_config['risk_management']['min_rr_ratio']}:1")
    print(f"  Leverage: {strategy_config['risk_management']['leverage']}x")

    # 데이터 다운로드
    print("\n" + "=" * 80)
    print("1단계: 히스토리컬 데이터 준비")
    print("=" * 80)

    # 1시간봉 데이터 (HTF)
    htf_df = download_bybit_data(
        symbol='BTC/USDT:USDT',
        timeframe='1h',
        start_date='2024-01-01',
        days=90
    )

    # 5분봉 데이터 (LTF)
    ltf_df = download_bybit_data(
        symbol='BTC/USDT:USDT',
        timeframe='5m',
        start_date='2024-01-01',
        days=90
    )

    print(f"\nHTF (1시간봉): {len(htf_df)} 캔들")
    print(f"  기간: {htf_df['timestamp'].min()} ~ {htf_df['timestamp'].max()}")
    print(f"LTF (5분봉): {len(ltf_df)} 캔들")
    print(f"  기간: {ltf_df['timestamp'].min()} ~ {ltf_df['timestamp'].max()}")

    # 백테스트 엔진 초기화
    print("\n" + "=" * 80)
    print("2단계: 백테스트 엔진 초기화")
    print("=" * 80)

    config = BacktestEngineConfig(trader_id="BACKTESTER-001")
    engine = BacktestEngine(config=config)

    # Venue 추가 (테스트용 BINANCE venue 사용)
    venue = Venue("BINANCE")
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        base_currency=USDT,
        starting_balances=[Money(10000, USDT)],
    )

    # 인스트루먼트 생성 및 추가
    instrument = create_test_instrument()
    engine.add_instrument(instrument)

    print(f"✅ Venue 추가: {venue}")
    print(f"✅ 인스트루먼트 추가: {instrument.id}")
    print(f"✅ 초기 잔고: $10,000 USDT")

    # 바 데이터 생성 및 추가
    print("\n" + "=" * 80)
    print("3단계: 바 데이터 추가")
    print("=" * 80)

    # HTF 바 타입
    htf_bar_type = BarType(
        instrument_id=instrument.id,
        bar_spec=BarSpecification(
            step=1,
            aggregation=BarAggregation.HOUR,
            price_type=4,  # LAST
        ),
        aggregation_source=1,  # INTERNAL (백테스트용)
    )

    # LTF 바 타입
    ltf_bar_type = BarType(
        instrument_id=instrument.id,
        bar_spec=BarSpecification(
            step=5,
            aggregation=BarAggregation.MINUTE,
            price_type=4,  # LAST
        ),
        aggregation_source=1,  # INTERNAL (백테스트용)
    )

    # DataFrame을 Bar 객체로 변환
    htf_bars = df_to_bars(htf_df, instrument.id, htf_bar_type)
    ltf_bars = df_to_bars(ltf_df, instrument.id, ltf_bar_type)

    # 엔진에 추가
    engine.add_data(htf_bars)
    engine.add_data(ltf_bars)

    print(f"✅ HTF 바 추가: {len(htf_bars)} 개")
    print(f"✅ LTF 바 추가: {len(ltf_bars)} 개")

    # 전략 추가
    print("\n" + "=" * 80)
    print("4단계: 전략 추가")
    print("=" * 80)

    strategy_cfg = {
        'instrument_id': str(instrument.id),
        'htf_bar_type': str(htf_bar_type),
        'ltf_bar_type': str(ltf_bar_type),
        'risk_per_trade_pct': strategy_config['risk_management']['risk_per_trade_pct'],
        'min_rr_ratio': strategy_config['risk_management']['min_rr_ratio'],
        'leverage': strategy_config['risk_management']['leverage'],
        'order_block_params': strategy_config['order_block_params'],
        'fvg_params': strategy_config['fvg_params'],
        'liquidity_params': strategy_config['liquidity_params'],
        'market_structure_params': strategy_config['market_structure_params'],
    }

    engine.add_strategy(ICTStrategy(config=strategy_cfg))
    print("✅ ICT 전략 추가 완료")

    # 백테스트 실행
    print("\n" + "=" * 80)
    print("5단계: 백테스트 실행")
    print("=" * 80)
    print("실행 중...\n")

    engine.run()

    print("\n" + "=" * 80)
    print("6단계: 결과 분석")
    print("=" * 80)

    # 계좌 통계
    account = engine.trader.generate_account_report(venue)
    print(f"\n💰 계좌 결과:")
    print(f"  시작 잔고: $10,000.00")

    final_balance = 10000.0  # 기본값
    try:
        # 최종 잔고 가져오기
        portfolio_account = list(engine.trader.portfolio.accounts())[0]
        final_balance = portfolio_account.balance_total().as_double()
        pnl = final_balance - 10000.0
        return_pct = (pnl / 10000.0) * 100

        print(f"  최종 잔고: ${final_balance:.2f}")
        print(f"  총 PnL: ${pnl:+.2f}")
        print(f"  수익률: {return_pct:+.2f}%")
    except Exception as e:
        print(f"  (잔고 정보를 가져올 수 없습니다)")

    # 거래 통계
    print(f"\n📊 거래 통계:")

    try:
        positions = engine.trader.generate_positions_report()
        fills = engine.trader.generate_order_fills_report()

        print(f"  총 주문 체결: {len(fills)} 건")
        print(f"  총 포지션: {len(positions)} 개")

        if positions:
            winning = [p for p in positions if p.realized_pnl.as_double() > 0]
            losing = [p for p in positions if p.realized_pnl.as_double() < 0]

            print(f"  승리 거래: {len(winning)} 건")
            print(f"  패배 거래: {len(losing)} 건")

            if positions:
                win_rate = (len(winning) / len(positions)) * 100
                print(f"  승률: {win_rate:.1f}%")

            if winning:
                avg_win = sum(p.realized_pnl.as_double() for p in winning) / len(winning)
                print(f"  평균 수익: ${avg_win:.2f}")

            if losing:
                avg_loss = sum(p.realized_pnl.as_double() for p in losing) / len(losing)
                print(f"  평균 손실: ${avg_loss:.2f}")

            total_wins = sum(p.realized_pnl.as_double() for p in winning)
            total_losses = abs(sum(p.realized_pnl.as_double() for p in losing))

            if total_losses > 0:
                profit_factor = total_wins / total_losses
                print(f"  Profit Factor: {profit_factor:.2f}")
        else:
            print("  (거래 없음)")

    except Exception as e:
        print(f"  (통계 생성 실패: {e})")

    print("\n" + "=" * 80)
    print("백테스트 완료!")
    print("=" * 80)


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
        run_backtest()

        print("\n💡 팁:")
        print("  - ccxt 설치하면 실제 Bybit 데이터 사용: pip install ccxt")
        print("  - 전략 파라미터 조정: config/strategy_config.json")
        print("  - 라이브 트레이딩: python live_trade.py")

    except KeyboardInterrupt:
        print("\n\n중단됨")
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
