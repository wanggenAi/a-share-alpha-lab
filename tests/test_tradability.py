import json
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest
from alpha_lab.data import Bar, save_csv
from alpha_lab.tradability import audit_eligibility, require_eligible_histories
from alpha_lab.portfolio import PortfolioRules, portfolio_from_directory


def bars(symbol="600519", n=75):
    d=date(2025, 1, 1)
    return [Bar(symbol,(d+timedelta(days=i)).isoformat(),
                10,10.1,9.9,10,1000) for i in range(n)]


def ledger(histories):
    return {"schema_version": "1", "sessions": [{
        "symbol": symbol, "date": b.date, "state": "REGULAR",
        "corporate_action": "NONE_DECLARED",
        "observed_at": b.date + "T09:00:00+08:00",
        "source_url": "https://example.com/synthetic-issuer-status"
    } for symbol, bs in histories.items() for b in bs]}


def test_strict_full_session_coverage_and_pass(tmp_path):
    h={"600519": bars()}
    f=tmp_path/"eligibility.json"
    f.write_text(json.dumps(ledger(h)),encoding="utf-8")
    a=audit_eligibility(h, ledger(h))
    assert a["status"]=="DECLARED_EVIDENCE_COMPLETE_UNVERIFIED"
    assert a["blocked_sessions"]==0 and a["required_sessions"]==75
    d=tmp_path/"prices"
    d.mkdir()
    save_csv(h["600519"],d/"600519.csv")
    r=portfolio_from_directory(d,PortfolioRules(first_trade_date=h["600519"][65].date),
        eligibility_ledger=f)
    assert r["tradability_evidence"]["status"]=="DECLARED_EVIDENCE_COMPLETE_UNVERIFIED"
    assert r["tradability_evidence"]["source_verification"].startswith("OPERATOR_DECLARED")


def test_missing_ST_halt_and_action_fail_closed(tmp_path):
    h={"600519": bars()}
    l=ledger(h)
    l["sessions"].pop()
    a=audit_eligibility(h,l)
    assert a["blocked_sessions"]==1
    assert a["reason_counts"]["MISSING_STATUS_EVIDENCE"]==1
    l=ledger(h)
    l["sessions"][68]["state"]="ST"
    l["sessions"][69]["state"]="SUSPENDED"
    l["sessions"][70]["corporate_action"]="SPLIT"
    a=audit_eligibility(h,l)
    assert a["blocked_sessions"]==3
    assert a["reason_counts"]["STATUS_NOT_REGULAR"]==2
    assert a["reason_counts"]["UNRESOLVED_CORPORATE_ACTION"]==1
    p=tmp_path/"x.json"
    p.write_text(json.dumps(l),encoding="utf-8")
    with pytest.raises(ValueError,match="PIT_ELIGIBILITY_BLOCKED"):
        require_eligible_histories(h,p)


def test_lookahead_issuance_after_open_is_blocked():
    h={"600519": bars()}
    l=ledger(h)
    l["sessions"][2]["observed_at"]=h["600519"][2].date+"T10:00:00+08:00"
    a=audit_eligibility(h,l)
    assert a["reason_counts"]["NOT_KNOWN_BEFORE_PREOPEN"]==1
    assert a["blocked_sessions"]==1
    # Equal to cutoff is permitted by this conservative dated-evidence schema.
    l["sessions"][2]["observed_at"]=h["600519"][2].date+"T09:15:00+08:00"
    assert audit_eligibility(h,l)["blocked_sessions"]==0


def test_duplicate_future_and_extra_session_metadata_rejected():
    h={"600519":bars()}
    l=ledger(h)
    l["sessions"].append(dict(l["sessions"][0]))
    with pytest.raises(ValueError,match="DUPLICATE_ELIGIBILITY_SESSION"):
        audit_eligibility(h,l)
    l=ledger(h)
    l["sessions"][0]["observed_at"]="2025-01-01T09:00:00"
    with pytest.raises(ValueError,match="OBSERVED_TIMESTAMP_MUST_HAVE_OFFSET"):
        audit_eligibility(h,l)
    l=ledger(h)
    l["sessions"][0]["date"]="2025-12-31"
    with pytest.raises(ValueError,match="UNMATCHED_EXTRA_ELIGIBILITY_SESSIONS"):
        audit_eligibility(h,l)


def test_unverified_source_and_currency_not_assumed():
    h={"600519":bars()}
    l=ledger(h)
    l["sessions"][0]["source_url"]="file:///private/pnl.csv"
    with pytest.raises(ValueError,match="INVALID_ELIGIBILITY_SOURCE_URL"):
        audit_eligibility(h,l)


def test_optional_pit_strict_mode_does_not_claim_proven_provenance(tmp_path):
    h={"600519":bars()}
    p=tmp_path/"prices"
    p.mkdir()
    save_csv(h["600519"],p/"x.csv")
    no_ledger=portfolio_from_directory(p,PortfolioRules(first_trade_date=h["600519"][65].date))
    assert no_ledger["tradability_evidence"]["status"]=="NOT_PROVIDED_UNVERIFIED"
