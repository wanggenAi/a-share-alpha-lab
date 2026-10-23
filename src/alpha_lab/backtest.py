"""Single-symbol research experiment, not production broker simulation."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import floor

from .data import Bar, validate_bars
from .strategy import detect


@dataclass(frozen=True)
class Assumptions:
    capital_per_trade: float = 20_000.0
    profit_target: float = 0.05
    stop_loss: float = 0.03
    max_holding_sessions: int = 15
    commission_rate: float = 0.0003
    commission_min: float = 5.0
    sell_stamp_tax: float = 0.0005
    transfer_fee_rate: float = 0.00001
    one_way_slippage: float = 0.0005
    main_board_price_limit: float = 0.10


def _locked(bar: Bar, prior_close: float, direction: str, limit: float) -> bool:
    """Conservative skip of one-price limit sessions; not order-book matching."""
    edge = round(prior_close * (1 + limit if direction == "up" else 1 - limit), 2)
    return (
        bar.volume <= 0
        or (bar.high == bar.low and abs(bar.open - edge) <= 0.011)
    )


def research_backtest(bars: list[Bar], cfg: Assumptions = Assumptions()) -> dict:
    validate_bars(bars)
    if not (
        cfg.capital_per_trade > 0
        and 0 < cfg.profit_target < 1
        and 0 < cfg.stop_loss < 1
        and cfg.max_holding_sessions >= 1
        and 0 <= cfg.one_way_slippage < 1
    ):
        raise ValueError("INVALID_BACKTEST_ASSUMPTIONS")
    trades: list[dict] = []
    censored = 0
    i = 64
    while i < len(bars) - 1:
        signal = detect(bars[: i + 1])
        if signal is None:
            i += 1
            continue
        entry_day = bars[i + 1]
        if _locked(entry_day, bars[i].close, "up", cfg.main_board_price_limit):
            i += 1
            continue
        entry_price = entry_day.open * (1 + cfg.one_way_slippage)
        shares = floor(cfg.capital_per_trade / entry_price / 100) * 100
        if shares < 100:
            i += 1
            continue
        entry_gross = shares * entry_price
        buy_fee = max(cfg.commission_min, entry_gross * cfg.commission_rate) + entry_gross * cfg.transfer_fee_rate
        stop = entry_price * (1 - cfg.stop_loss)
        target = entry_price * (1 + cfg.profit_target)
        exit_idx = None
        exit_price = None
        reason = ""
        # T+1: the earliest exit is one session AFTER the entry session.
        for j in range(i + 2, min(len(bars), i + 2 + cfg.max_holding_sessions)):
            day = bars[j]
            if _locked(day, bars[j - 1].close, "down", cfg.main_board_price_limit):
                continue
            holding_sessions = j - (i + 1)
            if day.low <= stop:
                exit_price = min(day.open, stop) * (1 - cfg.one_way_slippage)
                reason = "STOP_FIRST_IF_AMBIGUOUS"
            elif day.high >= target:
                exit_price = max(day.open, target) * (1 - cfg.one_way_slippage)
                reason = "TARGET"
            elif holding_sessions >= cfg.max_holding_sessions:
                exit_price = day.close * (1 - cfg.one_way_slippage)
                reason = "TIME"
            if exit_price is not None:
                exit_idx = j
                break
        if exit_idx is None:
            # Unclosed trades are censored, NOT counted as profitable exits.
            censored += 1
            i += 1
            continue
        exit_gross = shares * exit_price
        sell_fee = max(cfg.commission_min, exit_gross * cfg.commission_rate)
        sell_fee += exit_gross * (cfg.sell_stamp_tax + cfg.transfer_fee_rate)
        net_pnl = exit_gross - sell_fee - entry_gross - buy_fee
        trades.append({
            "symbol": signal.symbol,
            "signal_date": signal.asof,
            "entry_date": entry_day.date,
            "exit_date": bars[exit_idx].date,
            "entry_price": round(entry_price, 4),
            "exit_price": round(exit_price, 4),
            "shares": shares,
            "net_pnl": round(net_pnl, 2),
            "net_return_pct": round(100 * net_pnl / (entry_gross + buy_fee), 4),
            "reason": reason,
        })
        i = exit_idx + 1
    wins = sum(t["net_pnl"] > 0 for t in trades)
    equity = cfg.capital_per_trade
    peak = equity
    max_drawdown = 0.0
    for trade in trades:
        equity += trade["net_pnl"]
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)
    return {
        "status": "RESEARCH_ONLY_NOT_VALIDATED",
        "symbol": bars[0].symbol,
        "data_start": bars[0].date,
        "data_end": bars[-1].date,
        "strategy": "trend_pullback_v01",
        "assumptions": asdict(cfg),
        "limitations": [
            "unadjusted_history_corporate_actions_unhandled",
            "point_in_time_universe_unverified",
            "single_symbol_not_portfolio",
            "simplified_main_board_limits_and_fills",
            "no_out_of_sample_validation",
        ],
        "trade_count": len(trades),
        "censored_signals": censored,
        "win_rate": (round(wins / len(trades), 4) if trades else None),
        "average_net_trade_return_pct": (
            round(sum(t["net_return_pct"] for t in trades) / len(trades), 4)
            if trades else None
        ),
        "max_closed_trade_equity_drawdown_pct": round(max_drawdown * 100, 4),
        "trades": trades,
    }
