"""
ICT Market Analysis Tool — Main Entry Point.

Usage:
    python main.py                         # Analyze default symbol
    python main.py --symbol ETH/USDT       # Specify symbol
    python main.py --symbol BTC/USDT --watch   # Live watch mode
    python main.py --list-symbols          # Show configured symbols
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich.rule import Rule
from rich import box

from src.data.fetcher import MarketDataFetcher
from src.strategy.ict_strategy import ICTStrategy, MarketAnalysisSnapshot

console = Console()


def load_settings() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "config/settings.json")
    with open(config_path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def trend_badge(trend: str) -> Text:
    colors = {"bullish": "bold green", "bearish": "bold red", "ranging": "bold yellow"}
    symbols = {"bullish": "▲ BULLISH", "bearish": "▼ BEARISH", "ranging": "◆ RANGING"}
    return Text(symbols.get(trend, trend.upper()), style=colors.get(trend, "white"))


def render_header(snap: MarketAnalysisSnapshot, settings: dict) -> Panel:
    tfs = settings["market"]["timeframes"]
    session = snap.session_info
    active = ", ".join(session.get("active_sessions", ["—"])).upper() or "—"
    utc = session.get("current_utc", "—")

    lines = Text()
    lines.append(f"  Symbol : {snap.symbol}\n", style="bold cyan")
    lines.append(f"  Price  : {snap.current_price:,.4f}\n", style="bold white")
    lines.append(f"  Time   : {utc}\n", style="dim")
    lines.append(f"  Session: {active}\n", style="bold magenta")
    lines.append(f"  Zone   : {snap.premium_discount.upper()}\n",
                 style={"premium": "bold red", "discount": "bold green", "equilibrium": "bold yellow"}.get(
                     snap.premium_discount, "white"))
    lines.append(f"\n  HTF ({tfs['htf']}) Trend : ")
    lines.append_text(trend_badge(snap.htf_trend))
    lines.append(f"\n  LTF ({tfs['ltf']}) Trend : ")
    lines.append_text(trend_badge(snap.ltf_trend))

    return Panel(lines, title="[bold white]ICT Market Analysis[/bold white]",
                 border_style="cyan", padding=(0, 1))


def render_structure(snap: MarketAnalysisSnapshot, settings: dict) -> Table:
    tfs = settings["market"]["timeframes"]
    t = Table(title="Market Structure", box=box.SIMPLE_HEAD, show_header=True,
              header_style="bold cyan")
    t.add_column("TF", style="dim", width=6)
    t.add_column("Trend", width=12)
    t.add_column("Last BOS", width=20)
    t.add_column("Last CHoCH", width=20)
    t.add_column("Last HH", width=12)
    t.add_column("Last LL", width=12)

    for label, ms in [(tfs["htf"], snap.htf_structure), (tfs["ltf"], snap.ltf_structure)]:
        bos_str = "—"
        if ms.last_bos:
            color = "green" if "bull" in ms.last_bos.event_type else "red"
            bos_str = f"[{color}]{ms.last_bos.event_type} @ {ms.last_bos.price:.4f}[/{color}]"
        choch_str = "—"
        if ms.last_choch:
            color = "green" if "bull" in ms.last_choch.event_type else "red"
            choch_str = f"[{color}]{ms.last_choch.event_type} @ {ms.last_choch.price:.4f}[/{color}]"
        hh_str = f"[green]{ms.last_hh.price:.4f}[/green]" if ms.last_hh else "—"
        ll_str = f"[red]{ms.last_ll.price:.4f}[/red]" if ms.last_ll else "—"

        t.add_row(label, trend_badge(ms.trend), bos_str, choch_str, hh_str, ll_str)

    return t


def render_order_blocks(snap: MarketAnalysisSnapshot) -> Table:
    t = Table(title="Order Blocks", box=box.SIMPLE_HEAD, header_style="bold cyan")
    t.add_column("Type", width=12)
    t.add_column("Zone", width=22)
    t.add_column("Disp%", width=8)
    t.add_column("Mitigated", width=10)
    t.add_column("Breaker", width=8)
    t.add_column("Timestamp", width=20)

    max_show = 5
    obs = (
        snap.ob_result.bullish_obs[-max_show:] +
        snap.ob_result.bearish_obs[-max_show:]
    )
    obs.sort(key=lambda ob: ob.index, reverse=True)

    for ob in obs[:max_show * 2]:
        color = "green" if ob.kind == "bullish" else "red"
        kind_label = f"[{color}]{'Bull' if ob.kind == 'bullish' else 'Bear'} OB[/{color}]"
        if ob.is_breaker:
            kind_label = f"[{color}]Breaker[/{color}]"
        zone = f"[{color}]{ob.bottom:.4f} – {ob.top:.4f}[/{color}]"
        mitigated = "[red]YES[/red]" if ob.is_mitigated else "[green]NO[/green]"
        breaker = "[yellow]YES[/yellow]" if ob.is_breaker else "—"
        ts = ob.timestamp.strftime("%m-%d %H:%M")

        t.add_row(kind_label, zone, f"{ob.displacement_pct:.2f}%", mitigated, breaker, ts)

    if not obs:
        t.add_row("—", "No OBs detected", "—", "—", "—", "—")
    return t


def render_fvgs(snap: MarketAnalysisSnapshot) -> Table:
    t = Table(title="Fair Value Gaps", box=box.SIMPLE_HEAD, header_style="bold cyan")
    t.add_column("Type", width=12)
    t.add_column("Zone", width=22)
    t.add_column("Gap%", width=8)
    t.add_column("Fill%", width=8)
    t.add_column("Filled", width=8)
    t.add_column("Timestamp", width=20)

    max_show = 5
    fvgs = (
        snap.fvg_result.bullish_fvgs[-max_show:] +
        snap.fvg_result.bearish_fvgs[-max_show:]
    )
    fvgs.sort(key=lambda f: f.index, reverse=True)

    for fvg in fvgs[:max_show * 2]:
        color = "green" if fvg.kind == "bullish" else "red"
        kind_label = f"[{color}]{'Bull' if fvg.kind == 'bullish' else 'Bear'} FVG[/{color}]"
        if fvg.is_inverse:
            kind_label = f"[{color}]IFVG[/{color}]"
        zone = f"[{color}]{fvg.bottom:.4f} – {fvg.top:.4f}[/{color}]"
        filled = "[red]YES[/red]" if fvg.is_filled else "[green]NO[/green]"
        ts = fvg.timestamp.strftime("%m-%d %H:%M")
        t.add_row(kind_label, zone, f"{fvg.gap_pct:.3f}%", f"{fvg.fill_pct:.1f}%", filled, ts)

    if not fvgs:
        t.add_row("—", "No FVGs detected", "—", "—", "—", "—")
    return t


def render_liquidity(snap: MarketAnalysisSnapshot) -> Table:
    t = Table(title="Liquidity Levels", box=box.SIMPLE_HEAD, header_style="bold cyan")
    t.add_column("Type", width=12)
    t.add_column("Price", width=14)
    t.add_column("Strength", width=10)
    t.add_column("Swept", width=8)
    t.add_column("Inducement", width=12)
    t.add_column("Timestamp", width=20)

    liq = snap.liquidity_result
    max_show = 5
    levels = (
        sorted(liq.bsl_levels, key=lambda l: l.index, reverse=True)[:max_show] +
        sorted(liq.ssl_levels, key=lambda l: l.index, reverse=True)[:max_show]
    )
    levels.sort(key=lambda l: l.price, reverse=True)

    for lvl in levels[:max_show * 2]:
        color = "green" if lvl.kind == "ssl" else "red"
        kind_label = f"[{color}]{'BSL' if lvl.kind == 'bsl' else 'SSL'}[/{color}]"
        price_str = f"[{color}]{lvl.price:.4f}[/{color}]"
        swept = "[red]YES[/red]" if lvl.is_swept else "[green]NO[/green]"
        inducement = "[yellow]YES[/yellow]" if lvl.is_inducement else "—"
        ts = lvl.timestamp.strftime("%m-%d %H:%M")
        t.add_row(kind_label, price_str, str(lvl.strength), swept, inducement, ts)

    if not levels:
        t.add_row("—", "No levels detected", "—", "—", "—", "—")
    return t


def render_setups(snap: MarketAnalysisSnapshot) -> Panel:
    if not snap.setups:
        return Panel(
            "[dim]No high-confluence setups detected.[/dim]\n"
            "[dim]Waiting for better conditions...[/dim]",
            title="[bold white]Trade Setups[/bold white]",
            border_style="dim",
        )

    content = Text()
    for i, setup in enumerate(snap.setups, 1):
        color = "green" if setup.direction == "long" else "red"
        dir_label = "▲ LONG" if setup.direction == "long" else "▼ SHORT"
        content.append(f"\n  #{i} [{dir_label}]  Score: {setup.confluence_score}  |  R:R {setup.risk_reward:.2f}\n",
                        style=f"bold {color}")
        content.append(f"     Entry  : {setup.entry_price:,.4f}\n", style="white")
        content.append(f"     SL     : {setup.stop_loss:,.4f}  ({setup.risk_pct:.2f}% risk)\n", style="red")
        content.append(f"     TP     : {setup.take_profit:,.4f}  ({setup.reward_pct:.2f}% reward)\n", style="green")
        if setup.liquidity_target:
            content.append(f"     Target : {setup.liquidity_target:,.4f}\n", style="cyan")
        content.append("     Confluence:\n", style="dim")
        for reason in setup.confluence_reasons:
            content.append(f"       ✓ {reason}\n", style="dim green")

    return Panel(content, title="[bold white]Trade Setups[/bold white]",
                 border_style="green" if snap.setups else "dim")


def print_analysis(snap: MarketAnalysisSnapshot, settings: dict) -> None:
    console.print()
    console.print(render_header(snap, settings))
    console.print(render_structure(snap, settings))
    console.print(render_order_blocks(snap))
    console.print(render_fvgs(snap))
    console.print(render_liquidity(snap))
    console.print(render_setups(snap))
    console.print()


# ---------------------------------------------------------------------------
# Main Logic
# ---------------------------------------------------------------------------

def run_analysis(symbol: str, settings: dict) -> MarketAnalysisSnapshot:
    fetcher = MarketDataFetcher(settings)
    strategy = ICTStrategy(settings)
    tfs = settings["market"]["timeframes"]

    console.print(f"[dim]Fetching data for [cyan]{symbol}[/cyan]...[/dim]")

    htf_df = fetcher.fetch_ohlcv(symbol, tfs["htf"], limit=300)
    ltf_df = fetcher.fetch_ohlcv(symbol, tfs["ltf"], limit=300)
    current_price = fetcher.get_current_price(symbol)
    session_info = fetcher.get_session_info()

    snap = strategy.analyze(
        symbol=symbol,
        htf_df=htf_df,
        ltf_df=ltf_df,
        current_price=current_price,
        session_info=session_info,
    )
    return snap


def main():
    parser = argparse.ArgumentParser(
        description="ICT Market Analysis — Order Block / FVG / Liquidity"
    )
    parser.add_argument("--symbol", type=str, default=None,
                        help="Trading symbol (e.g. BTC/USDT)")
    parser.add_argument("--watch", action="store_true",
                        help="Continuously refresh analysis every 60s")
    parser.add_argument("--interval", type=int, default=60,
                        help="Refresh interval in seconds (with --watch)")
    parser.add_argument("--list-symbols", action="store_true",
                        help="List configured symbols and exit")
    args = parser.parse_args()

    settings = load_settings()

    if args.list_symbols:
        console.print("[bold cyan]Configured symbols:[/bold cyan]")
        for s in settings["market"]["symbols"]:
            console.print(f"  • {s}")
        return

    symbol = args.symbol or settings["market"]["default_symbol"]

    if args.watch:
        console.print(f"[bold cyan]Watch mode:[/bold cyan] refreshing every {args.interval}s. Ctrl+C to stop.\n")
        try:
            while True:
                console.clear()
                try:
                    snap = run_analysis(symbol, settings)
                    print_analysis(snap, settings)
                except Exception as e:
                    console.print(f"[red]Error during analysis: {e}[/red]")
                console.print(f"[dim]Next refresh in {args.interval}s...[/dim]")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            console.print("\n[dim]Watch mode stopped.[/dim]")
    else:
        try:
            snap = run_analysis(symbol, settings)
            print_analysis(snap, settings)
        except Exception as e:
            console.print(f"[red]Analysis failed: {e}[/red]")
            sys.exit(1)


if __name__ == "__main__":
    main()
