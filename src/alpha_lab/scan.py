"""Offline, fail-closed multi-symbol research scan from user-supplied CSV data.

This module does NOT verify corporate actions, market-wide coverage, fundamentals,
liquidity or investment suitability. WATCH_SIGNAL is never a live BUY instruction.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

from .data import Bar, load_csv, validate_bars
from .strategy import detect


STATUS_ORDER = {"WATCH_SIGNAL": 0, "WAIT_PRICE": 1, "REJECT": 2}
LIMITATIONS = [
    "unadjusted_history_corporate_actions_unhandled",
    "point_in_time_universe_and_ST_status_unverified",
    "no_fundamentals_valuation_or_liquidity_screen",
    "calendar_age_not_exchange_trading_calendar",
    "technical_signal_not_out_of_sample_validated",
    "no_real_time_quotes_or_order_execution",
]


def _rejected(source: str, reason: str, symbol: str | None = None,
              latest_date: str | None = None) -> dict:
    return {
        "symbol": symbol,
        "source": source,
        "latest_date": latest_date,
        "status": "REJECT",
        "reason": reason,
        "evidence": {},
        "signal_reference": None,
    }


def analyze_bars(bars: list[Bar], *, source: str, asof: date,
                 max_age_days: int = 5) -> dict:
    """Analyze one validated history, without using bars beyond the as-of date."""
    validate_bars(bars)
    last = bars[-1]
    last_day = date.fromisoformat(last.date)
    if last_day > asof:
        return _rejected(source, "FUTURE_DATA_AFTER_ASOF", last.symbol, last.date)
    age = (asof - last_day).days
    if age > max_age_days:
        return _rejected(source, "STALE_DATA", last.symbol, last.date)
    if len(bars) < 65:
        return _rejected(source, "INSUFFICIENT_BARS_MIN_65", last.symbol, last.date)
    if any(bar.volume <= 0 for bar in bars[-5:]):
        return _rejected(source, "RECENT_ZERO_VOLUME", last.symbol, last.date)

    closes = [bar.close for bar in bars]
    ma20 = sum(closes[-20:]) / 20
    ma60 = sum(closes[-60:]) / 60
    past_ma60 = sum(closes[-65:-5]) / 60
    high10 = max(bar.high for bar in bars[-10:])
    deviation_pct = 100 * (last.close / ma20 - 1)
    pullback_pct = 100 * (high10 - last.close) / high10
    evidence = {
        "close": round(last.close, 4),
        "ma20": round(ma20, 4),
        "ma60": round(ma60, 4),
        "ma60_five_sessions_ago": round(past_ma60, 4),
        "ma20_deviation_pct": round(deviation_pct, 3),
        "high10_pullback_pct": round(pullback_pct, 3),
        "last_session_change_pct": round(100 * (last.close / bars[-2].close - 1), 3),
        "last_volume": last.volume,
        "age_calendar_days": age,
        "observed_bars": len(bars),
    }
    signal = detect(bars)
    if signal:
        status, reason = "WATCH_SIGNAL", "TECHNICAL_HYPOTHESIS_MATCH"
        reference = {
            "asof": signal.asof,
            "reference_close": signal.reference_close,
            "research_lower": signal.lower,
            "research_upper": signal.upper,
        }
    elif ma20 > ma60 > past_ma60 and abs(deviation_pct) <= 5:
        status, reason = "WAIT_PRICE", "RISING_TREND_NEAR_MA20_NO_ENTRY_CONFIRMATION"
        reference = None
    else:
        status, reason = "REJECT", "NO_CURRENT_TECHNICAL_SETUP"
        reference = None
    return {
        "symbol": last.symbol,
        "source": source,
        "latest_date": last.date,
        "status": status,
        "reason": reason,
        "evidence": evidence,
        "signal_reference": reference,
    }


def scan_directory(directory: str | Path, *, asof: str,
                   max_age_days: int = 5) -> dict:
    """Create one canonical report. Invalid symbols/files do not silently disappear."""
    try:
        asof_day = date.fromisoformat(asof)
        if asof_day.isoformat() != asof:
            raise ValueError
    except ValueError as exc:
        raise ValueError("ASOF_MUST_BE_ISO_DATE") from exc
    if max_age_days < 0:
        raise ValueError("MAX_AGE_DAYS_MUST_BE_NONNEGATIVE")
    root = Path(directory)
    if not root.is_dir():
        raise ValueError("INPUT_DIRECTORY_NOT_FOUND")
    csvs = sorted(root.glob("*.csv"))
    if not csvs:
        raise ValueError("NO_CSV_FILES_FOUND")

    histories: list[tuple[str, list[Bar]]] = []
    records: list[dict] = []
    for path in csvs:
        try:
            histories.append((path.name, load_csv(path)))
        except (OSError, UnicodeError, ValueError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) else "CSV_READ_ERROR"
            records.append(_rejected(path.name, "DATA_ERROR:" + reason[:120]))

    symbol_counts = Counter(bars[0].symbol for _, bars in histories)
    for source, bars in histories:
        if symbol_counts[bars[0].symbol] > 1:
            records.append(_rejected(source, "DUPLICATE_SYMBOL_IN_INPUT",
                                     bars[0].symbol, bars[-1].date))
        else:
            records.append(analyze_bars(bars, source=source,
                                        asof=asof_day, max_age_days=max_age_days))
    records.sort(key=lambda r: (
        STATUS_ORDER[r["status"]],
        r["symbol"] or "999999",
        r["source"],
    ))
    counts = {key: sum(r["status"] == key for r in records) for key in STATUS_ORDER}
    return {
        "schema_version": "0.2",
        "status": "RESEARCH_ONLY_NOT_VALIDATED",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "asof": asof,
        "source_type": "LOCAL_UNADJUSTED_CSV",
        "max_age_calendar_days": max_age_days,
        "scanned_files": len(csvs),
        "status_counts": counts,
        "records": records,
        "limitations": LIMITATIONS.copy(),
    }


def render_dashboard(report: dict) -> str:
    """Human-readable view of the *same* canonical JSON report, no recalculation."""
    counts = report["status_counts"]
    out = [
        "# A-Share Alpha Lab | Research Dashboard",
        "",
        f'As-of: **{report["asof"]}** · Generated (UTC): {report["generated_at_utc"]}',
        "",
        "**RESEARCH ONLY — NO VERIFIED BUY SIGNALS OR BROKER ORDERS.**",
        "",
        (f'Files: {report["scanned_files"]} · Watch signals: {counts["WATCH_SIGNAL"]}'
         f' · Wait: {counts["WAIT_PRICE"]} · Rejected: {counts["REJECT"]}'),
        "",
        "| Code | State | Last data | Close | MA20 | MA60 | Reason |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for item in report["records"]:
        e = item["evidence"]
        clean = lambda v: str(v).replace("|", "/").replace("\n", " ")
        out.append("| " + " | ".join([
            clean(item["symbol"] or item["source"]),
            clean(item["status"]),
            clean(item["latest_date"] or "—"),
            clean(e.get("close", "—")),
            clean(e.get("ma20", "—")),
            clean(e.get("ma60", "—")),
            clean(item["reason"]),
        ]) + " |")
    out += ["", "## Data and model limits", ""]
    out.extend("- " + item for item in report["limitations"])
    out += ["", "WATCH_SIGNAL means the experimental technical hypothesis matched, "
            "not that valuation, business fundamentals, or tradability passed review.", ""]
    return "\n".join(out)
