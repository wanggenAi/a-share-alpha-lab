"""Opt-in, bounded and auditable AKShare daily OHLCV batch ingestion.

Real network use is initiated only by an explicit local CLI call. Data are
UNADJUSTED and not guaranteed point-in-time or investment-grade.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from .data import download_akshare, save_csv


MANIFEST = "_ingestion_manifest.json"


def _validate_symbols(symbols: list[str]) -> None:
    if (not isinstance(symbols, list) or not 1 <= len(symbols) <= 30
            or any(not isinstance(s, str) or len(s) != 6 or not s.isdigit()
                   for s in symbols) or len(set(symbols)) != len(symbols)):
        raise ValueError("INVALID_OR_DUPLICATE_SYMBOLS_MAX_30")


def _range(start: str, end: str) -> None:
    try:
        a = datetime.strptime(start, "%Y%m%d").date()
        b = datetime.strptime(end, "%Y%m%d").date()
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_INGEST_DATE_RANGE") from exc
    if a > b:
        raise ValueError("INVALID_INGEST_DATE_RANGE")


def batch_ingest(*, symbols: list[str], start: str, end: str, out_dir: str | Path,
                 source_terms_confirmed: bool = False, delay_seconds: float = 2.0,
                 fetcher=None, sleeper=None) -> dict:
    """At most 30 explicit tickers; partial result is saved but BLOCKED."""
    if not source_terms_confirmed:
        raise ValueError("SOURCE_TERMS_CONFIRMATION_REQUIRED")
    _validate_symbols(symbols)
    _range(start, end)
    if (type(delay_seconds) not in (float, int) or not 0.5 <= delay_seconds <= 30):
        raise ValueError("DELAY_SECONDS_OUT_OF_RANGE")
    dest = Path(out_dir).resolve()
    if dest.exists():
        raise ValueError("INGEST_OUTPUT_ALREADY_EXISTS")
    loader = fetcher or download_akshare
    sleep = sleeper or time.sleep
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".alpha-ingest-", dir=dest.parent))
    details, failures = [], []
    try:
        for idx, symbol in enumerate(symbols):
            try:
                bars = loader(symbol, start, end)
                path = staging / (symbol + ".csv")
                save_csv(bars, path)
                details.append({
                    "symbol": symbol,
                    "file": path.name,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "observations": len(bars),
                    "first_date": bars[0].date,
                    "last_date": bars[-1].date,
                })
            except (OSError, RuntimeError, ValueError, TimeoutError) as exc:
                failures.append({"symbol": symbol, "error_type": type(exc).__name__,
                                 "status": "DOWNLOAD_OR_DATA_VALIDATION_FAILED"})
            if idx < len(symbols) - 1:
                sleep(delay_seconds)
        result = {
            "schema_version": "0.7",
            "status": "COMPLETE_UNADJUSTED_RESEARCH_INPUT" if not failures
                      else "PARTIAL_BLOCKED",
            "source": "AKSHARE_STOCK_ZH_A_HIST_UNADJUSTED",
            "source_terms_confirmation": "DECLARED_BY_OPERATOR_NOT_VERIFIED",
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "start_yyyymmdd": start,
            "end_yyyymmdd": end,
            "requested_symbols": symbols,
            "downloaded": details,
            "failures": failures,
            "limitations": [
                "unadjusted_history_and_dividends_not_addressed",
                "provider_availability_and_data_rights_not_independently_verified",
                "historical_delisting_and_st_status_not_validated",
                "not_a_real_time_market_data_feed",
            ],
        }
        (staging / MANIFEST).write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        if dest.exists():
            raise ValueError("INGEST_OUTPUT_ALREADY_EXISTS")
        staging.rename(dest)
        return {**result, "output_dir": str(dest)}
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def check_ingestion_manifest(directory: str | Path) -> dict | None:
    """Return None for unmanaged local CSV; fail closed if manifest is present."""
    root = Path(directory)
    path = root / MANIFEST
    if not path.exists():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("INVALID_INGESTION_MANIFEST") from exc
    if (not isinstance(manifest, dict)
            or manifest.get("status") != "COMPLETE_UNADJUSTED_RESEARCH_INPUT"):
        raise ValueError("INCOMPLETE_OR_UNTRUSTED_INGESTION_MANIFEST")
    symbols = manifest.get("requested_symbols")
    _validate_symbols(symbols)
    records = manifest.get("downloaded")
    if not isinstance(records, list) or len(records) != len(symbols):
        raise ValueError("INGESTION_MANIFEST_INCOMPLETE")
    actual_files = {p.name for p in root.glob("*.csv")}
    manifest_files = set()
    recorded_symbols = set()
    for item in records:
        if not isinstance(item, dict):
            raise ValueError("INVALID_INGESTION_RECORD")
        sym = item.get("symbol")
        name = item.get("file")
        if sym not in symbols or sym in recorded_symbols or name != str(sym) + ".csv":
            raise ValueError("INVALID_INGESTION_RECORD")
        recorded_symbols.add(sym)
        manifest_files.add(name)
        file = root / name
        if not file.is_file() or not isinstance(item.get("sha256"), str):
            raise ValueError("INGESTION_FILE_MISSING")
        if hashlib.sha256(file.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("INGESTION_SHA256_MISMATCH")
    if manifest_files != actual_files or recorded_symbols != set(symbols):
        raise ValueError("INGESTION_MANIFEST_FILE_SET_MISMATCH")
    return manifest
