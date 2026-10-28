from datetime import date, timedelta

import pytest

from alpha_lab.data import Bar, save_csv
from alpha_lab.portfolio_evaluation import (
    evaluate_portfolio_folds, portfolio_folds_from_directory
)


def history(n=320, symbol="600519", rise=True):
    start=date(2024,1,1)
    closes=[10+i*.025 if rise else 20-i*.025 for i in range(n)]
    return [Bar(symbol,(start+timedelta(days=i)).isoformat(),
                c-.02,c+.1,c-.1,c,10000) for i,c in enumerate(closes)]


def test_folds_are_nonoverlapping_and_have_independent_starting_capital():
    bars=history()
    report=evaluate_portfolio_folds({"600519":bars},warmup_sessions=120,
                                    test_sessions=60,starting_cash=8000)
    assert report["fold_count"]==3
    assert report["starting_cash_each_independent_fold"]==8000
    assert report["status"]=="EXPERIMENTAL_PORTFOLIO_TIME_SPLITS_UNVALIDATED"
    for left,right in zip(report["folds"],report["folds"][1:]):
        assert left["last_test_session"] < right["first_test_session"]
    for fold in report["folds"]:
        assert fold["prior_history_last_date"] < fold["first_test_session"]
        assert fold["daily_equity"][0]["date"] == fold["first_test_session"]
        assert fold["daily_equity"][-1]["date"] == fold["last_test_session"]
        assert fold["ending_marked_equity"] == fold["daily_equity"][-1]["equity"]


def test_future_days_cannot_modify_earlier_folds():
    all_bars=history()
    short=evaluate_portfolio_folds({"600519":all_bars[:240]},warmup_sessions=120,
                                   test_sessions=60)
    long=evaluate_portfolio_folds({"600519":all_bars},warmup_sessions=120,
                                  test_sessions=60)
    # generated timestamps excluded; every completed earlier fold identical.
    assert short["folds"] == long["folds"][:2]


def test_invalid_calendar_and_unsupported_lookahead_block():
    a=history()
    b=history(n=319,symbol="000001")
    with pytest.raises(ValueError,match="CALENDAR_MISMATCH"):
        evaluate_portfolio_folds({"600519":a,"000001":b})
    with pytest.raises(ValueError,match="INSUFFICIENT_PORTFOLIO_HOLDOUT_HISTORY"):
        evaluate_portfolio_folds({"600519":a[:200]},warmup_sessions=120,
                                 test_sessions=60)
    with pytest.raises(ValueError,match="INVALID_PORTFOLIO_EVALUATION_WINDOWS"):
        evaluate_portfolio_folds({"600519":a},warmup_sessions=10)


def test_local_file_entrypoint(tmp_path):
    save_csv(history(),tmp_path/"600519.csv")
    report=portfolio_folds_from_directory(tmp_path,warmup_sessions=120,
                                          test_sessions=60)
    assert report["input_provenance"]["status"]=="UNMANAGED_USER_CSV_UNVERIFIED"
    assert report["fold_count"]==3


def test_no_compounded_profit_or_fake_winrate_when_no_signals():
    a=history(300)
    report=evaluate_portfolio_folds({"600519":a},warmup_sessions=120,test_sessions=60)
    assert report["positive_return_fold_count"]==0
    assert report["mean_fold_marked_return_pct_not_compounded"]==0
    assert all(f["trade_count"]==0 for f in report["folds"])
