import json
import math

import pytest

from alpha_lab.cockpit import build_cockpit, render_cockpit, build_from_files


def scan(asof="2026-10-28", status="WATCH_SIGNAL", valid=True):
    evidence = {"close": 10.5, "age_calendar_days": 0} if valid else {}
    return {
        "status": "RESEARCH_ONLY_NOT_VALIDATED",
        "asof": asof,
        "max_age_calendar_days": 5,
        "records": [{
            "symbol": "600519", "status": status, "reason":
            "TECHNICAL_HYPOTHESIS_MATCH" if status == "WATCH_SIGNAL"
            else "NO_CURRENT_TECHNICAL_SETUP",
            "evidence": evidence, "source": "600519.csv", "latest_date": asof,
        }],
    }


def holdings(asof="2026-10-28", positions=None, cash=1000):
    return {
        "asof": asof, "cash": cash,
        "positions": positions if positions is not None else [
            {"symbol": "600519", "shares": 100, "cost_basis_per_share": 10}],
    }


def test_holdings_and_candidates_are_auditable():
    result = build_cockpit(scan(), holdings())
    assert result["status"] == "RESEARCH_COCKPIT"
    assert result["investment_decision_status"].startswith("HUMAN_REVIEW")
    assert result["summary"]["portfolio_marked_value_excluding_fees"] == 2050
    assert result["summary"]["portfolio_unrealized_pnl_excluding_fees"] == 50
    assert result["candidates"][0]["first_seen_asof"] == "2026-10-28"
    assert "PRIVATE" not in render_cockpit(result).upper() or "do not commit" in render_cockpit(result)


def test_persistent_candidate_not_silently_discarded():
    first = build_cockpit(scan(), holdings())
    second = build_cockpit(scan("2026-10-29", "REJECT"),
                           holdings("2026-10-29"), previous=first)
    assert second["candidates"][0]["first_seen_asof"] == "2026-10-28"
    assert second["candidates"][0]["research_state"] == "DORMANT_NO_CURRENT_SETUP"


def test_missing_quote_does_not_create_false_portfolio_value():
    positions = [
        {"symbol": "600519", "shares": 100, "cost_basis_per_share": 10},
        {"symbol": "000001", "shares": 200, "cost_basis_per_share": 20},
    ]
    result = build_cockpit(scan(), holdings(positions=positions))
    assert result["summary"]["unvalued_positions"] == 1
    assert result["summary"]["portfolio_marked_value_excluding_fees"] is None
    assert result["summary"]["portfolio_unrealized_pnl_excluding_fees"] is None
    assert all(p["portfolio_weight_pct"] is None for p in result["holdings"])
    assert result["holdings"][0]["research_action"] == "REVIEW_DATA_MISSING"


def test_invalid_and_future_inputs_rejected():
    with pytest.raises(ValueError, match="HOLDINGS_ASOF_MISMATCH"):
        build_cockpit(scan(), holdings("2026-10-29"))
    with pytest.raises(ValueError, match="INVALID_OR_DUPLICATE_HOLDING"):
        build_cockpit(scan(), holdings(positions=[
            {"symbol": "600519", "shares": True, "cost_basis_per_share": 10}]))
    with pytest.raises(ValueError, match="INVALID_HOLDINGS_SCHEMA"):
        build_cockpit(scan(), holdings(cash=float("nan")))
    first = build_cockpit(scan(), holdings())
    with pytest.raises(ValueError, match="PREVIOUS_REPORT_FROM_FUTURE"):
        build_cockpit(scan("2026-10-27"), holdings("2026-10-27"), first)


def test_duplicate_market_symbol_blocks_valuation():
    s = scan()
    s["records"].append(dict(s["records"][0]))
    report = build_cockpit(s, holdings())
    assert report["summary"]["unvalued_positions"] == 1


def test_concentration_warning():
    x = build_cockpit(scan(), holdings(cash=0))
    assert x["summary"]["concentration_30pct_flag"] == "REVIEW_SINGLE_POSITION_OVER_30_PCT"
    assert x["holdings"][0]["portfolio_weight_pct"] == 100.0


def test_file_interface(tmp_path):
    one = tmp_path / "scan.json"
    two = tmp_path / "holdings.json"
    one.write_text(json.dumps(scan()), encoding="utf-8")
    two.write_text(json.dumps(holdings()), encoding="utf-8")
    result = build_from_files(one, two)
    assert result["asof"] == "2026-10-28"
