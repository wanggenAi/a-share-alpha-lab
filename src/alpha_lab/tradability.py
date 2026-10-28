"""Conservative per-session, as-known-then eligibility evidence for A shares.

Operator-declared URLs, timestamps, security status and action flags are NOT
independently authenticated. Missing/late/non-regular evidence blocks research.
Every record must be available BEFORE that session's 09:15 China pre-open
cutoff, preventing same-day hindsight metadata from justifying an entry.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .data import Bar, validate_bars

SHANGHAI = timezone(timedelta(hours=8))
STATES = frozenset(("REGULAR", "ST", "SUSPENDED", "DELISTED", "IPO_SPECIAL", "UNKNOWN"))
ACTIONS = frozenset(("NONE_DECLARED", "DIVIDEND", "SPLIT", "RIGHTS", "UNKNOWN"))
REASON_ORDER = ("MISSING_STATUS_EVIDENCE", "STATUS_NOT_REGULAR",
                "UNRESOLVED_CORPORATE_ACTION", "NOT_KNOWN_BEFORE_PREOPEN")


def _as_date(value: object) -> date:
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("INVALID_ELIGIBILITY_DATE")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("INVALID_ELIGIBILITY_DATE") from exc


def _observed(value: object) -> datetime:
    if type(value) is not str:
        raise ValueError("INVALID_OBSERVED_TIMESTAMP")
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("INVALID_OBSERVED_TIMESTAMP") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("OBSERVED_TIMESTAMP_MUST_HAVE_OFFSET")
    return dt


def _valid_url(url: object) -> bool:
    if type(url) is not str:
        return False
    info = urlsplit(url)
    return (info.scheme == "https" and bool(info.hostname)
            and info.username is None and info.password is None)


def audit_eligibility(histories: dict[str, list[Bar]], ledger: dict) -> dict:
    """Validate complete date-symbol universe against operator-declared evidence.

    Audit includes every missing/blocked session; the caller decides whether
    to halt the experiment. The status NEVER certifies provenance as official.
    """
    if not isinstance(histories, dict) or not histories or len(histories) > 30:
        raise ValueError("INVALID_ELIGIBILITY_UNIVERSE")
    if not isinstance(ledger, dict) or ledger.get("schema_version") != "1":
        raise ValueError("INVALID_ELIGIBILITY_SCHEMA")
    sessions = ledger.get("sessions")
    if not isinstance(sessions, list) or len(sessions) > 200000:
        raise ValueError("INVALID_ELIGIBILITY_SESSION_LIST")
    sources = {}
    for rec in sessions:
        if not isinstance(rec, dict):
            raise ValueError("INVALID_ELIGIBILITY_RECORD")
        symbol, day = rec.get("symbol"), rec.get("date")
        if (type(symbol) is not str or not re.fullmatch(r"\d{6}", symbol)):
            raise ValueError("INVALID_ELIGIBILITY_SYMBOL")
        _as_date(day)
        if rec.get("state") not in STATES or rec.get("corporate_action") not in ACTIONS:
            raise ValueError("INVALID_ELIGIBILITY_STATE_OR_ACTION")
        if not _valid_url(rec.get("source_url")):
            raise ValueError("INVALID_ELIGIBILITY_SOURCE_URL")
        published = _observed(rec.get("observed_at"))
        key = (symbol, day)
        if key in sources:
            raise ValueError("DUPLICATE_ELIGIBILITY_SESSION")
        sources[key] = (rec, published)
    expected = set()
    blocked = []
    checked = 0
    for symbol, bars in sorted(histories.items()):
        validate_bars(bars)
        if bars[0].symbol != symbol:
            raise ValueError("ELIGIBILITY_UNIVERSE_SYMBOL_MISMATCH")
        for bar in bars:
            key = (symbol, bar.date)
            expected.add(key)
            checked += 1
            record = sources.get(key)
            reasons = []
            if record is None:
                reasons.append("MISSING_STATUS_EVIDENCE")
            else:
                rec, observed_at = record
                if rec["state"] != "REGULAR":
                    reasons.append("STATUS_NOT_REGULAR")
                if rec["corporate_action"] != "NONE_DECLARED":
                    reasons.append("UNRESOLVED_CORPORATE_ACTION")
                preopen = datetime.combine(_as_date(bar.date), time(9, 15),
                                           tzinfo=SHANGHAI)
                if observed_at > preopen:
                    reasons.append("NOT_KNOWN_BEFORE_PREOPEN")
            if reasons:
                blocked.append({"symbol": symbol, "date": bar.date, "reasons": reasons})
    if set(sources) != expected:
        unknown = set(sources) - expected
        if unknown:
            raise ValueError("UNMATCHED_EXTRA_ELIGIBILITY_SESSIONS")
    counts = Counter(reason for item in blocked for reason in item["reasons"])
    return {
        "schema_version": "0.13",
        "status": ("DECLARED_EVIDENCE_COMPLETE_UNVERIFIED"
                   if not blocked else "BLOCKED_MISSING_OR_UNSAFE_ELIGIBILITY"),
        "source_verification": "OPERATOR_DECLARED_NOT_INDEPENDENTLY_VERIFIED",
        "required_sessions": checked,
        "provided_records": len(sources),
        "blocked_sessions": len(blocked),
        "reason_counts": {name: counts.get(name, 0) for name in REASON_ORDER},
        "blocked": blocked,
        "limitations": [
            "reported_security_states_are_not_verified_with_exchange",
            "one_record_required_per_symbol_per_observed_bar_date",
            "preopen_observation_cutoff_09_15_Asia_Shanghai",
            "no_independent_listing_ST_suspension_or_delisting_reconstruction",
            "NONE_DECLARED_is_not_a_guarantee_of_no_corporate_action",
            "unadjusted_prices_and_real_execution_remain_unverified",
        ],
    }


def audit_eligibility_file(histories: dict[str, list[Bar]],
                           path: str | Path) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return audit_eligibility(histories, payload)


def require_eligible_histories(histories: dict[str, list[Bar]],
                               path: str | Path) -> dict:
    report = audit_eligibility_file(histories, path)
    if report["blocked_sessions"]:
        first = report["blocked"][0]
        raise ValueError(
            "PIT_ELIGIBILITY_BLOCKED:"
            + first["symbol"] + ":" + first["date"]
            + ":" + ",".join(first["reasons"]))
    return report
