from dataclasses import replace
from datetime import date, timedelta

import pytest

from alpha_lab.data import Bar, save_csv
from alpha_lab.portfolio import PortfolioRules, simulate_portfolio, portfolio_from_directory


def price_series(symbol="600519"):
    start = date(2025, 1, 1)
    closes = [10 + i * .05 for i in range(85)]
    closes += [13.80, 13.62, 13.45, 13.63, 13.64, 14.65, 14.55, 14.50]
    return [Bar(symbol, (start+timedelta(days=i)).isoformat(),
                c-.04, c+.10, c-.12, c, 10000)
            for i,c in enumerate(closes)]


def flat(symbol="000001", count=93):
    start = date(2025,1,1)
    return [Bar(symbol,(start+timedelta(days=i)).isoformat(),
                10, 10.05, 9.95, 10, 10000) for i in range(count)]


def rules(bars):
    return PortfolioRules(starting_cash=20000, max_positions=1,
                          allocation_fraction=.8, first_trade_date=bars[65].date)


def test_double_entry_reconciliation_and_t_plus_one():
    bars = price_series()
    r = simulate_portfolio({"600519":bars, "000001":flat()}, rules(bars))
    assert r["metrics"]["closed_trade_count"] >= 1
    for t in r["trades"]:
        assert t["signal_date"] < t["entry_date"] < t["exit_date"]
        assert t["shares"] % 100 == 0
    for d in r["daily_equity"]:
        assert d["cash"] >= -1e-5
        assert d["equity"] == pytest.approx(d["cash"]+d["market_value"],abs=.001)
        assert d["equity"] == pytest.approx(20000+d["realized_pnl"]+d["unrealized_pnl"],abs=.001)


def test_early_ledger_is_not_changed_by_future_bar():
    bars = price_series()
    short = simulate_portfolio({"600519":bars[:91], "000001":flat(count=91)},rules(bars))
    changed = list(bars)
    last = changed[-1]
    changed[-1] = replace(last, open=14.7, low=14.5, high=14.9, close=14.8)
    future = simulate_portfolio({"600519":changed,"000001":flat()},rules(bars))
    assert short["daily_equity"] == future["daily_equity"][:len(short["daily_equity"])]
    assert short["orders"] == [o for o in future["orders"] if o["date"]<=bars[90].date]


def test_fail_closed_on_missing_sessions_and_wrong_board():
    b = price_series()
    with pytest.raises(ValueError,match="MISALIGNED_SESSION_PANEL"):
        simulate_portfolio({"600519":b,"000001":flat(count=92)},rules(b))
    with pytest.raises(ValueError,match="UNSUPPORTED_OR_MISMATCHED_BOARD"):
        simulate_portfolio({"300001":price_series("300001")},rules(b))
    with pytest.raises(ValueError,match="INVALID_PORTFOLIO_START_DATE"):
        simulate_portfolio({"600519":b},PortfolioRules(first_trade_date="no"))


def test_unverified_jump_or_zero_volume_movement_blocked():
    b = price_series()
    changed = list(b)
    x = changed[70]
    changed[70] = replace(x,open=x.open*1.35,high=x.high*1.35,
                          low=x.low*1.35,close=x.close*1.35)
    with pytest.raises(ValueError,match="PRICE_LIMIT_OR_CORPORATE_ACTION"):
        simulate_portfolio({"600519":changed},rules(b))
    stopped = list(b)
    stopped[69] = replace(stopped[69],volume=0)
    with pytest.raises(ValueError,match="ZERO_VOLUME_BAR_WITH_PRICE_MOVEMENT"):
        simulate_portfolio({"600519":stopped},rules(b))


def test_lot_and_fee_gate():
    b = price_series()
    r = simulate_portfolio({"600519":b},
        PortfolioRules(starting_cash=30, allocation_fraction=1,
                       first_trade_date=b[65].date))
    assert r["trades"] == []
    assert r["metrics"]["ending_equity_marked"] == 30
    assert any(o["reason"]=="INSUFFICIENT_CASH_FOR_LOT_AND_FEES" for o in r["orders"])


def test_block_halted_and_one_price_limit_up_entries():
    b = price_series()
    prev = b[88].close
    b[89] = Bar("600519",b[89].date,prev,prev,prev,prev,0)
    r = simulate_portfolio({"600519":b},rules(b))
    assert any(o["reason"]=="HALT_OR_ZERO_VOLUME" for o in r["orders"])
    limit=round(prev*1.1,2)
    b[89] = Bar("600519",b[89].date,limit,limit,limit,limit,10000)
    r2 = simulate_portfolio({"600519":b},rules(b))
    assert any(o["reason"]=="ONE_PRICE_LIMIT_UP" for o in r2["orders"])


def test_unverified_manifest_and_benchmark_reference(tmp_path):
    b=price_series()
    folder=tmp_path/"prices"
    folder.mkdir()
    save_csv(b,folder/"600519.csv")
    r=portfolio_from_directory(folder,rules(b))
    assert r["input_provenance"]["status"]=="UNMANAGED_USER_CSV_UNVERIFIED"
    r2=simulate_portfolio({"600519":b},rules(b),benchmark=flat("000300"))
    assert r2["benchmark_price_reference"]["not_investable_or_total_return_comparison"]
    with pytest.raises(ValueError,match="BENCHMARK_CALENDAR_NOT_ALIGNED"):
        simulate_portfolio({"600519":b},rules(b),benchmark=flat("000300",count=92))
