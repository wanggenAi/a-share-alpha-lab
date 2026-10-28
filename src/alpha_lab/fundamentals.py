"""Point-in-time manual financial filing evidence, with no simulated verification.

All amounts must be CNY yuan. Raw records are supplied by users or licensed
sources; declared URLs and metrics are NOT independently corroborated here.
Publication dates, NOT fiscal period ends, determine historical availability.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from urllib.parse import urlsplit


KINDS = frozenset({"Q1", "H1", "9M", "FY"})
NUMERIC_FIELDS = (
    "revenue_yuan", "net_income_yuan", "operating_cash_flow_yuan",
    "total_assets_yuan", "total_liabilities_yuan",
    "shareholders_equity_yuan", "shares_outstanding",
)


def _date(value: object) -> date:
    if not isinstance(value, str):
        raise ValueError("INVALID_FINANCIAL_DATE")
    try:
        d = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("INVALID_FINANCIAL_DATE") from exc
    if d.isoformat() != value:
        raise ValueError("INVALID_FINANCIAL_DATE")
    return d


def _number(value: object) -> bool:
    return type(value) in (float, int) and math.isfinite(value)


def _validate_record(rec: dict) -> None:
    if not isinstance(rec, dict):
        raise ValueError("INVALID_FILING_ENTRY")
    symbol = rec.get("symbol")
    if not isinstance(symbol, str) or len(symbol) != 6 or not symbol.isdigit():
        raise ValueError("INVALID_FILING_SYMBOL")
    fiscal = _date(rec.get("fiscal_end"))
    published = _date(rec.get("published_at"))
    if fiscal > published:
        raise ValueError("FILING_PUBLISHED_BEFORE_PERIOD_END")
    if rec.get("period_kind") not in KINDS or rec.get("currency") != "CNY":
        raise ValueError("INVALID_FILING_PERIOD_OR_CURRENCY")
    link = rec.get("source_url")
    if not isinstance(link, str):
        raise ValueError("INVALID_FILING_SOURCE")
    parsed = urlsplit(link)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("INVALID_FILING_SOURCE")
    if any(not _number(rec.get(name)) for name in NUMERIC_FIELDS):
        raise ValueError("INVALID_FILING_NUMERIC_FIELDS")
    if (rec["revenue_yuan"] < 0 or rec["total_assets_yuan"] <= 0
            or rec["total_liabilities_yuan"] < 0 or rec["shares_outstanding"] <= 0):
        raise ValueError("INVALID_FILING_BALANCE_FIELDS")


def _pct_change(current: float, prior: float) -> float | None:
    return round(100 * (current / prior - 1), 3) if prior > 0 else None


def research_financial_evidence(payload: dict, *, asof: str,
                                reference_prices: dict[str, float] | None = None) -> dict:
    """Return per-symbol evidence available AS OF date; no look-ahead leak."""
    today = _date(asof)
    if not isinstance(payload, dict) or payload.get("schema_version") != "1":
        raise ValueError("INVALID_FINANCIAL_INPUT_SCHEMA")
    records = payload.get("records")
    if not isinstance(records, list) or len(records) > 10000:
        raise ValueError("INVALID_FINANCIAL_RECORDS")
    selected = defaultdict(list)
    seen = set()
    for record in records:
        _validate_record(record)
        key = (record["symbol"], record["fiscal_end"], record["period_kind"])
        if key in seen:
            raise ValueError("DUPLICATE_FILING_PERIOD_RESTATEMENT_NEEDS_REVIEW")
        seen.add(key)
        if _date(record["published_at"]) <= today:
            selected[record["symbol"]].append(record)
    price_lookup = reference_prices or {}
    output = {}
    for symbol, available in selected.items():
        # Reporting periods and actual release dates are both explicit.
        latest = max(available, key=lambda x: (x["fiscal_end"], x["published_at"]))
        period = _date(latest["fiscal_end"])
        prev_candidates = [
            rec for rec in available
            if (rec["period_kind"] == latest["period_kind"]
                and _date(rec["fiscal_end"]).year == period.year - 1
                and _date(rec["fiscal_end"]).month == period.month
                and _date(rec["fiscal_end"]).day == period.day)
        ]
        prev = max(prev_candidates, key=lambda x: x["published_at"]) if prev_candidates else None
        liability_pct = round(100 * latest["total_liabilities_yuan"] /
                              latest["total_assets_yuan"], 3)
        income = latest["net_income_yuan"]
        cashflow = latest["operating_cash_flow_yuan"]
        price = price_lookup.get(symbol)
        if price is not None and (not _number(price) or price <= 0):
            raise ValueError("INVALID_FINANCIAL_REFERENCE_PRICE")
        market_cap = price * latest["shares_outstanding"] if price else None
        pe = (round(market_cap / income, 3)
              if market_cap is not None and latest["period_kind"] == "FY" and income > 0
              else None)
        eq = latest["shareholders_equity_yuan"]
        pb = round(market_cap / eq, 3) if market_cap is not None and eq > 0 else None
        revenue_yoy = (_pct_change(latest["revenue_yuan"], prev["revenue_yuan"])
                       if prev is not None else None)
        profit_yoy = (_pct_change(income, prev["net_income_yuan"])
                      if prev is not None else None)
        flags = []
        if income <= 0:
            flags.append("NONPOSITIVE_REPORTED_NET_INCOME")
        if cashflow < 0:
            flags.append("NEGATIVE_REPORTED_OPERATING_CASH_FLOW")
        elif income > 0 and cashflow < income:
            flags.append("OPERATING_CASH_FLOW_LT_REPORTED_PROFIT")
        if liability_pct > 70:
            flags.append("LIABILITIES_OVER_70_PERCENT_ASSETS")
        if revenue_yoy is not None and revenue_yoy < 0:
            flags.append("COMPARABLE_PERIOD_REVENUE_DECLINED")
        stale = (today - period).days > 550
        output[symbol] = {
            "status": "STALE_FILING_REVIEW" if stale else "DECLARED_UNVERIFIED_REVIEW",
            "asof": asof,
            "symbol": symbol,
            "fiscal_end": latest["fiscal_end"],
            "period_kind": latest["period_kind"],
            "published_at": latest["published_at"],
            "source_url": latest["source_url"],
            "source_verification": "URL_AND_NUMBERS_DECLARED_NOT_INDEPENDENTLY_VERIFIED",
            "comparable_previous_fiscal_end": prev["fiscal_end"] if prev else None,
            "metrics": {
                "revenue_yoy_pct": revenue_yoy,
                "net_income_yoy_pct": profit_yoy,
                "operating_cash_flow_to_net_income": (
                    round(cashflow / income, 4) if income > 0 else None),
                "liability_to_asset_pct": liability_pct,
                "pe_fy_reported_earnings_only": pe,
                "pb_reported_equity": pb,
            },
            "risk_flags": flags,
            "limitations": [
                "manual_filings_not_authenticated",
                "no_capex_or_free_cash_flow_validation",
                "valuation_uses_reference_share_price_and_reported_shares",
                "no_split_dividend_restatement_or_TTM_evidence",
            ],
        }
    return output
