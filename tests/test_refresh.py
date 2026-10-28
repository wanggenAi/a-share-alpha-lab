import json
from dataclasses import replace
from datetime import date, timedelta

import pytest

from alpha_lab.data import Bar, load_csv
from alpha_lab.ingestion import batch_ingest, check_ingestion_manifest
from alpha_lab.refresh import refresh_snapshot
from alpha_lab.scan import scan_directory


def full_series(symbol, start, end):
    base = date(2026,1,1)
    return [
        Bar(symbol, (base+timedelta(days=i)).isoformat(),
            10 + i*.01,10.12+i*.01,9.90+i*.01,10.01+i*.01,1000)
        for i in range(120)
        if start <= (base+timedelta(days=i)).strftime("%Y%m%d") <= end
    ]


def seed(tmp_path, symbols=None):
    previous=tmp_path/"original"
    syms=symbols or ["600519","000001"]
    batch_ingest(symbols=syms, start="20260101",end="20260315",
        out_dir=previous,source_terms_confirmed=True,delay_seconds=.5,
        fetcher=full_series,sleeper=lambda seconds:None)
    return previous


def test_append_and_full_hash_lineage_without_mutating_parent(tmp_path):
    parent=seed(tmp_path)
    old_manifest=(parent/"_ingestion_manifest.json").read_bytes()
    old_csv=(parent/"600519.csv").read_bytes()
    dest=tmp_path/"refresh"
    delays=[]
    report=refresh_snapshot(previous_dir=parent,out_dir=dest,end="20260325",
        source_terms_confirmed=True,delay_seconds=.5,
        fetcher=full_series,sleeper=delays.append)
    assert report["status"]=="COMPLETE_UNADJUSTED_RESEARCH_INPUT"
    assert delays==[.5]
    assert report["refresh_lineage"]["new_sessions_total"]==20
    assert len(load_csv(dest/"600519.csv")) == 84
    assert (parent/"_ingestion_manifest.json").read_bytes()==old_manifest
    assert (parent/"600519.csv").read_bytes()==old_csv
    assert check_ingestion_manifest(dest)["schema_version"]=="0.14"
    assert scan_directory(dest,asof="2026-03-25")["scanned_files"]==2


def test_same_end_revalidates_without_new_bars(tmp_path):
    parent=seed(tmp_path,["600519"])
    d=tmp_path/"same"
    report=refresh_snapshot(previous_dir=parent,out_dir=d,end="20260315",
        source_terms_confirmed=True,fetcher=full_series)
    assert report["status"]=="COMPLETE_UNADJUSTED_RESEARCH_INPUT"
    assert report["refresh_lineage"]["new_sessions_total"]==0
    assert report["downloaded"][0]["refresh_state"].startswith("NO_NEW")


def test_historical_change_fails_closed_and_keeps_audit_manifest(tmp_path):
    parent=seed(tmp_path,["600519"])
    def revised(sym,start,end):
        bars=full_series(sym,start,end)
        bars[0]=replace(bars[0],close=bars[0].close+.001)
        return bars
    dest=tmp_path/"partial"
    report=refresh_snapshot(previous_dir=parent,out_dir=dest,end="20260325",
        source_terms_confirmed=True,fetcher=revised)
    assert report["status"]=="PARTIAL_BLOCKED"
    assert report["failures"][0]["reason"]=="REFRESH_HISTORICAL_REVISION_BLOCKED"
    assert (dest/"_ingestion_manifest.json").exists()
    with pytest.raises(ValueError,match="INCOMPLETE_OR_UNTRUSTED"):
        check_ingestion_manifest(dest)


def test_missing_overlap_fails_not_silent_data_loss(tmp_path):
    parent=seed(tmp_path,["600519"])
    def incomplete(sym,start,end):
        result=full_series(sym,start,end)
        return result[1:]
    r=refresh_snapshot(previous_dir=parent,out_dir=tmp_path/"incomplete",
        end="20260325",source_terms_confirmed=True,fetcher=incomplete)
    assert r["status"]=="PARTIAL_BLOCKED"
    assert r["failures"][0]["reason"]=="REFRESH_OVERLAP_MISSING_OR_CHANGED_DATES"


def test_tampered_parent_and_no_consents_block_before_network(tmp_path):
    parent=seed(tmp_path,["600519"])
    calls=[]
    def probe(*args):
        calls.append(args)
        return full_series(*args)
    with pytest.raises(ValueError,match="SOURCE_TERMS_CONFIRMATION_REQUIRED"):
        refresh_snapshot(previous_dir=parent,out_dir=tmp_path/"no",
            end="20260325",fetcher=probe)
    assert calls==[]
    with pytest.raises(ValueError,match="REFRESH_END_BEFORE_EXISTING_LATEST_BAR"):
        refresh_snapshot(previous_dir=parent,out_dir=tmp_path/"earlier",
            end="20260101",source_terms_confirmed=True,fetcher=probe)
    assert calls==[]
    (parent/"600519.csv").write_text("unverified override",encoding="utf-8")
    with pytest.raises(ValueError,match="INGESTION_SHA256_MISMATCH"):
        refresh_snapshot(previous_dir=parent,out_dir=tmp_path/"tampered",
            end="20260325",source_terms_confirmed=True,fetcher=probe)
    assert calls==[]


def test_overwrite_and_nested_snapshots_rejected(tmp_path):
    parent=seed(tmp_path,["600519"])
    with pytest.raises(ValueError,match="REFRESH_OUTPUT_MUST_BE_NEW_AND_SEPARATE"):
        refresh_snapshot(previous_dir=parent,out_dir=parent/"child",
            end="20260325",source_terms_confirmed=True,fetcher=full_series)
    with pytest.raises(ValueError,match="REFRESH_OUTPUT_MUST_BE_NEW_AND_SEPARATE"):
        refresh_snapshot(previous_dir=parent,out_dir=parent,
            end="20260325",source_terms_confirmed=True,fetcher=full_series)
