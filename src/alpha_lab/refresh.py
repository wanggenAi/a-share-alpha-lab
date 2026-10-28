"""Immutable, bounded and auditable *incremental* unadjusted OHLCV refresh.

Requires explicit operator confirmation of applicable provider access terms.
Compares a re-fetched overlapping range byte-for-value at Bar semantics;
provider revisions/corporate actions are NOT silently accepted or overwritten.
A new snapshot is ALWAYS a new directory. No scheduling or brokerage actions.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .data import Bar, download_akshare, load_csv, save_csv, validate_bars
from .ingestion import MANIFEST, check_ingestion_manifest, _validate_symbols


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def refresh_snapshot(*, previous_dir: str | Path, out_dir: str | Path,
                     end: str, source_terms_confirmed: bool = False,
                     overlap_calendar_days: int = 21,
                     delay_seconds: float = 2.0,
                     fetcher=None, sleeper=None) -> dict:
    """Safely revalidate overlap and append new history, never rewrite previous.

    Incomplete/changed data becomes a PARTIAL_BLOCKED manifest; consumers
    reject that snapshot. No signal is generated from unverified differences.
    """
    if not source_terms_confirmed:
        raise ValueError("SOURCE_TERMS_CONFIRMATION_REQUIRED")
    if (type(overlap_calendar_days) is not int
            or not 7 <= overlap_calendar_days <= 90):
        raise ValueError("INVALID_REFRESH_OVERLAP_DAYS")
    if (type(delay_seconds) not in (int, float)
            or not 0.5 <= delay_seconds <= 30):
        raise ValueError("DELAY_SECONDS_OUT_OF_RANGE")
    try:
        end_day = datetime.strptime(end, "%Y%m%d").date()
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_REFRESH_END_DATE") from exc
    if end_day > datetime.now(timezone(timedelta(hours=8))).date():
        raise ValueError("REFRESH_END_DATE_IN_FUTURE")
    old_dir = Path(previous_dir).resolve()
    new_dir = Path(out_dir).resolve()
    if (new_dir.exists() or old_dir == new_dir
            or new_dir.is_relative_to(old_dir)
            or old_dir.is_relative_to(new_dir)):
        raise ValueError("REFRESH_OUTPUT_MUST_BE_NEW_AND_SEPARATE")
    parent = check_ingestion_manifest(old_dir)
    if parent is None or parent.get("source") != "AKSHARE_STOCK_ZH_A_HIST_UNADJUSTED":
        raise ValueError("PREVIOUS_SNAPSHOT_MUST_HAVE_VALID_AKSHARE_MANIFEST")
    symbols = parent["requested_symbols"]
    _validate_symbols(symbols)
    old_histories = {}
    for symbol in symbols:
        bars = load_csv(old_dir / (symbol + ".csv"))
        if bars[0].symbol != symbol:
            raise ValueError("PREVIOUS_SNAPSHOT_SYMBOL_MISMATCH")
        if end_day < date.fromisoformat(bars[-1].date):
            raise ValueError("REFRESH_END_BEFORE_EXISTING_LATEST_BAR")
        old_histories[symbol] = bars

    new_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".alpha-refresh-", dir=new_dir.parent))
    downloader = fetcher or download_akshare
    pause = sleeper or time.sleep
    details, failures = [], []
    try:
        for index, symbol in enumerate(symbols):
            old = old_histories[symbol]
            last = date.fromisoformat(old[-1].date)
            first = date.fromisoformat(old[0].date)
            overlap_start = max(first, last - timedelta(days=overlap_calendar_days))
            start = overlap_start.strftime("%Y%m%d")
            try:
                obtained = validate_bars(downloader(symbol, start, end))
                if obtained[0].symbol != symbol:
                    raise ValueError("REFRESH_PROVIDER_SYMBOL_MISMATCH")
                if (date.fromisoformat(obtained[0].date) < overlap_start
                        or date.fromisoformat(obtained[-1].date) > end_day):
                    raise ValueError("REFRESH_PROVIDER_RETURNED_OUT_OF_RANGE")
                # Require an exact overlap: latest previously known session
                # MUST be included, preventing silent outdated partial results.
                old_overlap = {b.date: b for b in old if b.date >= overlap_start.isoformat()}
                fetched_overlap = {b.date: b for b in obtained if b.date <= old[-1].date}
                if not old_overlap or set(old_overlap) != set(fetched_overlap):
                    raise ValueError("REFRESH_OVERLAP_MISSING_OR_CHANGED_DATES")
                if any(old_overlap[d] != fetched_overlap[d] for d in old_overlap):
                    raise ValueError("REFRESH_HISTORICAL_REVISION_BLOCKED")
                additional = [b for b in obtained if b.date > old[-1].date]
                merged = validate_bars(old + additional)
                file = staging / (symbol + ".csv")
                save_csv(merged, file)
                details.append({
                    "symbol": symbol,
                    "file": file.name,
                    "sha256": _hash(file),
                    "parent_file_sha256": _hash(old_dir / (symbol + ".csv")),
                    "observations": len(merged),
                    "first_date": merged[0].date,
                    "last_date": merged[-1].date,
                    "revalidated_overlap_sessions": len(old_overlap),
                    "new_sessions": len(additional),
                    "refresh_state": "APPENDED" if additional else "NO_NEW_SESSIONS_OVERLAP_RECHECKED",
                })
            except (OSError, RuntimeError, ValueError, TimeoutError, TypeError) as exc:
                failures.append({
                    "symbol": symbol,
                    "reason": str(exc) if isinstance(exc, ValueError) else type(exc).__name__,
                    "status": "REFRESH_OR_REVALIDATION_FAILED",
                })
            if index < len(symbols) - 1:
                pause(delay_seconds)
        result = {
            "schema_version": "0.14",
            "status": "COMPLETE_UNADJUSTED_RESEARCH_INPUT" if not failures else "PARTIAL_BLOCKED",
            "source": "AKSHARE_STOCK_ZH_A_HIST_UNADJUSTED",
            "source_terms_confirmation": "DECLARED_BY_OPERATOR_NOT_VERIFIED",
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "start_yyyymmdd": parent["start_yyyymmdd"],
            "end_yyyymmdd": end,
            "requested_symbols": symbols,
            "downloaded": details,
            "failures": failures,
            "refresh_lineage": {
                "parent_manifest_sha256": _hash(old_dir / MANIFEST),
                "parent_requested_end_yyyymmdd": parent["end_yyyymmdd"],
                "overlap_calendar_days": overlap_calendar_days,
                "new_sessions_total": sum(d["new_sessions"] for d in details),
                "refresh_is_not_real_time_quote_feed": True,
            },
            "limitations": [
                "unadjusted_history_corporate_actions_not_repaired",
                "provider_revisions_blocked_not_auto_accepted",
                "overlap_recheck_not_full_history_independent_verification",
                "no_point_in_time_ST_suspension_delisting_or_filing_evidence",
                "source_rights_and_provider_connectivity_not_independently_verified",
                "no_automatic_schedule_or_trading_orders",
            ],
        }
        (staging / MANIFEST).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if new_dir.exists():
            raise ValueError("REFRESH_OUTPUT_ALREADY_CREATED")
        staging.rename(new_dir)
        return {**result, "output_dir": str(new_dir)}
    finally:
        if staging.exists():
            shutil.rmtree(staging)
