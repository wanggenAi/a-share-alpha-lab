"""Chronological, non-overlapping portfolio experiments using a FROZEN rule.

These fixed-rule folds are NOT an optimized walk-forward model, a point-in-
time investable universe, nor statistically established out-of-sample alpha.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from .data import load_csv
from .ingestion import check_ingestion_manifest
from .portfolio import PortfolioRules, simulate_portfolio
from .tradability import require_eligible_histories


def evaluate_portfolio_folds(histories: dict, *, warmup_sessions: int = 120,
                             test_sessions: int = 60, min_folds: int = 2,
                             starting_cash: float = 100000.0,
                             max_positions: int = 5,
                             allocation_fraction: float = 0.20) -> dict:
    if (type(warmup_sessions) is not int or warmup_sessions < 65
            or type(test_sessions) is not int or test_sessions < 3
            or type(min_folds) is not int or min_folds < 2):
        raise ValueError("INVALID_PORTFOLIO_EVALUATION_WINDOWS")
    if not isinstance(histories, dict) or not histories:
        raise ValueError("INVALID_PORTFOLIO_HISTORIES")
    all_dates = [bar.date for bar in next(iter(histories.values()))]
    if any([b.date for b in bars] != all_dates for bars in histories.values()):
        raise ValueError("PORTFOLIO_EVALUATION_CALENDAR_MISMATCH")
    if len(all_dates) < warmup_sessions + min_folds * test_sessions:
        raise ValueError("INSUFFICIENT_PORTFOLIO_HOLDOUT_HISTORY")
    folds = []
    # All symbols present in the current user-provided panel: survivorship
    # bias remains unresolved, explicitly labeled below.
    for i in range(warmup_sessions, len(all_dates)-test_sessions+1, test_sessions):
        end = i + test_sessions
        rules = PortfolioRules(
            starting_cash=starting_cash, max_positions=max_positions,
            allocation_fraction=allocation_fraction, first_trade_date=all_dates[i])
        truncated = {symbol: bars[:end] for symbol, bars in histories.items()}
        report = simulate_portfolio(truncated, rules)
        metrics = report["metrics"]
        if any(t["entry_date"] < all_dates[i] or t["exit_date"] > all_dates[end-1]
               for t in report["trades"]):
            raise AssertionError("PORTFOLIO_HOLDOUT_TRADE_LEAK")
        folds.append({
            "prior_history_last_date": all_dates[i-1],
            "first_test_session": all_dates[i],
            "last_test_session": all_dates[end-1],
            "simulation_status": report["status"],
            "trade_count": metrics["closed_trade_count"],
            "ending_open_positions_marked_not_liquidated": metrics["ending_open_positions"],
            "net_marked_return_pct": metrics["total_marked_return_pct"],
            "max_marked_drawdown_pct": metrics["max_marked_drawdown_pct"],
            "ending_marked_equity": metrics["ending_equity_marked"],
            "daily_equity": report["daily_equity"],
            "trades": report["trades"],
        })
    returns = [f["net_marked_return_pct"] for f in folds]
    return {
        "schema_version": "0.11",
        "status": "EXPERIMENTAL_PORTFOLIO_TIME_SPLITS_UNVALIDATED",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "strategy": "frozen_trend_pullback_v01_no_fitting_or_search",
        "symbol_universe": sorted(histories),
        "warmup_sessions": warmup_sessions,
        "test_sessions_per_fold": test_sessions,
        "fold_count": len(folds),
        "starting_cash_each_independent_fold": starting_cash,
        "max_positions": max_positions,
        "allocation_fraction": allocation_fraction,
        "mean_fold_marked_return_pct_not_compounded": round(mean(returns), 4),
        "positive_return_fold_count": sum(v > 0 for v in returns),
        "folds": folds,
        "limitations": [
            "fixed_rules_not_retrained_or_optimised_this_is_not_walk_forward_fitting",
            "not_point_in_time_symbol_universe_or_survivorship_corrected",
            "raw_unadjusted_prices_no_dividends_splits_or_restatements",
            "strict_identical_exchange_session_panels_main_board_only",
            "historical_intraday_fills_and_costs_are_hypothetical",
            "folds_restart_from_cash_open_positions_marked_not_liquidated",
            "mean_of_fold_returns_is_not_compounded_strategy_annualized_return",
            "no_independent_evidence_of_positive_future_alpha",
        ],
    }


def portfolio_folds_from_directory(directory: str | Path,
                                   eligibility_ledger: str | Path | None = None,
                                   **kwargs) -> dict:
    root = Path(directory)
    if not root.is_dir():
        raise ValueError("PORTFOLIO_DIRECTORY_NOT_FOUND")
    manifest = check_ingestion_manifest(root)
    paths = sorted(root.glob("*.csv"))
    if not 1 <= len(paths) <= 30:
        raise ValueError("INVALID_PORTFOLIO_INPUT_CSV_COUNT")
    histories = {}
    for file in paths:
        bars = load_csv(file)
        if bars[0].symbol in histories:
            raise ValueError("DUPLICATE_PORTFOLIO_SYMBOL")
        histories[bars[0].symbol] = bars
    eligibility = (require_eligible_histories(histories, eligibility_ledger)
                   if eligibility_ledger is not None else None)
    report = evaluate_portfolio_folds(histories, **kwargs)
    report["tradability_evidence"] = (
        {"status": eligibility["status"], "required_sessions": eligibility["required_sessions"],
         "source_verification": eligibility["source_verification"]}
        if eligibility else {"status": "NOT_PROVIDED_UNVERIFIED"})
    report["input_provenance"] = (
        {"status": manifest["status"], "source": manifest["source"]}
        if manifest else {"status": "UNMANAGED_USER_CSV_UNVERIFIED"})
    return report
