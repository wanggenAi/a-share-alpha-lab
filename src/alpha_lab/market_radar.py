"""Benchmark-index technical context from explicit LOCAL as-of data.

Index input files must use the Bar CSV schema, one 6-digit identifier per file.
This is a *technical context proxy*, not an economic cycle forecast or index
total-return benchmark. Index labels and market coverage remain unverified.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path

from .data import load_csv


def build_market_radar(directory: str | Path, *, asof: str,
                       max_age_days: int = 5) -> dict:
    try:
        today = date.fromisoformat(asof)
        if today.isoformat() != asof:
            raise ValueError
    except ValueError as exc:
        raise ValueError("INVALID_MARKET_RADAR_ASOF") from exc
    if max_age_days < 0:
        raise ValueError("INVALID_MARKET_RADAR_MAX_AGE")
    root = Path(directory)
    if not root.is_dir():
        raise ValueError("MARKET_RADAR_DIRECTORY_NOT_FOUND")
    paths = sorted(root.glob("*.csv"))
    if not 1 <= len(paths) <= 10:
        raise ValueError("BENCHMARK_FILE_COUNT_MUST_BE_1_TO_10")
    states = []
    symbols = []
    for path in paths:
        try:
            bars = load_csv(path)
        except (OSError, UnicodeError, ValueError) as exc:
            raise ValueError("INVALID_BENCHMARK_CSV:" + path.name) from exc
        symbol = bars[0].symbol
        symbols.append(symbol)
        last = bars[-1]
        last_day = date.fromisoformat(last.date)
        if last_day > today:
            trend, reason = "DATA_BLOCKED", "FUTURE_BENCHMARK_DATA"
        elif (today - last_day).days > max_age_days:
            trend, reason = "DATA_BLOCKED", "STALE_BENCHMARK_DATA"
        elif len(bars) < 65 or any(b.volume <= 0 for b in bars[-5:]):
            trend, reason = "DATA_BLOCKED", "INSUFFICIENT_OR_ZERO_VOLUME_DATA"
        else:
            closes = [bar.close for bar in bars]
            ma20 = sum(closes[-20:]) / 20
            ma60 = sum(closes[-60:]) / 60
            old_ma60 = sum(closes[-65:-5]) / 60
            if last.close > ma20 > ma60 and ma60 > old_ma60:
                trend, reason = "UP_TREND", "CLOSE_GT_MA20_GT_RISING_MA60"
            elif last.close < ma20 < ma60 and ma60 < old_ma60:
                trend, reason = "DOWN_TREND", "CLOSE_LT_MA20_LT_FALLING_MA60"
            else:
                trend, reason = "MIXED_TREND", "NO_CLEAR_INDEX_TECHNICAL_TREND"
        states.append({
            "symbol": symbol,
            "source": path.name,
            "last_data_date": last.date,
            "trend": trend,
            "reason": reason,
            "reference_close": last.close if trend != "DATA_BLOCKED" else None,
        })
    if any(count != 1 for count in Counter(symbols).values()):
        raise ValueError("DUPLICATE_BENCHMARK_SYMBOL")
    valid = [x for x in states if x["trend"] != "DATA_BLOCKED"]
    up = sum(x["trend"] == "UP_TREND" for x in valid)
    down = sum(x["trend"] == "DOWN_TREND" for x in valid)
    if len(valid) != len(states):
        summary = "INCOMPLETE_BENCHMARK_DATA_NO_AGGREGATE_TREND"
    else:
        summary = f"{up}/{len(valid)}_UP_{down}/{len(valid)}_DOWN_TECHNICAL_INDEX_PROXIES"
    return {
        "schema_version": "0.8",
        "status": "LOCAL_INDEX_TECHNICAL_CONTEXT_ONLY",
        "asof": asof,
        "data_source_verification": "LOCAL_FILES_NOT_INDEPENDENTLY_VERIFIED",
        "technical_summary": summary,
        "indices": states,
        "limitations": [
            "not_a_macroeconomic_or_industry_cycle_forecast",
            "index_identity_and_coverage_not_independently_verified",
            "unadjusted_price_data_not_total_return_series",
            "no_market_breadth_from_the_full_listed_universe",
            "stale_or_future_index_data_blocks_aggregate_signal",
        ],
    }
