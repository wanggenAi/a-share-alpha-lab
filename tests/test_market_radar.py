from datetime import date, timedelta

import pytest

from alpha_lab.data import Bar, save_csv
from alpha_lab.market_radar import build_market_radar
from alpha_lab.cockpit import build_cockpit


def index_bars(symbol, rising=True):
    start = date(2026, 1, 1)
    closes = [10 + i * .025 if rising else 20 - i * .025 for i in range(100)]
    return [Bar(symbol, (start + timedelta(days=i)).isoformat(),
                c - .03, c + .10, c - .10, c, 10000)
            for i, c in enumerate(closes)]


def test_market_index_context_up_down(tmp_path):
    up = index_bars("000300")
    down = index_bars("000905", rising=False)
    save_csv(up, tmp_path / "index1.csv")
    save_csv(down, tmp_path / "index2.csv")
    report = build_market_radar(tmp_path, asof=up[-1].date)
    assert report["status"] == "LOCAL_INDEX_TECHNICAL_CONTEXT_ONLY"
    assert {r["trend"] for r in report["indices"]} == {"UP_TREND", "DOWN_TREND"}
    assert "1/2_UP_1/2_DOWN" in report["technical_summary"]


def test_partial_stale_benchmark_blocks_aggregate(tmp_path):
    up = index_bars("000300")
    save_csv(up, tmp_path / "index.csv")
    report = build_market_radar(tmp_path,
                                asof=(date.fromisoformat(up[-1].date) +
                                      timedelta(days=6)).isoformat())
    assert report["technical_summary"] == "INCOMPLETE_BENCHMARK_DATA_NO_AGGREGATE_TREND"
    assert report["indices"][0]["reference_close"] is None


def test_duplicate_or_invalid_benchmark_refused(tmp_path):
    up = index_bars("000300")
    save_csv(up, tmp_path / "index1.csv")
    save_csv(up, tmp_path / "index2.csv")
    with pytest.raises(ValueError, match="DUPLICATE_BENCHMARK_SYMBOL"):
        build_market_radar(tmp_path, asof=up[-1].date)
    with pytest.raises(ValueError, match="INVALID_MARKET_RADAR_ASOF"):
        build_market_radar(tmp_path, asof="2026/10/28")


def test_cockpit_index_context_is_optional_and_asof_guarded():
    asof = "2026-10-28"
    scan = {"status": "RESEARCH_ONLY_NOT_VALIDATED", "asof": asof,
            "max_age_calendar_days": 5, "records": []}
    holdings = {"asof": asof, "cash": 0, "positions": []}
    no_context = build_cockpit(scan, holdings)
    assert no_context["summary"]["market_cycle_radar"].startswith("UNAVAILABLE")
    report = {"status": "LOCAL_INDEX_TECHNICAL_CONTEXT_ONLY",
              "asof": asof,
              "technical_summary": "1/1_UP_0/1_DOWN_TECHNICAL_INDEX_PROXIES",
              "indices": [{"symbol": "000300", "source": "index.csv",
                           "trend": "UP_TREND", "last_data_date": asof,
                           "reason": "CLOSE_GT_MA20_GT_RISING_MA60"}]}
    added = build_cockpit(scan, holdings, market_radar=report)
    assert added["summary"]["market_cycle_radar"] == report["technical_summary"]
    assert len(added["market_radar"]["indices"]) == 1
    with pytest.raises(ValueError, match="MARKET_RADAR_ASOF_MISMATCH"):
        build_cockpit(scan, holdings, market_radar={**report, "asof": "2026-10-29"})
