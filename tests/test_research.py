from datetime import date, timedelta

import pytest

from alpha_lab.data import Bar, validate_bars
from alpha_lab.strategy import detect
from alpha_lab.backtest import research_backtest, Assumptions
from alpha_lab.intelligence import parse_feed, append_unique


def bars_for_test():
    start = date(2025, 1, 1)
    closes = [10 + index * 0.05 for index in range(85)]
    # Recent pullback (from the 10-session high) and first recovery candle.
    closes.extend([13.80, 13.62, 13.45, 13.63])
    bars = []
    for i, close in enumerate(closes):
        bars.append(Bar(
            "600519", (start + timedelta(days=i)).isoformat(),
            close - 0.04, close + 0.10, close - 0.12, close, 10000,
        ))
    return bars


def test_signal_uses_only_known_bars():
    bars = bars_for_test()
    assert detect(bars) is not None
    assert detect(bars[:-1]) is None
    assert detect(bars[:40]) is None


def test_bad_data_fails_closed():
    bars = bars_for_test()
    with pytest.raises(ValueError, match="OUT_OF_ORDER"):
        validate_bars(bars + [bars[-1]])
    with pytest.raises(ValueError, match="INVALID_OHLC"):
        validate_bars([Bar("600519", "2025-01-01", 10, 9, 8, 10, 1)])


def test_research_has_no_fabricated_buy_or_return():
    report = research_backtest(bars_for_test())
    assert report["status"] == "RESEARCH_ONLY_NOT_VALIDATED"
    assert report["symbol"] == "600519"
    assert report["win_rate"] is None or 0 <= report["win_rate"] <= 1
    assert "no_out_of_sample_validation" in report["limitations"]


def test_t_plus_one_exit_and_round_lots():
    bars = bars_for_test()
    last = bars[-1]
    # A next-session entry and a following-session rally.
    entry = Bar(last.symbol, (date.fromisoformat(last.date) + timedelta(days=1)).isoformat(),
                last.close, last.close + 0.2, last.close - 0.2, last.close, 10000)
    exit_bar = Bar(last.symbol, (date.fromisoformat(last.date) + timedelta(days=2)).isoformat(),
                   last.close * 1.06, last.close * 1.08, last.close * 1.04, last.close * 1.06, 10000)
    report = research_backtest(bars + [entry, exit_bar], Assumptions())
    assert report["trade_count"] == 1
    assert report["trades"][0]["reason"] == "TARGET"
    for trade in report["trades"]:
        assert trade["entry_date"] < trade["exit_date"]
        assert trade["shares"] % 100 == 0


def test_feed_provenance_and_dedup(tmp_path):
    xml = b"<rss><channel><item><title>Notice A</title><link>https://example.com/a</link><pubDate>Tue, 20 Oct 2026 03:00:00 GMT</pubDate></item></channel></rss>"
    events = parse_feed(xml, "https://example.com/feed.xml", "2026-10-23T00:00:00+00:00")
    assert len(events) == 1
    assert events[0]["research_status"] == "UNVERIFIED"
    assert events[0]["retrieved_at"]
    path = tmp_path / "news.jsonl"
    assert append_unique(events, path) == 1
    assert append_unique(events, path) == 0


def test_nan_is_rejected():
    bars = bars_for_test()
    with pytest.raises(ValueError, match="NONFINITE_DATA"):
        validate_bars([Bar("600519", "2025-01-01", 10, 11, 9, float("nan"), 100)])


def test_duplicate_news_in_single_batch(tmp_path):
    xml = b"<rss><channel><item><title>A</title><link>https://example.com/x</link></item></channel></rss>"
    event = parse_feed(xml, "https://example.com/rss", "2026-10-23T00:00:00+00:00")[0]
    assert append_unique([event, event], tmp_path / "events.jsonl") == 1
