"""The real holdings cockpit must never confuse hypothetical P&L with a user's account."""
import json
from datetime import date, timedelta

import pytest

from alpha_lab.data import Bar, save_csv
from alpha_lab.portfolio import PortfolioRules, simulate_portfolio
from alpha_lab.cockpit import build_cockpit
from alpha_lab.html_dashboard import render_html
from alpha_lab.pipeline import run_local_pipeline
from alpha_lab.scan import scan_directory


def bars():
    start = date(2025, 1, 1)
    prices = [10 + i*.05 for i in range(85)]
    prices += [13.80, 13.62, 13.45, 13.63]
    return [Bar("600519", (start+timedelta(days=i)).isoformat(),
                close-.04, close+.10, close-.12, close, 10000)
            for i,close in enumerate(prices)]


def test_one_command_archive_includes_experiment_but_not_real_account_pnl(tmp_path):
    prices = tmp_path / "prices"
    prices.mkdir()
    history = bars()
    save_csv(history, prices / "600519.csv")
    latest = history[-1].date
    positions = tmp_path / "holdings.json"
    positions.write_text(json.dumps({"asof": latest, "cash": 1000,
        "positions": [{"symbol": "600519", "shares": 100,
                       "cost_basis_per_share": 10.0}]}), encoding="utf-8")
    target = tmp_path / "output" / latest
    report = run_local_pipeline(input_dir=prices, asof=latest,
        holdings_path=positions, out_dir=target,
        portfolio_first_trade_date=history[65].date, portfolio_starting_cash=10000)
    assert "portfolio_research.json" in report["files"]
    cockpit = json.loads((target / "cockpit.json").read_text(encoding="utf-8"))
    assert cockpit["portfolio_experiment"]["status"] == "HYPOTHETICAL_RESEARCH_NOT_REAL_HOLDINGS"
    assert cockpit["summary"]["cash_from_user_input"] == 1000
    assert cockpit["portfolio_experiment"]["metrics"]["starting_equity"] == 10000
    assert cockpit["summary"]["portfolio_marked_value_excluding_fees"] != 10000
    html = (target / "cockpit.html").read_text(encoding="utf-8")
    assert "历史模拟组合研究" in html
    assert "不是实际持仓" in html
    assert "aria-label='历史假设权益变化曲线" in html
    assert "投资研究驾驶舱" in html


def test_bad_future_research_or_forged_equity_is_rejected(tmp_path):
    prices = tmp_path / "prices"
    prices.mkdir()
    history = bars()
    save_csv(history, prices/"600519.csv")
    asof = history[-1].date
    scan = scan_directory(prices, asof=asof)
    holdings = {"asof": asof, "cash": 0, "positions": []}
    historical = simulate_portfolio({"600519": history},
        PortfolioRules(first_trade_date=history[65].date))
    bad = {**historical, "last_session": "2099-01-01"}
    with pytest.raises(ValueError, match="HYPOTHETICAL_PORTFOLIO_ASOF_MISMATCH"):
        build_cockpit(scan, holdings, historical_portfolio=bad)
    bad_equity = {**historical, "metrics": {**historical["metrics"],
                  "ending_equity_marked": 1}}
    with pytest.raises(ValueError, match="INVALID_HYPOTHETICAL_PORTFOLIO_EQUITY"):
        build_cockpit(scan, holdings, historical_portfolio=bad_equity)


def test_no_historical_research_is_visibly_not_reported(tmp_path):
    prices = tmp_path / "prices"
    prices.mkdir()
    history = bars()
    save_csv(history, prices/"600519.csv")
    asof = history[-1].date
    cockpit = build_cockpit(scan_directory(prices, asof=asof),
        {"asof": asof, "cash": 0, "positions": []})
    assert cockpit["portfolio_experiment"] is None
    assert "历史模拟组合研究" not in render_html(cockpit)


def test_history_report_must_end_at_snapshot_asof(tmp_path):
    prices = tmp_path / "prices"
    prices.mkdir()
    history = bars()
    save_csv(history, prices / "600519.csv")
    holdings = tmp_path / "hold.json"
    holdings.write_text(json.dumps({"asof": "2025-04-01",
        "cash": 0, "positions": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="HOLDINGS_ASOF_MISMATCH"):
        run_local_pipeline(input_dir=prices, holdings_path=holdings,
            asof=history[-1].date, out_dir=tmp_path/"snap",
            portfolio_first_trade_date=history[65].date)
    assert not (tmp_path/"snap").exists()
