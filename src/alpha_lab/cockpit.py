"""Local-only research cockpit: holdings, persistent candidates and evidence.

Private positions are read from local input files and MUST NOT be committed.
All outputs are research REVIEW states; never autonomous trade instructions.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path


def _iso(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("INVALID_ASOF_DATE")
    try:
        day = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("INVALID_ASOF_DATE") from exc
    if day.isoformat() != value:
        raise ValueError("INVALID_ASOF_DATE")
    return value


def _finite_nonnegative(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def validate_holdings(holdings: dict, asof: str) -> tuple[list[dict], float]:
    if not isinstance(holdings, dict) or _iso(holdings.get("asof")) != asof:
        raise ValueError("HOLDINGS_ASOF_MISMATCH")
    positions = holdings.get("positions")
    cash = holdings.get("cash")
    if not isinstance(positions, list) or not _finite_nonnegative(cash):
        raise ValueError("INVALID_HOLDINGS_SCHEMA")
    if len(positions) > 500:
        raise ValueError("TOO_MANY_POSITIONS")
    seen = set()
    clean = []
    for p in positions:
        if not isinstance(p, dict):
            raise ValueError("INVALID_HOLDING")
        symbol = p.get("symbol")
        shares = p.get("shares")
        cost = p.get("cost_basis_per_share")
        if (not isinstance(symbol, str) or len(symbol) != 6 or not symbol.isdigit()
                or symbol in seen or type(shares) is not int or shares <= 0
                or not _finite_nonnegative(cost) or cost <= 0):
            raise ValueError("INVALID_OR_DUPLICATE_HOLDING")
        seen.add(symbol)
        clean.append({"symbol": symbol, "shares": shares,
                      "cost_basis_per_share": float(cost)})
    return sorted(clean, key=lambda x: x["symbol"]), float(cash)


def _quote(row: dict | None, *, max_age: int) -> float | None:
    if not row or row.get("reason", "").startswith(("DATA_ERROR:", "DUPLICATE_SYMBOL")):
        return None
    evidence = row.get("evidence", {})
    close, age = evidence.get("close"), evidence.get("age_calendar_days")
    if (not isinstance(age, int) or age < 0 or age > max_age
            or type(close) not in (int, float) or not math.isfinite(close)
            or close <= 0 or row.get("reason") in (
                "STALE_DATA", "FUTURE_DATA_AFTER_ASOF", "RECENT_ZERO_VOLUME",
                "INSUFFICIENT_BARS_MIN_65")):
        return None
    return float(close)


def _clean_scan(scan: dict) -> tuple[str, dict[str, dict], int]:
    if not isinstance(scan, dict) or scan.get("status") != "RESEARCH_ONLY_NOT_VALIDATED":
        raise ValueError("INVALID_SCAN_REPORT")
    asof = _iso(scan.get("asof"))
    rows, max_age = scan.get("records"), scan.get("max_age_calendar_days")
    if not isinstance(rows, list) or type(max_age) is not int or max_age < 0:
        raise ValueError("INVALID_SCAN_REPORT")
    counter = Counter(r.get("symbol") for r in rows
                      if isinstance(r, dict) and r.get("symbol"))
    indexed = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("status") not in (
            "WATCH_SIGNAL", "WAIT_PRICE", "REJECT"):
            raise ValueError("INVALID_SCAN_RECORD")
        symbol = row.get("symbol")
        if symbol and counter[symbol] == 1:
            indexed[symbol] = row
    return asof, indexed, max_age


def build_cockpit(scan: dict, holdings: dict, previous: dict | None = None) -> dict:
    asof, indexed, max_age = _clean_scan(scan)
    positions, cash = validate_holdings(holdings, asof)
    history = {}
    if previous is not None:
        if not isinstance(previous, dict) or previous.get("status") != "RESEARCH_COCKPIT":
            raise ValueError("INVALID_PREVIOUS_COCKPIT")
        prev_asof = _iso(previous.get("asof"))
        if prev_asof > asof:
            raise ValueError("PREVIOUS_REPORT_FROM_FUTURE")
        prev_items = previous.get("candidates")
        if not isinstance(prev_items, list) or len(prev_items) > 5000:
            raise ValueError("INVALID_PREVIOUS_CANDIDATES")
        for row in prev_items:
            if not isinstance(row, dict):
                raise ValueError("INVALID_PREVIOUS_CANDIDATES")
            sym, first = row.get("symbol"), _iso(row.get("first_seen_asof"))
            if (not isinstance(sym, str) or len(sym) != 6 or not sym.isdigit()
                    or sym in history or first > prev_asof):
                raise ValueError("INVALID_PREVIOUS_CANDIDATES")
            history[sym] = first

    for symbol, row in indexed.items():
        if row["status"] in ("WATCH_SIGNAL", "WAIT_PRICE") and _quote(
                row, max_age=max_age) is not None:
            history.setdefault(symbol, asof)
    candidates = []
    for symbol, first in sorted(history.items()):
        row = indexed.get(symbol)
        price = _quote(row, max_age=max_age)
        if price is None:
            state = "BLOCKED_MISSING_OR_UNSAFE_DATA"
        elif row["status"] in ("WATCH_SIGNAL", "WAIT_PRICE"):
            state = row["status"]
        else:
            state = "DORMANT_NO_CURRENT_SETUP"
        candidates.append({
            "symbol": symbol,
            "first_seen_asof": first,
            "last_checked_asof": asof,
            "research_state": state,
            "latest_reference_close": price,
            "evidence_source": row.get("source") if row else None,
            "reason": row.get("reason") if row else "MISSING_FROM_CURRENT_SCAN",
        })

    valued = []
    for p in positions:
        row = indexed.get(p["symbol"])
        price = _quote(row, max_age=max_age)
        market_value = round(p["shares"] * price, 2) if price is not None else None
        unrealized = (
            round(p["shares"] * (price - p["cost_basis_per_share"]), 2)
            if price is not None else None
        )
        if price is None:
            action = "REVIEW_DATA_MISSING"
        elif row["status"] == "WATCH_SIGNAL":
            action = "REVIEW_HOLDING_WITH_TECHNICAL_SETUP"
        elif row["status"] == "WAIT_PRICE":
            action = "REVIEW_HOLDING_AWAITING_CONFIRMATION"
        else:
            action = "REVIEW_HOLDING_NO_CURRENT_SETUP"
        valued.append({
            **p,
            "reference_close": price,
            "market_value_excluding_fees": market_value,
            "unrealized_pnl_excluding_fees": unrealized,
            "research_action": action,
            "evidence_source": row.get("source") if row else None,
            "data_date": row.get("latest_date") if row else None,
        })
    complete = all(p["market_value_excluding_fees"] is not None for p in valued)
    # Never publish a partial portfolio as a full valuation.
    gross = round(sum(p["market_value_excluding_fees"] for p in valued) + cash, 2) if complete else None
    if complete and gross > 0:
        for p in valued:
            p["portfolio_weight_pct"] = round(
                100 * p["market_value_excluding_fees"] / gross, 2)
    else:
        for p in valued:
            p["portfolio_weight_pct"] = None
    max_weight = max((p["portfolio_weight_pct"] for p in valued), default=0) if gross is not None else None
    concentration_flag = (
        "REVIEW_SINGLE_POSITION_OVER_30_PCT" if max_weight is not None and max_weight > 30
        else "NO_CONCENTRATION_FLAG_AT_30_PCT" if max_weight is not None
        else "UNKNOWN_INCOMPLETE_VALUATION"
    )
    return {
        "schema_version": "0.4",
        "status": "RESEARCH_COCKPIT",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "asof": asof,
        "investment_decision_status": "HUMAN_REVIEW_REQUIRED_NOT_A_BUY_OR_SELL_SIGNAL",
        "holdings": valued,
        "candidates": candidates,
        "summary": {
            "positions": len(valued),
            "candidate_count": len(candidates),
            "unvalued_positions": sum(p["reference_close"] is None for p in valued),
            "cash_from_user_input": cash,
            "portfolio_marked_value_excluding_fees": gross,
            "portfolio_unrealized_pnl_excluding_fees": (
                round(sum(p["unrealized_pnl_excluding_fees"] for p in valued), 2)
                if complete else None
            ),
            "concentration_30pct_flag": concentration_flag,
            "universe_coverage": "ONLY_USER_SUPPLIED_LOCAL_CSV_FILES",
            "market_cycle_radar": "UNAVAILABLE_WITHOUT_VERIFIED_BENCHMARK_DATA",
        },
        "limitations": [
            "private_positions_local_only_do_not_publish",
            "unadjusted_prices_may_distort_profit_loss_across_corporate_actions",
            "cost_basis_and_cash_are_user_supplied_not_broker_reconciled",
            "no_fees_dividends_taxes_or_fx_in_marked_values",
            "no_market_wide_or_fundamental_coverage",
            "all_actions_are_review_labels_not_trade_instructions",
        ],
    }


def render_cockpit(report: dict) -> str:
    s = report["summary"]
    lines = [
        "# A-Share Alpha Lab | Investment Research Cockpit", "",
        f'As-of: **{report["asof"]}** · {report["investment_decision_status"]}', "",
        "**Local private output: do not commit holdings or this report.**", "",
        f'Holdings: {s["positions"]} · Research candidates: {s["candidate_count"]} '
        f'· Unpriced positions: {s["unvalued_positions"]}', "",
        f'Portfolio value (excluding fees): {s["portfolio_marked_value_excluding_fees"]}',
        f'Unrealized P/L (excluding fees): {s["portfolio_unrealized_pnl_excluding_fees"]}',
        f'Risk flag: {s["concentration_30pct_flag"]}', "",
        "## Position research actions", "",
        "| Ticker | Shares | Reference price | Weight % | Review state | Evidence |",
        "|---|---:|---:|---:|---|---|",
    ]
    esc = lambda value: str(value if value is not None else "—").replace("|", "/").replace("\n", " ")
    for p in report["holdings"]:
        lines.append("| " + " | ".join(esc(x) for x in (
            p["symbol"], p["shares"], p["reference_close"],
            p["portfolio_weight_pct"], p["research_action"], p["evidence_source"],
        )) + " |")
    lines += ["", "## Persistent candidate queue", "",
              "| Ticker | First seen | Current state | Source | Reason |",
              "|---|---|---|---|---|"]
    for c in report["candidates"]:
        lines.append("| " + " | ".join(esc(x) for x in (
            c["symbol"], c["first_seen_asof"], c["research_state"],
            c["evidence_source"], c["reason"],
        )) + " |")
    lines += ["", "## Market and cycle radar", "",
              s["market_cycle_radar"], "", "## Limitations", ""]
    lines += ["- " + x for x in report["limitations"]]
    lines += ["", "All technical conclusions require human interpretation; no automated trading.", ""]
    return "\n".join(lines)


def build_from_files(scan_path: str | Path, holdings_path: str | Path,
                     previous_path: str | Path | None = None) -> dict:
    scan = json.loads(Path(scan_path).read_text(encoding="utf-8"))
    holdings = json.loads(Path(holdings_path).read_text(encoding="utf-8"))
    prior = (json.loads(Path(previous_path).read_text(encoding="utf-8"))
             if previous_path is not None else None)
    return build_cockpit(scan, holdings, previous=prior)
