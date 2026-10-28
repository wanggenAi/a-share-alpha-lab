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
    args = parser.parse_args()
    if args.command == "fetch":
        bars = download_akshare(args.symbol, args.start, args.end)
        save_csv(bars, args.out)
        result = {"status": "DOWNLOADED_UNADJUSTED_RESEARCH_ONLY", "bars": len(bars), "path": args.out}
    elif args.command == "backtest":
        result = research_backtest(load_csv(args.csv))
        destination = Path(args.out)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
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
