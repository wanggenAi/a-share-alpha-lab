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
    cockpit.add_argument("--out", required=True)
    cockpit.add_argument("--markdown", required=True)
    one = commands.add_parser("run", help="one-command offline snapshot including HTML cockpit")
    one.add_argument("--input-dir", required=True, help="local CSV market history directory")
    one.add_argument("--holdings", required=True, help="local/private holdings JSON")
    one.add_argument("--asof", required=True, help="explicit YYYY-MM-DD snapshot date")
    one.add_argument("--out-dir", required=True, help="new snapshot directory; never overwritten")
    one.add_argument("--fundamentals", help="optional dated financial filings JSON")
    one.add_argument("--previous", help="previous saved cockpit.json for durable candidates")
    one.add_argument("--max-age-days", type=int, default=5)
    ingest = commands.add_parser("ingest", help="bounded opt-in AKShare daily batch download")
    ingest.add_argument("--symbols", required=True, help="local JSON array of <=30 symbols")
    ingest.add_argument("--start", required=True, help="YYYYMMDD")
    ingest.add_argument("--end", required=True, help="YYYYMMDD")
    ingest.add_argument("--out-dir", required=True, help="new local directory")
    ingest.add_argument("--delay-seconds", type=float, default=2.0)
    ingest.add_argument("--source-terms-confirmed", action="store_true",
                        help="operator has verified the applicable data access terms")
    args = parser.parse_args()
    if args.command == "ingest":
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
        if outputs[0].resolve() == outputs[1].resolve() or any(
                x.resolve() in {p.resolve() for p in inputs} for x in outputs):
            raise ValueError("OUTPUT_MUST_NOT_OVERWRITE_INPUT")
        result = build_from_files(args.scan, args.holdings, args.previous,
                                  args.fundamentals)
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
