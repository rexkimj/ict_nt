"""
히스토리컬 데이터 다운로드 스크립트

Bybit에서 OHLCV 데이터를 다운로드하여 NautilusTrader 백테스팅에 사용할 수 있도록 준비합니다.

사용법:
    pip install ccxt
    python download_data.py

옵션:
    --symbol: 거래 심볼 (기본: BTC/USDT:USDT)
    --timeframe: 타임프레임 (기본: 1h)
    --start-date: 시작 날짜 (기본: 2024-01-01)
    --end-date: 종료 날짜 (기본: today)
"""
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import time

try:
    import ccxt
    import pandas as pd
except ImportError:
    print("Error: ccxt와 pandas가 필요합니다.")
    print("설치: pip install ccxt pandas")
    exit(1)


def download_ohlcv_data(
    symbol: str = 'BTC/USDT:USDT',
    timeframe: str = '1h',
    start_date: str = '2024-01-01',
    end_date: str = None,
    output_dir: str = 'data'
):
    """
    Bybit에서 OHLCV 데이터 다운로드

    Parameters
    ----------
    symbol : str
        거래 심볼
    timeframe : str
        타임프레임 (1m, 5m, 15m, 1h, 4h, 1d 등)
    start_date : str
        시작 날짜 (YYYY-MM-DD)
    end_date : str
        종료 날짜 (YYYY-MM-DD)
    output_dir : str
        출력 디렉토리
    """
    print("=" * 80)
    print("Bybit 히스토리컬 데이터 다운로드")
    print("=" * 80)

    # Bybit 거래소 초기화
    exchange = ccxt.bybit({
        'enableRateLimit': True,
        'options': {
            'defaultType': 'linear',  # USDT perpetual
        }
    })

    print(f"\n설정:")
    print(f"  거래소: Bybit")
    print(f"  심볼: {symbol}")
    print(f"  타임프레임: {timeframe}")
    print(f"  시작 날짜: {start_date}")
    print(f"  종료 날짜: {end_date or 'today'}")

    # 날짜 파싱
    start_ts = exchange.parse8601(f"{start_date}T00:00:00Z")

    if end_date:
        end_ts = exchange.parse8601(f"{end_date}T23:59:59Z")
    else:
        end_ts = exchange.milliseconds()

    print(f"\n데이터 다운로드 중...")

    all_ohlcv = []
    current_ts = start_ts

    # 타임프레임을 밀리초로 변환
    timeframe_ms = {
        '1m': 60 * 1000,
        '5m': 5 * 60 * 1000,
        '15m': 15 * 60 * 1000,
        '1h': 60 * 60 * 1000,
        '4h': 4 * 60 * 60 * 1000,
        '1d': 24 * 60 * 60 * 1000,
    }

    limit = 1000  # Bybit의 최대 limit

    while current_ts < end_ts:
        try:
            # OHLCV 데이터 요청
            ohlcv = exchange.fetch_ohlcv(
                symbol,
                timeframe,
                since=current_ts,
                limit=limit
            )

            if not ohlcv:
                break

            all_ohlcv.extend(ohlcv)

            # 다음 요청의 시작 시간
            last_ts = ohlcv[-1][0]
            current_ts = last_ts + timeframe_ms.get(timeframe, 60 * 60 * 1000)

            # 진행 상황 출력
            last_date = datetime.fromtimestamp(last_ts / 1000)
            print(f"  다운로드 중: {last_date} ({len(all_ohlcv)} 캔들)")

            # Rate limit 준수
            time.sleep(exchange.rateLimit / 1000)

            # 종료 날짜를 넘으면 중단
            if current_ts > end_ts:
                break

        except Exception as e:
            print(f"Error: {e}")
            print("잠시 후 재시도...")
            time.sleep(5)
            continue

    print(f"\n총 {len(all_ohlcv)} 개의 캔들 다운로드 완료!")

    # DataFrame 생성
    df = pd.DataFrame(
        all_ohlcv,
        columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
    )

    # 타임스탬프를 datetime으로 변환
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

    # 중복 제거
    df = df.drop_duplicates(subset=['timestamp'])
    df = df.sort_values('timestamp')

    # 출력 디렉토리 생성
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    # CSV 저장
    filename = f"{symbol.replace('/', '').replace(':', '_')}_{timeframe}.csv"
    filepath = output_path / filename

    df.to_csv(filepath, index=False)

    print(f"\n저장 완료: {filepath}")
    print(f"  데이터 기간: {df['timestamp'].min()} ~ {df['timestamp'].max()}")
    print(f"  총 캔들 수: {len(df)}")

    # 데이터 미리보기
    print("\n데이터 미리보기:")
    print(df.head())
    print("...")
    print(df.tail())

    return df


def download_multiple_timeframes(
    symbol: str = 'BTC/USDT:USDT',
    timeframes: list = ['5m', '1h'],
    start_date: str = '2024-01-01',
    end_date: str = None
):
    """
    여러 타임프레임의 데이터를 한번에 다운로드

    Parameters
    ----------
    symbol : str
        거래 심볼
    timeframes : list
        타임프레임 리스트
    start_date : str
        시작 날짜
    end_date : str
        종료 날짜
    """
    print("=" * 80)
    print(f"다중 타임프레임 데이터 다운로드: {timeframes}")
    print("=" * 80)

    for tf in timeframes:
        print(f"\n[{tf}] 다운로드 시작...")
        download_ohlcv_data(
            symbol=symbol,
            timeframe=tf,
            start_date=start_date,
            end_date=end_date
        )
        print(f"[{tf}] 완료!")
        time.sleep(2)  # Rate limit

    print("\n" + "=" * 80)
    print("모든 타임프레임 다운로드 완료!")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Bybit 히스토리컬 데이터 다운로드')

    parser.add_argument(
        '--symbol',
        type=str,
        default='BTC/USDT:USDT',
        help='거래 심볼 (기본: BTC/USDT:USDT)'
    )
    parser.add_argument(
        '--timeframe',
        type=str,
        default='1h',
        help='타임프레임 (기본: 1h)'
    )
    parser.add_argument(
        '--start-date',
        type=str,
        default='2024-01-01',
        help='시작 날짜 YYYY-MM-DD (기본: 2024-01-01)'
    )
    parser.add_argument(
        '--end-date',
        type=str,
        default=None,
        help='종료 날짜 YYYY-MM-DD (기본: today)'
    )
    parser.add_argument(
        '--multi',
        action='store_true',
        help='다중 타임프레임 다운로드 (5m, 1h)'
    )

    args = parser.parse_args()

    try:
        if args.multi:
            # 다중 타임프레임
            download_multiple_timeframes(
                symbol=args.symbol,
                timeframes=['5m', '1h'],
                start_date=args.start_date,
                end_date=args.end_date
            )
        else:
            # 단일 타임프레임
            download_ohlcv_data(
                symbol=args.symbol,
                timeframe=args.timeframe,
                start_date=args.start_date,
                end_date=args.end_date
            )

        print("\n✅ 성공!")
        print("\n다음 단계:")
        print("  1. data/ 폴더에 CSV 파일이 저장되었습니다")
        print("  2. 백테스트 스크립트를 수정하여 이 데이터를 로드하세요")
        print("  3. 자세한 내용은 backtest.py의 가이드를 참고하세요")

    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()

        print("\n문제 해결:")
        print("  1. ccxt 설치: pip install ccxt")
        print("  2. 인터넷 연결 확인")
        print("  3. Bybit API 상태 확인")
