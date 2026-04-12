"""
ICT Strategy Live Trading Script

Bybit 거래소에서 실시간 트레이딩

사용법:
    1. .env 파일 생성 및 API 키 설정
    2. python live_trade.py

주의사항:
    - 반드시 테스트넷에서 먼저 테스트하세요
    - 리스크 관리 설정을 확인하세요
    - API 키를 안전하게 보관하세요
"""
import json
import os
from pathlib import Path
from dotenv import load_dotenv

from nautilus_trader.live.node import TradingNode
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.adapters.bybit.config import BybitDataClientConfig
from nautilus_trader.adapters.bybit.config import BybitExecClientConfig
from nautilus_trader.adapters.bybit.factories import BybitLiveDataClientFactory
from nautilus_trader.adapters.bybit.factories import BybitLiveExecClientFactory
from nautilus_trader.model.identifiers import TraderId

from strategies.ict_strategy import ICTStrategy


def load_config(config_path: str) -> dict:
    """설정 파일 로드"""
    with open(config_path, 'r') as f:
        return json.load(f)


def setup_live_trading():
    """라이브 트레이딩 설정 및 실행"""
    print("=" * 80)
    print("ICT Trading Strategy - Live Trading")
    print("=" * 80)

    # 환경 변수 로드
    load_dotenv()

    # API 키 확인
    api_key = os.getenv('BYBIT_API_KEY')
    api_secret = os.getenv('BYBIT_API_SECRET')
    use_testnet = os.getenv('BYBIT_TESTNET', 'true').lower() == 'true'

    if not api_key or not api_secret:
        print("\nERROR: Bybit API credentials not found!")
        print("Please create a .env file with:")
        print("  BYBIT_API_KEY=your_key")
        print("  BYBIT_API_SECRET=your_secret")
        print("  BYBIT_TESTNET=true")
        return

    # 설정 로드
    strategy_config = load_config('config/strategy_config.json')

    print(f"\n{'TESTNET' if use_testnet else 'MAINNET'} Mode")
    print(f"Instrument: {strategy_config['instrument_id']}")
    print(f"HTF: {strategy_config['htf_bar_type']}")
    print(f"LTF: {strategy_config['ltf_bar_type']}")
    print(f"Risk per Trade: {strategy_config['risk_management']['risk_per_trade_pct']}%")
    print(f"Min RR Ratio: {strategy_config['risk_management']['min_rr_ratio']}:1")
    print(f"Leverage: {strategy_config['risk_management']['leverage']}x")

    # 안전 확인
    if not use_testnet:
        print("\n" + "!" * 80)
        print("WARNING: You are about to trade on MAINNET with REAL MONEY!")
        print("!" * 80)
        response = input("\nType 'YES' to continue: ")
        if response != 'YES':
            print("Aborted.")
            return

    print("\n" + "=" * 80)
    print("Initializing Trading Node...")
    print("=" * 80)

    # Bybit 데이터 클라이언트 설정
    data_config = BybitDataClientConfig(
        api_key=api_key,
        api_secret=api_secret,
        testnet=use_testnet,
        base_url_http="https://api-testnet.bybit.com" if use_testnet else "https://api.bybit.com",
    )

    # Bybit 실행 클라이언트 설정
    exec_config = BybitExecClientConfig(
        api_key=api_key,
        api_secret=api_secret,
        testnet=use_testnet,
        base_url_http="https://api-testnet.bybit.com" if use_testnet else "https://api.bybit.com",
    )

    # 트레이딩 노드 설정
    node_config = TradingNodeConfig(
        trader_id=TraderId("TRADER-001"),
        log_level="INFO",
        cache_database_path=str(Path.cwd() / "cache"),
        data_clients={
            "BYBIT": data_config,
        },
        exec_clients={
            "BYBIT": exec_config,
        },
    )

    # 트레이딩 노드 생성
    node = TradingNode(config=node_config)

    # 전략 설정
    strategy_cfg = {
        'instrument_id': strategy_config['instrument_id'],
        'htf_bar_type': strategy_config['htf_bar_type'],
        'ltf_bar_type': strategy_config['ltf_bar_type'],
        'risk_per_trade_pct': strategy_config['risk_management']['risk_per_trade_pct'],
        'min_rr_ratio': strategy_config['risk_management']['min_rr_ratio'],
        'leverage': strategy_config['risk_management']['leverage'],
        'order_block_params': strategy_config['order_block_params'],
        'fvg_params': strategy_config['fvg_params'],
        'liquidity_params': strategy_config['liquidity_params'],
        'market_structure_params': strategy_config['market_structure_params'],
    }

    # 전략 추가
    node.add_strategy(ICTStrategy, strategy_cfg)

    print("\nStarting Live Trading...")
    print("=" * 80)
    print("Press Ctrl+C to stop")
    print("=" * 80)

    try:
        # 노드 시작
        node.start()

        # 실행 유지
        input("\nPress Enter to stop trading...\n")

    except KeyboardInterrupt:
        print("\n\nReceived stop signal...")

    finally:
        print("\nStopping Trading Node...")
        node.stop()

        print("\nFinal Account State:")
        # 최종 계좌 상태 출력
        for venue in node.trader.portfolio.accounts():
            account = node.trader.portfolio.account(venue)
            print(f"  Balance: ${account.balance_total().as_double():.2f}")

        print("\n" + "=" * 80)
        print("Trading Stopped")
        print("=" * 80)


def dry_run_validation():
    """실행 전 설정 검증"""
    print("\n" + "=" * 80)
    print("Configuration Validation")
    print("=" * 80)

    # 환경 변수 확인
    load_dotenv()
    api_key = os.getenv('BYBIT_API_KEY')
    api_secret = os.getenv('BYBIT_API_SECRET')

    checks = {
        'API Key exists': bool(api_key),
        'API Secret exists': bool(api_secret),
        'Strategy config exists': Path('config/strategy_config.json').exists(),
        'Bybit config exists': Path('config/bybit_config.json').exists(),
    }

    all_passed = True
    for check, passed in checks.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {check}: {status}")
        if not passed:
            all_passed = False

    print("=" * 80)

    if all_passed:
        print("\n✓ All checks passed! Ready to trade.\n")
        return True
    else:
        print("\n✗ Some checks failed. Please fix the issues above.\n")
        return False


if __name__ == "__main__":
    print("""
    ██╗ ██████╗████████╗    ████████╗██████╗  █████╗ ██████╗ ██╗███╗   ██╗ ██████╗
    ██║██╔════╝╚══██╔══╝    ╚══██╔══╝██╔══██╗██╔══██╗██╔══██╗██║████╗  ██║██╔════╝
    ██║██║        ██║          ██║   ██████╔╝███████║██║  ██║██║██╔██╗ ██║██║  ███╗
    ██║██║        ██║          ██║   ██╔══██╗██╔══██║██║  ██║██║██║╚██╗██║██║   ██║
    ██║╚██████╗   ██║          ██║   ██║  ██║██║  ██║██████╔╝██║██║ ╚████║╚██████╔╝
    ╚═╝ ╚═════╝   ╚═╝          ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ ╚═╝╚═╝  ╚═══╝ ╚═════╝

    Inner Circle Trader Strategy - Powered by NautilusTrader
    """)

    # 설정 검증
    if not dry_run_validation():
        exit(1)

    # 라이브 트레이딩 시작
    try:
        setup_live_trading()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
