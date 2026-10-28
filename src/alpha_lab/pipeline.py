"""Atomic, privacy-safe offline scan → cockpit → HTML/Markdown pipeline."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from .cockpit import build_cockpit, render_cockpit
from .html_dashboard import render_html
from .scan import scan_directory
from .market_radar import build_market_radar
from .portfolio import PortfolioRules, portfolio_from_directory


def run_local_pipeline(*, input_dir: str | Path, holdings_path: str | Path,
                       asof: str, out_dir: str | Path,
                       fundamentals_path: str | Path | None = None,
                       previous_path: str | Path | None = None,
                       benchmark_dir: str | Path | None = None,
                       portfolio_first_trade_date: str | None = None,
                       eligibility_ledger_path: str | Path | None = None,
                       portfolio_starting_cash: float = 100000.0,
                       portfolio_max_positions: int = 5,
                       portfolio_allocation_fraction: float = 0.20,
                       max_age_days: int = 5) -> dict:
    """No market downloads, no orders, no overwriting existing snapshots."""
    dest = Path(out_dir).resolve()
    inputs = [Path(holdings_path).resolve(), Path(input_dir).resolve()]
    if fundamentals_path is not None:
        inputs.append(Path(fundamentals_path).resolve())
    if previous_path is not None:
        inputs.append(Path(previous_path).resolve())
    if benchmark_dir is not None:
        inputs.append(Path(benchmark_dir).resolve())
    if eligibility_ledger_path is not None:
        inputs.append(Path(eligibility_ledger_path).resolve())
    if dest.exists() or dest in inputs or dest.is_relative_to(inputs[1]):
        raise ValueError("SNAPSHOT_TARGET_EXISTS_OR_COLLIDES_WITH_INPUT")
    scan = scan_directory(input_dir, asof=asof, max_age_days=max_age_days)
    holdings = json.loads(Path(holdings_path).read_text(encoding="utf-8"))
    financial = (json.loads(Path(fundamentals_path).read_text(encoding="utf-8"))
                 if fundamentals_path is not None else None)
    previous = (json.loads(Path(previous_path).read_text(encoding="utf-8"))
                if previous_path is not None else None)
    market = (build_market_radar(benchmark_dir, asof=asof,
                                  max_age_days=max_age_days)
              if benchmark_dir is not None else None)
    experiment = None
    if portfolio_first_trade_date is not None:
        rules = PortfolioRules(
            first_trade_date=portfolio_first_trade_date,
            starting_cash=portfolio_starting_cash,
            max_positions=portfolio_max_positions,
            allocation_fraction=portfolio_allocation_fraction)
        experiment = portfolio_from_directory(input_dir, rules,
                                               eligibility_ledger=eligibility_ledger_path)
        if experiment["last_session"] != asof:
            raise ValueError("HYPOTHETICAL_PORTFOLIO_ASOF_MISMATCH")
    cockpit = build_cockpit(scan, holdings, previous=previous,
                            fundamentals=financial, market_radar=market,
                            historical_portfolio=experiment)
    rendered_html = render_html(cockpit)
    rendered_markdown = render_cockpit(cockpit)

    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".alpha-staging-", dir=dest.parent))
    try:
        files = {
            "scan.json": json.dumps(scan, ensure_ascii=False, indent=2),
            "cockpit.json": json.dumps(cockpit, ensure_ascii=False, indent=2),
            "cockpit.md": rendered_markdown,
            "cockpit.html": rendered_html,
        }
        if experiment is not None:
            files["portfolio_research.json"] = json.dumps(experiment, ensure_ascii=False, indent=2)
        if market is not None:
            files["market_radar.json"] = json.dumps(market, ensure_ascii=False, indent=2)
        for name, data in files.items():
            (staging / name).write_text(data, encoding="utf-8")
        if dest.exists():
            raise ValueError("SNAPSHOT_TARGET_ALREADY_CREATED")
        staging.rename(dest)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {
        "status": "COMPLETED_LOCAL_RESEARCH_SNAPSHOT_NOT_VALIDATED_FOR_TRADING",
        "asof": asof,
        "snapshot_directory": str(dest),
        "files": sorted(files),
        "candidates": len(cockpit["candidates"]),
        "positions": len(cockpit["holdings"]),
        "missing_price_positions": cockpit["summary"]["unvalued_positions"],
    }
