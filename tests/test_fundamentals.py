import pytest

from alpha_lab.fundamentals import research_financial_evidence
from alpha_lab.cockpit import build_cockpit, render_cockpit


def filing(year, published, *, revenue=100, income=20, ocf=25):
    return {
        "symbol": "600519", "fiscal_end": f"{year}-12-31", "period_kind": "FY",
        "published_at": published, "source_url": "https://example.com/filing.pdf",
        "currency": "CNY", "revenue_yuan": revenue,
        "net_income_yuan": income, "operating_cash_flow_yuan": ocf,
        "total_assets_yuan": 500, "total_liabilities_yuan": 200,
        "shareholders_equity_yuan": 300, "shares_outstanding": 100,
    }


def payload(*records):
    return {"schema_version": "1", "records": list(records)}


def mock_scan(asof):
    return {"status": "RESEARCH_ONLY_NOT_VALIDATED", "asof": asof,
            "max_age_calendar_days": 5,
            "records": [{
                "symbol": "600519", "source": "600519.csv",
                "status": "WAIT_PRICE", "reason": "RISING_TREND_NEAR_MA20_NO_ENTRY_CONFIRMATION",
                "evidence": {"close": 12.0, "age_calendar_days": 0},
                "latest_date": asof,
            }]}


def mock_holdings(asof):
    return {"asof": asof, "cash": 100, "positions": [{
        "symbol": "600519", "shares": 100, "cost_basis_per_share": 10,
    }]}


def test_publication_time_not_period_end_prevents_leakage():
    f2024 = filing(2024, "2025-04-01")
    f2025 = filing(2025, "2026-04-01", revenue=110, income=24)
    before = research_financial_evidence(payload(f2024, f2025),
                                         asof="2026-03-31", reference_prices={"600519": 12})
    assert before["600519"]["fiscal_end"] == "2024-12-31"
    after = research_financial_evidence(payload(f2024, f2025),
                                        asof="2026-04-02", reference_prices={"600519": 12})
    x = after["600519"]
    assert x["fiscal_end"] == "2025-12-31"
    assert x["comparable_previous_fiscal_end"] == "2024-12-31"
    assert x["metrics"]["revenue_yoy_pct"] == 10
    assert x["metrics"]["pe_fy_reported_earnings_only"] == 50
    assert x["metrics"]["pb_reported_equity"] == 4


def test_unreleased_only_yields_empty_evidence():
    assert research_financial_evidence(payload(filing(2025, "2026-04-01")),
                                       asof="2026-03-01") == {}


def test_negative_cashflow_flags_and_noncomparable_period():
    item = filing(2025, "2026-03-01", income=15, ocf=-3)
    result = research_financial_evidence(payload(item), asof="2026-03-03")
    e = result["600519"]
    assert "NEGATIVE_REPORTED_OPERATING_CASH_FLOW" in e["risk_flags"]
    assert e["metrics"]["revenue_yoy_pct"] is None
    assert e["metrics"]["pe_fy_reported_earnings_only"] is None


def test_invalid_data_and_duplicate_rejected():
    with pytest.raises(ValueError, match="DUPLICATE_FILING_PERIOD"):
        research_financial_evidence(payload(filing(2025, "2026-03-01"),
                                            filing(2025, "2026-03-02")), asof="2026-03-02")
    bad = filing(2025, "2026-03-01")
    bad["operating_cash_flow_yuan"] = float("nan")
    with pytest.raises(ValueError, match="INVALID_FILING_NUMERIC"):
        research_financial_evidence(payload(bad), asof="2026-03-02")
    wrong = filing(2025, "2026-03-01")
    wrong["fiscal_end"] = "2026-04-01"
    with pytest.raises(ValueError, match="FILING_PUBLISHED_BEFORE"):
        research_financial_evidence(payload(wrong), asof="2026-03-02")


def test_cockpit_unknown_without_financial_evidence():
    c = build_cockpit(mock_scan("2026-10-28"), mock_holdings("2026-10-28"))
    assert c["holdings"][0]["financial_status"] == "UNKNOWN_NO_FILING_INPUT"
    assert c["summary"]["financial_evidence_count"] == 0


def test_cockpit_financial_enrichment_is_declaration_not_verification():
    asof = "2026-04-02"
    evidence = payload(filing(2024, "2025-04-01"),
                       filing(2025, "2026-04-01", revenue=120))
    c = build_cockpit(mock_scan(asof), mock_holdings(asof), fundamentals=evidence)
    assert c["holdings"][0]["financial_status"] == "DECLARED_UNVERIFIED_REVIEW"
    assert c["holdings"][0]["financial_metrics"]["revenue_yoy_pct"] == 20
    assert c["candidates"][0]["financial_status"] == "DECLARED_UNVERIFIED_REVIEW"
    assert "Financial" in render_cockpit(c)
