"""Conservative multi-symbol historical portfolio accounting experiment.

Not an investable backtest: requires aligned main-board OHLCV, lacks verified
PIT delistings, ST rules, corporate actions, and executable order-book fills.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from math import floor, isfinite
from pathlib import Path

from .backtest import Assumptions, _locked
from .data import Bar, load_csv, validate_bars
from .ingestion import check_ingestion_manifest
from .strategy import detect


@dataclass(frozen=True)
class PortfolioRules:
    starting_cash: float = 100000.0
    first_trade_date: str = ""
    max_positions: int = 5
    allocation_fraction: float = 0.20


def _board(symbol: str) -> bool:
    return symbol.startswith(("000", "001", "002", "003", "600", "601", "603", "605"))


def _buy_fee(gross: float, a: Assumptions) -> float:
    return max(a.commission_min, gross * a.commission_rate) + gross * a.transfer_fee_rate


def _sell_fee(gross: float, a: Assumptions) -> float:
    return max(a.commission_min, gross * a.commission_rate) + gross * (a.sell_stamp_tax + a.transfer_fee_rate)


def _check(histories: dict[str, list[Bar]], rules: PortfolioRules, costs: Assumptions):
    if not (isfinite(rules.starting_cash) and rules.starting_cash > 0
            and type(rules.max_positions) is int and 1 <= rules.max_positions <= 20
            and isfinite(rules.allocation_fraction) and 0 < rules.allocation_fraction <= 1
            and all(isfinite(v) for v in (costs.profit_target, costs.stop_loss,
                costs.commission_rate, costs.commission_min, costs.sell_stamp_tax,
                costs.transfer_fee_rate, costs.one_way_slippage, costs.main_board_price_limit))
            and 0 < costs.profit_target < 1 and 0 < costs.stop_loss < 1
            and type(costs.max_holding_sessions) is int and costs.max_holding_sessions > 0
            and 0 <= costs.one_way_slippage < .1
            and min(costs.commission_rate, costs.commission_min, costs.sell_stamp_tax,
                    costs.transfer_fee_rate) >= 0 and costs.main_board_price_limit == .10):
        raise ValueError("INVALID_PORTFOLIO_RULES")
    try:
        d = date.fromisoformat(rules.first_trade_date)
        if d.isoformat() != rules.first_trade_date:
            raise ValueError
    except ValueError as exc:
        raise ValueError("INVALID_PORTFOLIO_START_DATE") from exc
    if not isinstance(histories, dict) or not 1 <= len(histories) <= 30:
        raise ValueError("INVALID_PORTFOLIO_UNIVERSE_SIZE")
    calendar = None
    for symbol, bars in sorted(histories.items()):
        validate_bars(bars)
        if symbol != bars[0].symbol or not _board(symbol):
            raise ValueError("UNSUPPORTED_OR_MISMATCHED_BOARD")
        dates = [b.date for b in bars]
        if calendar is None:
            calendar = dates
        elif dates != calendar:
            raise ValueError("INCOMPLETE_OR_MISALIGNED_SESSION_PANEL")
        for i in range(1, len(bars)):
            previous, current = bars[i-1], bars[i]
            if current.volume == 0 and any(abs(x-previous.close) > .011 for x in (
                    current.open, current.high, current.low, current.close)):
                raise ValueError("ZERO_VOLUME_BAR_WITH_PRICE_MOVEMENT")
            if (abs(current.open / previous.close - 1) > .105
                    or abs(current.close / previous.close - 1) > .105):
                raise ValueError("PRICE_LIMIT_OR_CORPORATE_ACTION_UNVERIFIED")
    assert calendar is not None
    if rules.first_trade_date not in calendar:
        raise ValueError("START_DATE_NOT_IN_EXACT_SESSION_CALENDAR")
    first = calendar.index(rules.first_trade_date)
    if first < 65:
        raise ValueError("INSUFFICIENT_WARMUP_SESSIONS")
    return sorted(histories), calendar, first


def simulate_portfolio(histories: dict[str, list[Bar]], rules: PortfolioRules,
                       costs: Assumptions = Assumptions(),
                       *, benchmark: list[Bar] | None = None) -> dict:
    """No future signal data; hypothetical next-open buys and T+1 exits.

    Intraday sell proceeds are never recycled to fund same-day opening buys.
    Positions held at final session are only marked, never called closed wins.
    """
    symbols, calendar, first = _check(histories, rules, costs)
    if benchmark is not None:
        validate_bars(benchmark)
        if [b.date for b in benchmark] != calendar:
            raise ValueError("BENCHMARK_CALENDAR_NOT_ALIGNED")
    cash = rules.starting_cash
    positions = {}
    orders, trades, equity_curve = [], [], []
    realized = turnover = 0.0
    peak = cash
    worst_drawdown = 0.0
    stale_marks = 0

    def log(day, symbol, action, state, reason, **more):
        orders.append(dict(date=day, symbol=symbol, action=action,
                           state=state, reason=reason, **more))

    for i in range(first, len(calendar)):
        day = calendar[i]
        # Signal is based on the prior CLOSED session, not today's high/low.
        for symbol in symbols:
            signal = detect(histories[symbol][:i])
            if signal is None:
                continue
            bar, prev = histories[symbol][i], histories[symbol][i-1]
            why = None
            if symbol in positions:
                why = "ALREADY_HELD"
            elif len(positions) >= rules.max_positions:
                why = "MAX_POSITIONS"
            elif bar.volume <= 0:
                why = "HALT_OR_ZERO_VOLUME"
            elif _locked(bar, prev.close, "up", costs.main_board_price_limit):
                why = "ONE_PRICE_LIMIT_UP"
            if why:
                log(day, symbol, "BUY", "SKIPPED", why, signal_date=signal.asof)
                continue
            fill = bar.open * (1 + costs.one_way_slippage)
            budget = min(cash, rules.starting_cash * rules.allocation_fraction)
            lots = floor(budget / fill / 100)
            while lots > 0:
                gross = 100 * lots * fill
                fee = _buy_fee(gross, costs)
                if gross + fee <= budget + 1e-8:
                    break
                lots -= 1
            if lots == 0:
                log(day, symbol, "BUY", "SKIPPED", "INSUFFICIENT_CASH_FOR_LOT_AND_FEES",
                    signal_date=signal.asof)
                continue
            shares = 100 * lots
            total = gross + fee
            cash -= total
            turnover += gross
            positions[symbol] = dict(shares=shares, entry_index=i, entry_date=day,
                signal_date=signal.asof, entry_fill=fill, entry_gross=gross,
                entry_fee=fee, entry_total=total,
                stop=fill * (1-costs.stop_loss), target=fill * (1+costs.profit_target))
            log(day, symbol, "BUY", "HYPOTHETICALLY_FILLED", "NEXT_SESSION_OPEN",
                signal_date=signal.asof, shares=shares, price=round(fill, 6),
                fee=round(fee, 4))
        # Sell decisions may use that session's high and low under the
        # conservative stop-first ambiguity convention.
        for symbol in sorted(list(positions)):
            pos = positions[symbol]
            if i <= pos["entry_index"]:
                continue  # T+1
            bar, prior = histories[symbol][i], histories[symbol][i-1]
            if bar.volume <= 0:
                log(day, symbol, "SELL", "SKIPPED", "HALT_OR_ZERO_VOLUME")
                continue
            if _locked(bar, prior.close, "down", costs.main_board_price_limit):
                log(day, symbol, "SELL", "SKIPPED", "ONE_PRICE_LIMIT_DOWN")
                continue
            fill, reason = None, None
            if bar.low <= pos["stop"]:
                fill = min(bar.open, pos["stop"]) * (1-costs.one_way_slippage)
                reason = "STOP_FIRST_IF_BOTH_LEVELS_TOUCHED"
            elif bar.high >= pos["target"]:
                fill = max(bar.open, pos["target"]) * (1-costs.one_way_slippage)
                reason = "TARGET_LEVEL"
            elif i-pos["entry_index"] >= costs.max_holding_sessions:
                fill = bar.close * (1-costs.one_way_slippage)
                reason = "MAX_HOLDING_SESSIONS_CLOSE_ASSUMPTION"
            if fill is None:
                continue
            gross = pos["shares"] * fill
            fee = _sell_fee(gross, costs)
            pnl = gross - fee - pos["entry_total"]
            cash += gross - fee
            realized += pnl
            turnover += gross
            trades.append(dict(symbol=symbol, signal_date=pos["signal_date"],
                entry_date=pos["entry_date"], exit_date=day,
                shares=pos["shares"], entry_price=round(pos["entry_fill"], 6),
                exit_price=round(fill, 6), buy_fee=round(pos["entry_fee"], 4),
                sell_fee=round(fee, 4), net_pnl=round(pnl, 4), reason=reason))
            log(day, symbol, "SELL", "HYPOTHETICALLY_FILLED", reason,
                shares=pos["shares"], price=round(fill, 6), fee=round(fee, 4))
            del positions[symbol]
        market_value = sum(pos["shares"] * histories[s][i].close
                           for s, pos in positions.items())
        unrealized = sum(pos["shares"] * histories[s][i].close-pos["entry_total"]
                         for s, pos in positions.items())
        equity = cash + market_value
        # Double-entry reconciliation on EVERY observed trading session.
        if abs(equity - (rules.starting_cash + realized + unrealized)) > 1e-5:
            raise AssertionError("PORTFOLIO_CASH_PNL_RECONCILIATION_FAILURE")
        flagged = any(histories[s][i].volume <= 0 for s in positions)
        if flagged:
            stale_marks += 1
        peak = max(peak, equity)
        drawdown = (peak-equity)/peak
        worst_drawdown = max(worst_drawdown, drawdown)
        equity_curve.append(dict(date=day, cash=round(cash, 4),
            market_value=round(market_value, 4), equity=round(equity, 4),
            realized_pnl=round(realized, 4), unrealized_pnl=round(unrealized, 4),
            exposure_pct=round(100*market_value/equity, 4) if equity > 0 else None,
            drawdown_pct=round(100*drawdown, 4), open_positions=len(positions),
            stale_mark=flagged))
    ending = equity_curve[-1]["equity"]
    reference = None if benchmark is None else {
        "symbol": benchmark[0].symbol,
        "unadjusted_price_change_pct": round(
            100*(benchmark[-1].close / benchmark[first-1].close - 1), 4),
        "not_investable_or_total_return_comparison": True,
    }
    return dict(schema_version="0.9",
        status="UNVERIFIED_HISTORICAL_PORTFOLIO_RESEARCH_ONLY",
        created_utc=datetime.now(timezone.utc).isoformat(),
        first_trade_date=rules.first_trade_date, last_session=calendar[-1],
        universe_symbols=symbols, rules=asdict(rules),
        costs=asdict(costs), strategy="fixed_trend_pullback_v01_symbol_code_order",
        metrics=dict(starting_equity=rules.starting_cash,
            ending_equity_marked=ending,
            total_marked_return_pct=round(100*(ending/rules.starting_cash-1), 4),
            max_marked_drawdown_pct=round(100*worst_drawdown, 4),
            closed_trade_count=len(trades),
            closed_trade_win_rate=round(sum(t["net_pnl"] > 0 for t in trades)/len(trades), 4)
                if trades else None,
            turnover_to_starting_capital=round(turnover/rules.starting_cash, 4),
            ending_cash=equity_curve[-1]["cash"],
            ending_open_positions=len(positions),
            stale_mark_sessions=stale_marks),
        orders=orders, trades=trades, daily_equity=equity_curve,
        open_positions=[dict(symbol=s, shares=p["shares"], entry_date=p["entry_date"],
            signal_date=p["signal_date"], total_entry_cost=round(p["entry_total"], 4),
            marked_close=histories[s][-1].close)
            for s, p in sorted(positions.items())],
        benchmark_price_reference=reference,
        limitations=[
            "not_point_in_time_universe_ignores_delisted_issuers",
            "unadjusted_raw_prices_corporate_actions_and_dividends_unhandled",
            "strict_identical_session_calendar_cannot_handle_missing_suspension_rows",
            "ST_IPO_and_no_limit_sessions_unverified_main_board_only",
            "hypothetical_stop_target_fills_not_order_book_executions",
            "fixed_code_order_not_quality_ranking_or_walk_forward_optimization",
            "benchmark_price_only_not_total_return",
            "no_verified_out_of_sample_edge_or_reliable_investment_recommendation",
        ])


def portfolio_from_directory(directory: str | Path, rules: PortfolioRules,
                             costs: Assumptions = Assumptions(),
                             benchmark_csv: str | Path | None = None) -> dict:
    root = Path(directory)
    if not root.is_dir():
        raise ValueError("PORTFOLIO_DIRECTORY_NOT_FOUND")
    manifest = check_ingestion_manifest(root)
    paths = sorted(root.glob("*.csv"))
    if not 1 <= len(paths) <= 30:
        raise ValueError("INVALID_PORTFOLIO_INPUT_CSV_COUNT")
    histories = {}
    for path in paths:
        bars = load_csv(path)
        if bars[0].symbol in histories:
            raise ValueError("DUPLICATE_PORTFOLIO_SYMBOL")
        histories[bars[0].symbol] = bars
    benchmark = load_csv(benchmark_csv) if benchmark_csv is not None else None
    result = simulate_portfolio(histories, rules, costs, benchmark=benchmark)
    result["input_provenance"] = (
        {"status": manifest["status"], "source": manifest["source"],
         "retrieved_at_utc": manifest["retrieved_at_utc"]}
        if manifest else {"status": "UNMANAGED_USER_CSV_UNVERIFIED"})
    return result
