"""Chronological out-of-sample experiments of a PRE-FIXED technical rule.

No fitting/search of parameters is performed. Thus this is rolling temporal
holdout evaluation, not a learned walk-forward model or validation of profitability.
Historical unadjusted OHLCV cannot establish real tradability/total returns.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .backtest import research_backtest
from .data import load_csv, validate_bars, Bar


def evaluate_rolling_holdout(bars: list[Bar], *, warmup: int = 120,
                             window: int = 60, min_folds: int = 2) -> dict:
    validate_bars(bars)
    if warmup < 65 or window < 3 or min_folds < 1:
        raise ValueError("INVALID_EVALUATION_WINDOW")
    if len(bars) < warmup + window * min_folds:
        raise ValueError("INSUFFICIENT_DATA_FOR_HOLDOUT")
    folds = []
    # Fixed, non-overlapping OOS calendar windows; each fold uses only the
    # history available through its own end. Never import future observations.
    for first in range(warmup, len(bars) - window + 1, window):
        end = first + window
        history = bars[:end]
        test_start, test_end = bars[first].date, history[-1].date
        trial = research_backtest(history, signal_start=test_start)
        trades = trial["trades"]
        assert all(test_start <= t["signal_date"] < t["entry_date"] <= test_end
                   for t in trades)
        # Close-to-close passive change is a reference only, NOT an investable
        # portfolio benchmark or directly comparable with sparse trades.
        passive_pct = 100 * (history[-1].close / bars[first].close - 1)
        folds.append({
            "train_end": bars[first - 1].date,
            "test_start": test_start,
            "test_end": test_end,
            "trade_count": len(trades),
            "censored_signals": trial["censored_signals"],
            "net_realized_pnl": round(sum(t["net_pnl"] for t in trades), 2),
            "mean_net_trade_return_pct": (
                round(sum(t["net_return_pct"] for t in trades) / len(trades), 4)
                if trades else None
            ),
            "passive_close_change_pct_reference_only": round(passive_pct, 4),
            "trades": trades,
        })
    count = sum(f["trade_count"] for f in folds)
    all_trades = [t for f in folds for t in f["trades"]]
    wins = sum(t["net_pnl"] > 0 for t in all_trades)
    return {
        "schema_version": "0.3",
        "status": "EXPERIMENTAL_HOLDOUT_NOT_INVESTMENT_VALIDATION",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": bars[0].symbol,
        "strategy": "fixed_trend_pullback_v01_no_parameter_search",
        "input_adjustment": "UNKNOWN_UNVERIFIED",
        "warmup_sessions": warmup,
        "holdout_window_sessions": window,
        "fold_count": len(folds),
        "closed_trade_count": count,
        "censored_signals": sum(f["censored_signals"] for f in folds),
        "aggregate_win_rate": round(wins / count, 4) if count else None,
        "aggregate_mean_net_trade_return_pct": (
            round(sum(t["net_return_pct"] for t in all_trades) / count, 4)
            if count else None
        ),
        "folds": folds,
        "limitations": [
            "unadjusted_prices_and_corporate_actions_unverified",
            "not_a_real_portfolio_equity_curve",
            "no_point_in_time_universe_and_delisting_coverage",
            "not_walk_forward_fitting_fixed_rule_only",
            "fold_boundaries_censor_unclosed_trades_no_cross_fold_double_counting",
            "passive_price_change_not_total_return_benchmark",
            "no_proven_out_of_sample_edge_or_live_tradability",
        ],
    }


def evaluate_file(path: str | Path, *, warmup: int = 120,
                  window: int = 60, min_folds: int = 2) -> dict:
    return evaluate_rolling_holdout(load_csv(path), warmup=warmup,
                                    window=window, min_folds=min_folds)
