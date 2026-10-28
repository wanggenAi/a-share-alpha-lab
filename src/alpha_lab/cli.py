"""Manual, inspectable research commands."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .backtest import research_backtest
from .data import download_akshare, load_csv, save_csv
from .intelligence import poll_feeds
from .scan import scan_directory, render_dashboard
from .evaluation import evaluate_file
from .cockpit import build_from_files, render_cockpit
from .pipeline import run_local_pipeline
from .ingestion import batch_ingest
from .refresh import refresh_snapshot
from .market_radar import build_market_radar
from .tradability import audit_eligibility_file
from .portfolio import PortfolioRules, portfolio_from_directory
from .portfolio_evaluation import portfolio_folds_from_directory


def main() -> None:
    parser = argparse.ArgumentParser(description="A-Share Alpha Lab: research only")
    commands = parser.add_subparsers(dest="command", required=True)
    fetch = commands.add_parser("fetch", help="fetch unadjusted bars with optional AKShare")
    fetch.add_argument("--symbol", required=True)
    fetch.add_argument("--start", required=True)
    fetch.add_argument("--end", required=True)
    fetch.add_argument("--out", required=True)
    test = commands.add_parser("backtest", help="research one symbol with a CSV")
    test.add_argument("--csv", required=True)
    test.add_argument("--out", required=True)
    news = commands.add_parser("news", help="read configured RSS/Atom feeds")
    news.add_argument("--feeds", required=True)
    news.add_argument("--out", required=True)
    scan = commands.add_parser("scan", help="offline multi-symbol CSV research dashboard")
    scan.add_argument("--input-dir", required=True)
    scan.add_argument("--asof", required=True, help="YYYY-MM-DD, explicit snapshot cutoff")
    scan.add_argument("--max-age-days", type=int, default=5)
    scan.add_argument("--out", required=True, help="canonical JSON report")
    scan.add_argument("--markdown", required=True, help="readable dashboard Markdown")
    evaluate = commands.add_parser("evaluate", help="chronological fixed-rule holdout experiment")
    evaluate.add_argument("--csv", required=True)
    evaluate.add_argument("--warmup", type=int, default=120)
    evaluate.add_argument("--window", type=int, default=60)
    evaluate.add_argument("--out", required=True)
    cockpit = commands.add_parser("cockpit", help="local persistent research and holdings view")
    cockpit.add_argument("--scan", required=True)
    cockpit.add_argument("--holdings", required=True)
    cockpit.add_argument("--previous", help="optional earlier local cockpit JSON")
    cockpit.add_argument("--fundamentals", help="optional local dated filing evidence JSON")
    cockpit.add_argument("--market-radar", help="optional market radar JSON")
    cockpit.add_argument("--portfolio-report", help="optional historical hypothetical portfolio JSON")
    cockpit.add_argument("--out", required=True)
    cockpit.add_argument("--markdown", required=True)
    one = commands.add_parser("run", help="one-command offline snapshot including HTML cockpit")
    one.add_argument("--input-dir", required=True, help="local CSV market history directory")
    one.add_argument("--holdings", required=True, help="local/private holdings JSON")
    one.add_argument("--asof", required=True, help="explicit YYYY-MM-DD snapshot date")
    one.add_argument("--out-dir", required=True, help="new snapshot directory; never overwritten")
    one.add_argument("--fundamentals", help="optional dated financial filings JSON")
    one.add_argument("--benchmark-dir", help="optional local benchmark index CSV directory")
    one.add_argument("--portfolio-first-trade-date", help="optional hypothetical portfolio start date")
    one.add_argument("--eligibility-ledger", help="optional private daily as-known trading-state JSON")
    one.add_argument("--portfolio-starting-cash", type=float, default=100000.0)
    one.add_argument("--portfolio-max-positions", type=int, default=5)
    one.add_argument("--portfolio-allocation-fraction", type=float, default=0.20)
    one.add_argument("--previous", help="previous saved cockpit.json for durable candidates")
    one.add_argument("--max-age-days", type=int, default=5)
    radar = commands.add_parser("radar", help="research-only index trend proxy")
    radar.add_argument("--input-dir", required=True)
    radar.add_argument("--asof", required=True)
    radar.add_argument("--out", required=True)
    radar.add_argument("--max-age-days", type=int, default=5)
    ingest = commands.add_parser("ingest", help="bounded opt-in AKShare daily batch download")
    ingest.add_argument("--symbols", required=True, help="local JSON array of <=30 symbols")
    ingest.add_argument("--start", required=True, help="YYYYMMDD")
    ingest.add_argument("--end", required=True, help="YYYYMMDD")
    ingest.add_argument("--out-dir", required=True, help="new local directory")
    ingest.add_argument("--delay-seconds", type=float, default=2.0)
    ingest.add_argument("--source-terms-confirmed", action="store_true",
                        help="operator has verified the applicable data access terms")
    portfolio = commands.add_parser("portfolio", help="multi-symbol hypothetical cash/equity research, NOT trades")
    portfolio.add_argument("--input-dir", required=True)
    portfolio.add_argument("--first-trade-date", required=True, help="YYYY-MM-DD observed session")
    portfolio.add_argument("--starting-cash", type=float, default=100000.0)
    portfolio.add_argument("--max-positions", type=int, default=5)
    portfolio.add_argument("--allocation-fraction", type=float, default=0.2)
    portfolio.add_argument("--benchmark-csv", help="local unadjusted price reference only")
    portfolio.add_argument("--eligibility-ledger", help="optional daily trading eligibility JSON")
    portfolio.add_argument("--out", required=True)
    validation = commands.add_parser("portfolio-evaluate", help="fixed-rule chronological portfolio folds")
    validation.add_argument("--input-dir", required=True)
    validation.add_argument("--warmup", type=int, default=120)
    validation.add_argument("--window", type=int, default=60)
    validation.add_argument("--starting-cash", type=float, default=100000.0)
    validation.add_argument("--max-positions", type=int, default=5)
    validation.add_argument("--allocation-fraction", type=float, default=0.20)
    validation.add_argument("--eligibility-ledger", help="optional daily trading eligibility JSON")
    validation.add_argument("--out", required=True)
    audit = commands.add_parser("audit-eligibility", help="audit as-known per-session trading status")
    audit.add_argument("--input-dir", required=True)
    audit.add_argument("--ledger", required=True)
    audit.add_argument("--out", required=True)
    refresh = commands.add_parser("refresh", help="immutable incremental CSV snapshot with overlap checks")
    refresh.add_argument("--previous-dir", required=True, help="prior complete manifest-based input")
    refresh.add_argument("--out-dir", required=True, help="new directory, never overwritten")
    refresh.add_argument("--end", required=True, help="YYYYMMDD end date")
    refresh.add_argument("--overlap-days", type=int, default=21)
    refresh.add_argument("--delay-seconds", type=float, default=2.0)
    refresh.add_argument("--source-terms-confirmed", action="store_true")
    args = parser.parse_args()
    if args.command == "refresh":
        result = refresh_snapshot(
            previous_dir=args.previous_dir, out_dir=args.out_dir,
            end=args.end, overlap_calendar_days=args.overlap_days,
            delay_seconds=args.delay_seconds,
            source_terms_confirmed=args.source_terms_confirmed)
    elif args.command == "audit-eligibility":
        histories = {}
        for source in sorted(Path(args.input_dir).glob("*.csv")):
            bars = load_csv(source)
            if bars[0].symbol in histories:
                raise ValueError("DUPLICATE_ELIGIBILITY_CSV_SYMBOL")
            histories[bars[0].symbol] = bars
        result = audit_eligibility_file(histories, args.ledger)
        output = Path(args.out)
        if (output.exists()
                or output.resolve().is_relative_to(Path(args.input_dir).resolve())
                or output.resolve() == Path(args.ledger).resolve()):
            raise ValueError("ELIGIBILITY_AUDIT_OUTPUT_MUST_BE_NEW")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    elif args.command == "portfolio-evaluate":
        result = portfolio_folds_from_directory(
            args.input_dir, warmup_sessions=args.warmup,
            test_sessions=args.window, starting_cash=args.starting_cash,
            max_positions=args.max_positions,
            allocation_fraction=args.allocation_fraction,
            eligibility_ledger=args.eligibility_ledger)
        out = Path(args.out)
        if out.exists() or out.resolve().is_relative_to(Path(args.input_dir).resolve()):
            raise ValueError("PORTFOLIO_EVALUATION_OUTPUT_MUST_BE_NEW_OUTSIDE_INPUT")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    elif args.command == "portfolio":
        settings = PortfolioRules(starting_cash=args.starting_cash,
                                  first_trade_date=args.first_trade_date,
                                  max_positions=args.max_positions,
                                  allocation_fraction=args.allocation_fraction)
        result = portfolio_from_directory(args.input_dir, settings,
                                          benchmark_csv=args.benchmark_csv,
                                          eligibility_ledger=args.eligibility_ledger)
        output = Path(args.out)
        if (output.exists()
                or output.resolve().is_relative_to(Path(args.input_dir).resolve())
                or (args.benchmark_csv and output.resolve() == Path(args.benchmark_csv).resolve())):
            raise ValueError("PORTFOLIO_OUTPUT_MUST_BE_NEW_AND_OUTSIDE_INPUT")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    elif args.command == "radar":
        result = build_market_radar(args.input_dir, asof=args.asof,
                                    max_age_days=args.max_age_days)
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    elif args.command == "ingest":
        symbols = json.loads(Path(args.symbols).read_text(encoding="utf-8"))
        result = batch_ingest(symbols=symbols, start=args.start, end=args.end,
                              out_dir=args.out_dir,
                              delay_seconds=args.delay_seconds,
                              source_terms_confirmed=args.source_terms_confirmed)
    elif args.command == "run":
        result = run_local_pipeline(input_dir=args.input_dir,
                                    holdings_path=args.holdings,
                                    asof=args.asof, out_dir=args.out_dir,
                                    fundamentals_path=args.fundamentals,
                                    previous_path=args.previous,
                                    benchmark_dir=args.benchmark_dir,
                                    portfolio_first_trade_date=args.portfolio_first_trade_date,
                                    eligibility_ledger_path=args.eligibility_ledger,
                                    portfolio_starting_cash=args.portfolio_starting_cash,
                                    portfolio_max_positions=args.portfolio_max_positions,
                                    portfolio_allocation_fraction=args.portfolio_allocation_fraction,
                                    max_age_days=args.max_age_days)
    elif args.command == "fetch":
        bars = download_akshare(args.symbol, args.start, args.end)
        save_csv(bars, args.out)
        result = {"status": "DOWNLOADED_UNADJUSTED_RESEARCH_ONLY", "bars": len(bars), "path": args.out}
    elif args.command == "backtest":
        result = research_backtest(load_csv(args.csv))
        destination = Path(args.out)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    elif args.command == "cockpit":
        outputs = [Path(args.out), Path(args.markdown)]
        inputs = [Path(args.scan), Path(args.holdings)]
        if args.previous:
            inputs.append(Path(args.previous))
        if args.fundamentals:
            inputs.append(Path(args.fundamentals))
        if args.market_radar:
            inputs.append(Path(args.market_radar))
        if args.portfolio_report:
            inputs.append(Path(args.portfolio_report))
        if outputs[0].resolve() == outputs[1].resolve() or any(
                x.resolve() in {p.resolve() for p in inputs} for x in outputs):
            raise ValueError("OUTPUT_MUST_NOT_OVERWRITE_INPUT")
        result = build_from_files(args.scan, args.holdings, args.previous,
                                  args.fundamentals, args.market_radar,
                                  args.portfolio_report)
        for path in outputs:
            path.parent.mkdir(parents=True, exist_ok=True)
        outputs[0].write_text(json.dumps(result, indent=2, ensure_ascii=False),
                              encoding="utf-8")
        outputs[1].write_text(render_cockpit(result), encoding="utf-8")
    elif args.command == "evaluate":
        result = evaluate_file(args.csv, warmup=args.warmup, window=args.window)
        destination = Path(args.out)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, indent=2, ensure_ascii=False),
                               encoding="utf-8")
    elif args.command == "scan":
        result = scan_directory(args.input_dir, asof=args.asof,
                                max_age_days=args.max_age_days)
        output = Path(args.out)
        dashboard = Path(args.markdown)
        if output.resolve() == dashboard.resolve():
            raise ValueError("OUTPUT_PATHS_MUST_DIFFER")
        for path in (output, dashboard):
            path.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False),
                          encoding="utf-8")
        dashboard.write_text(render_dashboard(result), encoding="utf-8")
    else:
        sources = json.loads(Path(args.feeds).read_text(encoding="utf-8"))
        if not isinstance(sources, list) or any(not isinstance(u, str) for u in sources):
            raise ValueError("FEEDS_CONFIG_MUST_BE_URL_LIST")
        result = poll_feeds(sources, args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
