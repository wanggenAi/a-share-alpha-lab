from datetime import date, timedelta

import pytest

from alpha_lab.data import Bar, save_csv
from alpha_lab.scan import analyze_bars, render_dashboard, scan_directory


def sample_bars(symbol="600519"):
    start = date(2025, 1, 1)
    closes = [10 + i * 0.05 for i in range(85)]
    closes.extend([13.80, 13.62, 13.45, 13.63])
    return [
        Bar(symbol, (start + timedelta(days=i)).isoformat(),
            close - 0.04, close + 0.10, close - 0.12, close, 10000)
        for i, close in enumerate(closes)
    ]


def test_scan_watch_signal_and_dashboard(tmp_path):
    bars = sample_bars()
    save_csv(bars, tmp_path / "600519.csv")
    report = scan_directory(tmp_path, asof=bars[-1].date)
    assert report["status"] == "RESEARCH_ONLY_NOT_VALIDATED"
    assert report["scanned_files"] == 1
    assert report["status_counts"]["WATCH_SIGNAL"] == 1
    entry = report["records"][0]
    assert entry["signal_reference"]["asof"] == bars[-1].date
    text = render_dashboard(report)
    assert "600519" in text and "NO VERIFIED BUY" in text


def test_stale_and_future_data_fail_closed(tmp_path):
    bars = sample_bars()
    save_csv(bars, tmp_path / "one.csv")
    stale = scan_directory(tmp_path, asof=(date.fromisoformat(bars[-1].date)
                           + timedelta(days=6)).isoformat())
    assert stale["records"][0]["reason"] == "STALE_DATA"
    future = scan_directory(tmp_path, asof=bars[-2].date)
    assert future["records"][0]["reason"] == "FUTURE_DATA_AFTER_ASOF"


def test_invalid_and_duplicate_files_explicitly_rejected(tmp_path):
    bars = sample_bars()
    save_csv(bars, tmp_path / "a.csv")
    save_csv(bars, tmp_path / "b.csv")
    (tmp_path / "bad.csv").write_text("invalid,data\nx,y\n", encoding="utf-8")
    report = scan_directory(tmp_path, asof=bars[-1].date)
    assert report["status_counts"]["REJECT"] == 3
    assert sum(row["reason"] == "DUPLICATE_SYMBOL_IN_INPUT"
               for row in report["records"]) == 2
    assert any(row["reason"].startswith("DATA_ERROR:") for row in report["records"])


def test_insufficient_bars_and_zero_volume():
    bars = sample_bars()
    asof = date.fromisoformat(bars[-1].date)
    short = analyze_bars(bars[:60], source="short.csv",
                         asof=date.fromisoformat(bars[59].date))
    assert short["reason"] == "INSUFFICIENT_BARS_MIN_65"
    last = bars[-1]
    zero = bars[:-1] + [Bar(last.symbol, last.date, last.open, last.high,
                             last.low, last.close, 0)]
    assert analyze_bars(zero, source="zero.csv", asof=asof)["reason"] == "RECENT_ZERO_VOLUME"


def test_bad_options_fail_closed(tmp_path):
    with pytest.raises(ValueError, match="NO_CSV"):
        scan_directory(tmp_path, asof="2026-10-28")
    with pytest.raises(ValueError, match="ASOF_MUST"):
        scan_directory(tmp_path, asof="28/10/2026")
    with pytest.raises(ValueError, match="MAX_AGE"):
        scan_directory(tmp_path, asof="2026-10-28", max_age_days=-1)


def test_stable_status_and_provenance_on_no_signal(tmp_path):
    bars = sample_bars()
    changed = bars[:-1] + [Bar(bars[-1].symbol, bars[-1].date,
                              7.0, 7.1, 6.9, 7.0, 10000)]
    save_csv(changed, tmp_path / "x.csv")
    report = scan_directory(tmp_path, asof=changed[-1].date)
    rec = report["records"][0]
    assert rec["status"] == "REJECT"
    assert rec["reason"] == "NO_CURRENT_TECHNICAL_SETUP"
    assert rec["source"] == "x.csv"
