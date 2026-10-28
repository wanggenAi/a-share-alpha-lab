import json
from datetime import date, timedelta

import pytest

from alpha_lab.data import Bar, save_csv
from alpha_lab.cockpit import build_cockpit
from alpha_lab.html_dashboard import render_html
from alpha_lab.pipeline import run_local_pipeline


def bars_for_test():
    start = date(2025, 1, 1)
    closes = [10 + i * 0.05 for i in range(85)]
    closes += [13.80, 13.62, 13.45, 13.63]
    return [
        Bar("600519", (start + timedelta(days=i)).isoformat(),
            close - .04, close + .10, close - .12, close, 10000)
        for i, close in enumerate(closes)
    ]


def test_one_command_pipeline_creates_static_snapshot(tmp_path):
    prices = tmp_path / "data"
    prices.mkdir()
    bars = bars_for_test()
    save_csv(bars, prices / "600519.csv")
    holds = tmp_path / "holdings.json"
    asof = bars[-1].date
    holds.write_text(json.dumps({
        "asof": asof, "cash": 1000,
        "positions": [{"symbol": "600519", "shares": 100,
                       "cost_basis_per_share": 10.0}]
    }), encoding="utf-8")
    target = tmp_path / "output" / asof
    done = run_local_pipeline(input_dir=prices, holdings_path=holds, asof=asof,
                              out_dir=target)
    assert done["positions"] == 1
    assert done["status"].startswith("COMPLETED_LOCAL_RESEARCH")
    assert (target / "cockpit.html").exists()
    html = (target / "cockpit.html").read_text(encoding="utf-8")
    assert "<!doctype html>" in html and "A股投资研究驾驶舱" in html
    assert "600519" in html
    assert (target / "cockpit.json").exists()
    with pytest.raises(ValueError, match="SNAPSHOT_TARGET"):
        run_local_pipeline(input_dir=prices, holdings_path=holds, asof=asof,
                           out_dir=target)


def test_html_escapes_untrusted_market_and_financial_text():
    report = build_cockpit({
        "status": "RESEARCH_ONLY_NOT_VALIDATED", "asof": "2026-10-28",
        "max_age_calendar_days": 5,
        "records": [{
            "symbol": "600519", "latest_date": "2026-10-28",
            "status": "WATCH_SIGNAL", "reason": "<script>alert('x')</script>",
            "source": "fake&<.csv",
            "evidence": {"close": 12.0, "age_calendar_days": 0}
        }]
    }, {"asof": "2026-10-28", "cash": 0, "positions": []})
    html = render_html(report)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "fake&amp;&lt;.csv" in html


def test_pipeline_rejects_future_or_mismatched_holdings_without_output(tmp_path):
    prices = tmp_path / "prices"
    prices.mkdir()
    bars = bars_for_test()
    save_csv(bars, prices / "one.csv")
    p = tmp_path / "holdings.json"
    p.write_text(json.dumps({"asof": "2026-10-28", "cash": 0,
                              "positions": []}), encoding="utf-8")
    target = tmp_path / "output"
    with pytest.raises(ValueError, match="HOLDINGS_ASOF_MISMATCH"):
        run_local_pipeline(input_dir=prices, holdings_path=p,
                           asof=bars[-1].date, out_dir=target)
    assert not target.exists()


def test_pipeline_target_cannot_live_inside_price_inputs(tmp_path):
    prices = tmp_path / "prices"
    prices.mkdir()
    hold = tmp_path / "hold.json"
    hold.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="SNAPSHOT_TARGET"):
        run_local_pipeline(input_dir=prices, holdings_path=hold,
                           asof="2026-10-28", out_dir=prices / "output")
