import json
from datetime import date, timedelta

import pytest

from alpha_lab.data import Bar
from alpha_lab.ingestion import batch_ingest, check_ingestion_manifest
from alpha_lab.scan import scan_directory


def fake_loader(symbol, start, end):
    begin = date(2026, 1, 1)
    return [
        Bar(symbol, (begin + timedelta(days=i)).isoformat(),
            10, 11, 9, 10.1, 1000)
        for i in range(90)
    ]


def test_bounded_ingest_complete_manifest_and_scan(tmp_path):
    dest = tmp_path / "prices"
    pauses = []
    result = batch_ingest(
        symbols=["600519", "000001"], start="20260101", end="20261028",
        out_dir=dest, source_terms_confirmed=True,
        delay_seconds=0.5, fetcher=fake_loader, sleeper=pauses.append)
    assert result["status"] == "COMPLETE_UNADJUSTED_RESEARCH_INPUT"
    assert pauses == [0.5]
    manifest = check_ingestion_manifest(dest)
    assert len(manifest["downloaded"]) == 2
    report = scan_directory(dest, asof="2026-03-31")
    assert report["scanned_files"] == 2
    assert report["ingestion_provenance"]["status"] == "COMPLETE_UNADJUSTED_RESEARCH_INPUT"
    with pytest.raises(ValueError, match="INGEST_OUTPUT_ALREADY_EXISTS"):
        batch_ingest(symbols=["600519"], start="20260101", end="20261028",
                     out_dir=dest, source_terms_confirmed=True, fetcher=fake_loader)


def test_partial_download_is_blocked_not_silently_accepted(tmp_path):
    dest = tmp_path / "partial"
    def sometimes_bad(sym, start, end):
        if sym == "000001":
            raise TimeoutError("provider down")
        return fake_loader(sym, start, end)
    report = batch_ingest(symbols=["600519", "000001"],
                          start="20260101", end="20261028",
                          out_dir=dest, source_terms_confirmed=True,
                          delay_seconds=0.5, fetcher=sometimes_bad,
                          sleeper=lambda _: None)
    assert report["status"] == "PARTIAL_BLOCKED"
    assert report["failures"][0]["symbol"] == "000001"
    with pytest.raises(ValueError, match="INCOMPLETE_OR_UNTRUSTED"):
        scan_directory(dest, asof="2026-03-31")


def test_tamper_detected_and_new_csv_not_silently_added(tmp_path):
    dest = tmp_path / "prices"
    batch_ingest(symbols=["600519"], start="20260101", end="20261028",
                 out_dir=dest, source_terms_confirmed=True, fetcher=fake_loader)
    target = dest / "600519.csv"
    target.write_text(target.read_text(encoding="utf-8") + "bad\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA256"):
        check_ingestion_manifest(dest)


def test_unsafe_or_unbounded_requests_rejected_before_network(tmp_path):
    with pytest.raises(ValueError, match="SOURCE_TERMS"):
        batch_ingest(symbols=["600519"], start="20260101", end="20261028",
                     out_dir=tmp_path / "a", fetcher=fake_loader)
    with pytest.raises(ValueError, match="INVALID_OR_DUPLICATE"):
        batch_ingest(symbols=["600519", "600519"], start="20260101", end="20261028",
                     out_dir=tmp_path / "b", fetcher=fake_loader,
                     source_terms_confirmed=True)
    with pytest.raises(ValueError, match="DELAY_SECONDS"):
        batch_ingest(symbols=["600519"], start="20260101", end="20261028",
                     out_dir=tmp_path / "c", fetcher=fake_loader,
                     source_terms_confirmed=True, delay_seconds=0)
    with pytest.raises(ValueError, match="INVALID_INGEST_DATE_RANGE"):
        batch_ingest(symbols=["600519"], start="20269999", end="20261028",
                     out_dir=tmp_path / "d", fetcher=fake_loader,
                     source_terms_confirmed=True)
