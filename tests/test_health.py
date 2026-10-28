from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import json

import pytest

from alpha_lab.data import Bar
from alpha_lab.ingestion import batch_ingest
from alpha_lab.health import check_snapshot_health


def fake(sym, start, end):
    d=date(2026,1,1)
    return [
        Bar(sym,(d+timedelta(days=i)).isoformat(),10,10.1,9.9,10,1000)
        for i in range(90)
    ]


def set_up(tmp_path, symbols=None):
    folder=tmp_path/"data"
    batch_ingest(symbols=symbols or ["600519"],start="20260101",end="20260331",
                 out_dir=folder,source_terms_confirmed=True,
                 fetcher=fake,sleeper=lambda s:None)
    return folder


def check(folder, **kwargs):
    return check_snapshot_health(folder,asof="2026-03-31",
        now_utc=datetime(2026,3,31,12,tzinfo=timezone.utc),
        max_fetch_age_hours=24*365,**kwargs)


def test_checked_snapshot_source_and_bar_readiness(tmp_path):
    folder=set_up(tmp_path)
    result=check(folder)
    # Date-relative retrieval is real test-runtime, so a future timestamp
    # is explicitly flagged rather than labeled as fresh.
    assert result["status"]=="BLOCKED_DATA_HEALTH"
    assert any(i["reason"]=="RETRIEVAL_TIMESTAMP_IN_FUTURE" for i in result["issues"])
    # Freeze manifest timestamp at a known past instant to test readiness.
    manifest=folder/"_ingestion_manifest.json"
    m=json.loads(manifest.read_text(encoding="utf-8"))
    m["retrieved_at_utc"]="2026-03-31T11:30:00+00:00"
    manifest.write_text(json.dumps(m),encoding="utf-8")
    result=check(folder)
    assert result["status"]=="READY_FOR_OFFLINE_TECHNICAL_RESEARCH_ONLY"
    assert result["issue_count"]==0
    assert result["records"][0]["last_bar_date"]=="2026-03-31"
    assert result["source_authenticity"]=="NOT_INDEPENDENTLY_VERIFIED"


def test_stale_and_suspended_data_are_reported(tmp_path):
    folder=set_up(tmp_path)
    mfile=folder/"_ingestion_manifest.json"
    m=json.loads(mfile.read_text(encoding="utf-8"))
    m["retrieved_at_utc"]="2026-03-31T11:30:00+00:00"
    mfile.write_text(json.dumps(m),encoding="utf-8")
    result=check_snapshot_health(folder,asof="2026-04-12",
        now_utc=datetime(2026,4,12,12,tzinfo=timezone.utc),
        max_fetch_age_hours=24)
    reasons={i["reason"] for i in result["issues"]}
    assert "STALE_LAST_BAR" in reasons
    assert "BATCH_RETRIEVAL_TOO_OLD" in reasons


def test_tamper_is_not_silently_cleared(tmp_path):
    folder=set_up(tmp_path)
    (folder/"600519.csv").write_text("malicious",encoding="utf-8")
    result=check(folder)
    assert result["status"]=="BLOCKED_DATA_HEALTH"
    assert any(i["reason"]=="INVALID_OR_INCOMPLETE_MANIFEST" for i in result["issues"])


def test_no_manifest_and_empty_directories_block(tmp_path):
    p=tmp_path/"missing"
    r=check(p)
    assert r["status"]=="BLOCKED_DATA_HEALTH"
    why={x["reason"] for x in r["issues"]}
    assert "NO_COMPLETE_HASHED_INGESTION_MANIFEST" in why
    assert "NO_LOCAL_PRICE_FILES" in why


def test_future_data_and_invalid_thresholds(tmp_path):
    folder=set_up(tmp_path)
    result=check_snapshot_health(folder,asof="2026-01-25",
        now_utc=datetime(2026,3,31,12,tzinfo=timezone.utc))
    assert any(x["reason"]=="FUTURE_PRICE_DATA_AFTER_ASOF" for x in result["issues"])
    with pytest.raises(ValueError,match="INVALID_HEALTH_THRESHOLDS"):
        check_snapshot_health(folder,asof="2026-03-31",max_bar_age_days=-1)
