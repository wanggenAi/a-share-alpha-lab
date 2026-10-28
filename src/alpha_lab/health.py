"""Conservative local snapshot health monitor; provenance is not authentication.

Separate checked, actionable readiness from data-provider success claims.
No live internet calls, no scheduling, no trading and no private holdings.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from math import isfinite
from pathlib import Path

from .data import load_csv
from .ingestion import check_ingestion_manifest

UTC = timezone.utc


def _date(value: str) -> date:
    try:
        d = date.fromisoformat(value)
        if d.isoformat() != value:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_HEALTH_ASOF_DATE") from exc
    return d


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("MISSING_MANIFEST_RETRIEVAL_TIME")
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("INVALID_MANIFEST_RETRIEVAL_TIME") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("MANIFEST_RETRIEVAL_TIME_MUST_HAVE_OFFSET")
    return dt.astimezone(UTC)


def check_snapshot_health(directory: str | Path, *, asof: str,
                          max_bar_age_days: int = 5,
                          max_fetch_age_hours: int = 24,
                          min_bars: int = 65,
                          now_utc: datetime | None = None) -> dict:
    if (type(max_bar_age_days) is not int or max_bar_age_days < 0
            or type(max_fetch_age_hours) is not int or max_fetch_age_hours < 1
            or type(min_bars) is not int or min_bars < 65):
        raise ValueError("INVALID_HEALTH_THRESHOLDS")
    asof_date = _date(asof)
    current = now_utc or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("HEALTH_NOW_REQUIRES_TIMEZONE")
    current = current.astimezone(UTC)
    root = Path(directory)
    flags = []
    manifest = None
    try:
        manifest = check_ingestion_manifest(root)
    except (OSError, ValueError) as exc:
        flags.append({"scope": "batch", "reason": "INVALID_OR_INCOMPLETE_MANIFEST",
                      "details": str(exc)[:140]})
    if manifest is None:
        flags.append({"scope": "batch", "reason": "NO_COMPLETE_HASHED_INGESTION_MANIFEST"})
    files = sorted(root.glob("*.csv")) if root.is_dir() else []
    if not files:
        flags.append({"scope": "batch", "reason": "NO_LOCAL_PRICE_FILES"})
    if manifest is not None:
        try:
            fetched = _timestamp(manifest.get("retrieved_at_utc"))
            if fetched > current + timedelta(minutes=5):
                flags.append({"scope": "batch", "reason": "RETRIEVAL_TIMESTAMP_IN_FUTURE"})
            elif (current - fetched).total_seconds() > 3600 * max_fetch_age_hours:
                flags.append({"scope": "batch", "reason": "BATCH_RETRIEVAL_TOO_OLD"})
        except ValueError as exc:
            flags.append({"scope": "batch", "reason": str(exc)})
    symbols = []
    records = []
    for path in files:
        try:
            bars = load_csv(path)
        except (OSError, UnicodeError, ValueError) as exc:
            flags.append({"scope": path.name, "reason": "INVALID_PRICE_CSV",
                          "details": str(exc)[:140]})
            continue
        symbol = bars[0].symbol
        symbols.append(symbol)
        latest = _date(bars[-1].date)
        age = (asof_date - latest).days
        codes = []
        if age < 0:
            codes.append("FUTURE_PRICE_DATA_AFTER_ASOF")
        if age > max_bar_age_days:
            codes.append("STALE_LAST_BAR")
        if len(bars) < min_bars:
            codes.append("INSUFFICIENT_HISTORY")
        if any(b.volume <= 0 for b in bars[-5:]):
            codes.append("RECENT_SUSPENSION_OR_ZERO_VOLUME")
        for code in codes:
            flags.append({"scope": symbol, "reason": code})
        records.append({
            "symbol": symbol, "file": path.name,
            "first_bar_date": bars[0].date,
            "last_bar_date": bars[-1].date,
            "age_calendar_days": age,
            "observed_bars": len(bars),
            "data_status": "OK_FOR_TECHNICAL_RESEARCH" if not codes else "BLOCKED",
        })
    if any(v > 1 for v in Counter(symbols).values()):
        flags.append({"scope": "batch", "reason": "DUPLICATE_SYMBOL_FILES"})
    last_dates = {r["last_bar_date"] for r in records}
    if len(last_dates) > 1:
        flags.append({"scope": "batch", "reason": "INCONSISTENT_LAST_SESSION_DATES"})
    return {
        "schema_version": "0.15",
        "status": "READY_FOR_OFFLINE_TECHNICAL_RESEARCH_ONLY" if not flags
                  else "BLOCKED_DATA_HEALTH",
        "asof": asof,
        "checked_at_utc": current.isoformat(),
        "requested_symbols": manifest.get("requested_symbols") if manifest else None,
        "has_hash_verified_complete_manifest": manifest is not None,
        "source_authenticity": "NOT_INDEPENDENTLY_VERIFIED",
        "files_checked": len(files),
        "records": records,
        "issue_count": len(flags),
        "issues": flags,
        "limitations": [
            "only_calendar_day_staleness_not_exchange_trading_calendar",
            "SHA256_manifest_integrity_not_provider_authentication",
            "same_last_session_does_not_guarantee_complete_exchange_calendar",
            "no_corporate_action_adjustment_or_point_in_time_ST_status",
            "no_real_time_trading_signal_or_authenticated_fundamentals",
        ],
    }
