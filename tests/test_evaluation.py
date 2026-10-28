"""Chronological holdout: explicit non-overlap, no leakage and insufficient-data gates."""
from datetime import date, timedelta

import pytest

from alpha_lab.data import Bar, save_csv
from alpha_lab.backtest import research_backtest
from alpha_lab.evaluation import evaluate_rolling_holdout, evaluate_file


def history(n=300):
    start = date(2024, 1, 1)
    # One gradual rise; values are deterministic synthetic research fixtures.
    closes = [10 + i * 0.025 for i in range(n)]
    return [
        Bar("600519", (start + timedelta(days=i)).isoformat(),
            c - 0.02, c + 0.1, c - 0.1, c, 5000)
        for i, c in enumerate(closes)
    ]


def test_folds_strictly_temporal_and_no_leakage():
    bars = history()
    result = evaluate_rolling_holdout(bars, warmup=120, window=60)
    assert result["status"] == "EXPERIMENTAL_HOLDOUT_NOT_INVESTMENT_VALIDATION"
    assert result["fold_count"] == 3
    folds = result["folds"]
    assert folds[0]["train_end"] < folds[0]["test_start"] <= folds[0]["test_end"]
    for a, b in zip(folds, folds[1:]):
        assert a["test_end"] < b["test_start"]
    assert result["aggregate_win_rate"] is None
    assert result["closed_trade_count"] == 0


def test_future_bars_cannot_change_prior_holdout():
    bars = history(360)
    first = evaluate_rolling_holdout(bars[:240], warmup=120, window=60)
    full = evaluate_rolling_holdout(bars, warmup=120, window=60)
    assert first["folds"] == full["folds"][:2]


def test_no_in_sample_trade_leaks_into_evaluation():
    bars = history()
    # Fixed start beyond final available entry session: any prior signals must be skipped.
    report = research_backtest(bars, signal_start=bars[-1].date)
    assert report["trade_count"] == 0
    assert report["signal_start"] == bars[-1].date


def test_validation_and_roundtrip(tmp_path):
    bars = history(240)
    path = tmp_path / "x.csv"
    save_csv(bars, path)
    report = evaluate_file(path, warmup=120, window=60)
    assert report["fold_count"] == 2
    with pytest.raises(ValueError, match="INVALID_EVALUATION_WINDOW"):
        evaluate_rolling_holdout(bars, warmup=10)
    with pytest.raises(ValueError, match="INSUFFICIENT_DATA_FOR_HOLDOUT"):
        evaluate_rolling_holdout(bars[:125], warmup=120, window=60)
    with pytest.raises(ValueError, match="INVALID_SIGNAL_START"):
        research_backtest(bars, signal_start="tomorrow")


def test_nonoverlap_of_executed_trades():
    # If a signal occurs, executions must be in that fold's available future.
    bars = history(300)
    result = evaluate_rolling_holdout(bars, warmup=120, window=60)
    for f in result["folds"]:
        for trade in f["trades"]:
            assert f["test_start"] <= trade["signal_date"]
            assert f["test_start"] < trade["entry_date"]
            assert trade["exit_date"] <= f["test_end"]
