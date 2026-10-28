"""Opt-in public-only GitHub research; never accepts holdings or credentials."""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from alpha_lab.ingestion import batch_ingest
from alpha_lab.scan import render_dashboard, scan_directory


def parse_symbols(raw: str) -> list[str]:
    symbols = [s.strip() for s in raw.split(",")] if isinstance(raw, str) else []
    if (not 1 <= len(symbols) <= 10 or len(set(symbols)) != len(symbols)
            or any(not re.fullmatch(r"[0-9]{6}", s) for s in symbols)):
        raise ValueError("INVALID_PUBLIC_SYMBOLS_MAX_10")
    return symbols


def validate_dates(start: str, end: str, today: date | None = None):
    now = today or datetime.now(ZoneInfo("Asia/Shanghai")).date()
    try:
        a = datetime.strptime(start, "%Y%m%d").date()
        b = datetime.strptime(end, "%Y%m%d").date() if end else now
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_PUBLIC_DATE_RANGE") from exc
    if a > b or b > now or (b-a).days > 5500:
        raise ValueError("INVALID_OR_FUTURE_PUBLIC_DATE_RANGE")
    return a.strftime("%Y%m%d"), b.strftime("%Y%m%d"), b.isoformat()


def _static_html(scan: dict) -> str:
    text = escape(render_dashboard(scan), quote=True)
    return (
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>公开A股研究快照</title><style>"
        "body{font-family:system-ui,sans-serif;max-width:1200px;margin:32px auto;"
        "padding:0 16px;background:#f5f7fb;color:#182437}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:20px;"
        "border:1px solid #dde4ee;border-radius:10px;font:13px/1.7 monospace}"
        "p{padding:12px;background:#fff1da}</style></head><body>"
        "<h1>公开A股技术研究快照</h1><p>未连接私人持仓；未经复权、退市、财报"
        "和独立样本外验证。公开研究，不是买卖建议。</p>"
        "<pre>" + text + "</pre></body></html>"
    )


def run_public_research(*, symbols_text: str, start: str, end: str,
                        confirmed: bool, dest: str | Path,
                        fetcher=None, sleeper=None, today: date | None = None) -> dict:
    if confirmed is not True:
        raise ValueError("MANUAL_SOURCE_TERMS_CONFIRMATION_REQUIRED")
    symbols = parse_symbols(symbols_text)
    start, end, asof = validate_dates(start, end, today)
    dest = Path(dest)
    if dest.exists():
        raise ValueError("PUBLIC_OUTPUT_ALREADY_EXISTS")
    dest.mkdir(parents=True)
    manifest = batch_ingest(
        symbols=symbols, start=start, end=end, out_dir=dest/"prices",
        source_terms_confirmed=True, delay_seconds=2.0,
        fetcher=fetcher, sleeper=sleeper)
    if manifest["status"] != "COMPLETE_UNADJUSTED_RESEARCH_INPUT":
        raise ValueError("PUBLIC_RESEARCH_BLOCKED_INCOMPLETE_PROVIDER")
    scan = scan_directory(dest/"prices", asof=asof, max_age_days=7)
    (dest/"scan.json").write_text(
        json.dumps(scan, ensure_ascii=False, indent=2), encoding="utf-8")
    (dest/"dashboard.md").write_text(render_dashboard(scan), encoding="utf-8")
    (dest/"dashboard.html").write_text(_static_html(scan), encoding="utf-8")
    return {"status": "PUBLIC_RESEARCH_CREATED_NOT_VALIDATED_FOR_TRADING",
            "asof": asof, "symbols": symbols}


if __name__ == "__main__":
    try:
        report = run_public_research(
            symbols_text=os.environ.get("PUBLIC_SYMBOLS", ""),
            start=os.environ.get("PUBLIC_START", ""),
            end=os.environ.get("PUBLIC_END", ""),
            confirmed=os.environ.get("PUBLIC_TERMS", "").lower() == "true",
            dest=os.environ.get("PUBLIC_OUTPUT", "output/manual-public-research"))
        print(json.dumps(report, ensure_ascii=False))
    except (ValueError, RuntimeError) as exc:
        print(f"PUBLIC_RESEARCH_NOT_PRODUCED: {exc}", file=sys.stderr)
        sys.exit(1)
