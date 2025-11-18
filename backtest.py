"""
ICT Strategy Backtesting Script

NautilusTrader를 사용한 백테스팅

사용법:
    python backtest.py
"""
import json
from pathlib import Path
from datetime import datetime, timedelta

from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.config import BacktestDataConfig, BacktestEngineConfig
from nautilus_trader.config import BacktestRunConfig, BacktestVenueConfig
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.test_kit.providers import TestInstrumentProvider

from strategies.ict_strategy import ICTStrategy


def load_config(config_path: str) -> dict:
    """설정 파일 로드"""
    with open(config_path, 'r') as f:
        return json.load(f)


def run_backtest():
    """백테스팅 실행"""
    print("=" * 80)
    print("ICT Trading Strategy Backtest")
    print("=" * 80)

    # 설정 로드
    strategy_config = load_config('config/strategy_config.json')

    # 백테스트 기간 설정
    start_date = datetime(2024, 1, 1)
    end_date = datetime(2024, 6, 30)

    print(f"\nBacktest Period: {start_date} to {end_date}")
    print(f"Instrument: {strategy_config['instrument_id']}")
    print(f"HTF: {strategy_config['htf_bar_type']}")
    print(f"LTF: {strategy_config['ltf_bar_type']}")
    print(f"Risk per Trade: {strategy_config['risk_management']['risk_per_trade_pct']}%")
    print(f"Min RR Ratio: {strategy_config['risk_management']['min_rr_ratio']}:1")
    print(f"Leverage: {strategy_config['risk_management']['leverage']}x")

    # Venue 설정
    venue = Venue("BYBIT")

    # 백테스트 엔진 설정
    backtest_config = BacktestEngineConfig(
        trader_id="BACKTESTER-001",
        log_level="INFO",
    )

    # 데이터 설정
    data_config = BacktestDataConfig(
        catalog_path=str(Path.cwd() / "catalog"),
        data_cls="nautilus_trader.model.data.Bar",
        instrument_id=strategy_config['instrument_id'],
        start=start_date,
        end=end_date,
    )

    # Venue 설정
    venue_config = BacktestVenueConfig(
        name="BYBIT",
        venue_type="exchange",
        oms_type="NETTING",
        account_type="MARGIN",
        starting_balances=["10000 USDT"],
        base_currency="USDT",
        default_leverage=strategy_config['risk_management']['leverage'],
    )

    # 백테스트 실행 설정
    run_config = BacktestRunConfig(
        engine=backtest_config,
        venues=[venue_config],
        data=[data_config],
    )

    print("\n" + "=" * 80)
    print("Initializing Backtest Engine...")
    print("=" * 80)

    # 백테스트 노드 생성
    node = BacktestNode(configs=[run_config])

    # 전략 추가
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

    node.add_strategy(ICTStrategy, strategy_cfg)

    print("\nRunning Backtest...")
    print("=" * 80)

    # 백테스트 실행
    node.run()

    print("\n" + "=" * 80)
    print("Backtest Complete!")
    print("=" * 80)

    # 결과 출력
    engine = node.engine

    # 계좌 통계
    account = engine.portfolio.account(venue)
    print(f"\nAccount Statistics:")
    print(f"  Starting Balance: ${10000:.2f}")
    print(f"  Ending Balance: ${account.balance_total().as_double():.2f}")
    print(f"  Total PnL: ${account.balance_total().as_double() - 10000:.2f}")
    print(f"  Return: {((account.balance_total().as_double() / 10000) - 1) * 100:.2f}%")

    # 거래 통계
    if engine.trader.generate_order_fills_report():
        fills = engine.trader.generate_order_fills_report()
        print(f"\nTrade Statistics:")
        print(f"  Total Trades: {len(fills)}")

    # 포지션 통계
    if engine.trader.generate_positions_report():
        positions = engine.trader.generate_positions_report()
        print(f"  Total Positions: {len(positions)}")

        winning_trades = [p for p in positions if p.realized_pnl.as_double() > 0]
        losing_trades = [p for p in positions if p.realized_pnl.as_double() < 0]

        if positions:
            print(f"  Winning Trades: {len(winning_trades)}")
            print(f"  Losing Trades: {len(losing_trades)}")
            print(f"  Win Rate: {len(winning_trades) / len(positions) * 100:.2f}%")

            total_wins = sum(p.realized_pnl.as_double() for p in winning_trades)
            total_losses = sum(p.realized_pnl.as_double() for p in losing_trades)

            if winning_trades:
                print(f"  Avg Win: ${total_wins / len(winning_trades):.2f}")
            if losing_trades:
                print(f"  Avg Loss: ${total_losses / len(losing_trades):.2f}")

            if total_losses != 0:
                profit_factor = abs(total_wins / total_losses)
                print(f"  Profit Factor: {profit_factor:.2f}")

    print("\n" + "=" * 80)
    print("Backtest Results saved to: results/")
    print("=" * 80)


if __name__ == "__main__":
    try:
        run_backtest()
    except Exception as e:
        print(f"\nError during backtest: {e}")
        import traceback
        traceback.print_exc()
