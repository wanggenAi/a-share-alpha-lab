import json
from datetime import date, timedelta

import pytest
from alpha_lab.data import Bar
from tools.manual_public_research import parse_symbols, validate_dates, run_public_research


def fake_fetch(sym, start, end):
    first=date(2025,1,1)
    return [Bar(sym,(first+timedelta(days=i)).isoformat(),
                10,10.2,9.9,10,10000) for i in range(90)]


def test_public_input_sanitization():
    assert parse_symbols("600519, 000001")==["600519","000001"]
    with pytest.raises(ValueError,match="INVALID_PUBLIC_SYMBOLS"):
        parse_symbols("600519; echo secret")
    with pytest.raises(ValueError,match="INVALID_PUBLIC_SYMBOLS"):
        parse_symbols("600519,600519")
    assert validate_dates("20250101","",date(2025,4,1))[1]=="20250401"
    with pytest.raises(ValueError,match="INVALID_OR_FUTURE"):
        validate_dates("20250101","20270101",date(2026,10,28))


def test_public_manual_happy_path(tmp_path):
    dest=tmp_path/"report"
    result=run_public_research(symbols_text="600519",start="20250101",
        end="20250331",confirmed=True,dest=dest,fetcher=fake_fetch,
        sleeper=lambda _:None,today=date(2026,10,28))
    assert result["status"].startswith("PUBLIC_RESEARCH_CREATED")
    assert (dest/"scan.json").is_file()
    assert (dest/"dashboard.html").is_file()
    assert (dest/"prices"/"_ingestion_manifest.json").is_file()
    assert "未连接私人持仓" in (dest/"dashboard.html").read_text(encoding="utf-8")
    assert not any("holdings" in p.name for p in dest.rglob("*"))
    assert json.loads((dest/"scan.json").read_text(encoding="utf-8"))["scanned_files"]==1


def test_consent_precedes_any_network_call(tmp_path):
    calls=[]
    def probe(*args):
        calls.append(args)
        return fake_fetch(*args)
    with pytest.raises(ValueError,match="MANUAL_SOURCE_TERMS"):
        run_public_research(symbols_text="600519",start="20250101",end="20250331",
            confirmed=False,dest=tmp_path/"no",fetcher=probe)
    assert calls==[] and not (tmp_path/"no").exists()


def test_partial_provider_failure_does_not_publish_dashboard(tmp_path):
    def bad(sym,start,end):
        if sym=="000001":
            raise TimeoutError("network error")
        return fake_fetch(sym,start,end)
    dest=tmp_path/"failed"
    with pytest.raises(ValueError,match="PUBLIC_RESEARCH_BLOCKED_INCOMPLETE"):
        run_public_research(symbols_text="600519,000001",start="20250101",
            end="20250331",confirmed=True,dest=dest,fetcher=bad,
            sleeper=lambda _:None,today=date(2026,10,28))
    assert (dest/"prices"/"_ingestion_manifest.json").is_file()
    assert not (dest/"dashboard.html").exists()
