"""Manual, inspectable research commands."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .backtest import research_backtest
from .data import download_akshare, load_csv, save_csv
from .intelligence import poll_feeds


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
    else:
        sources = json.loads(Path(args.feeds).read_text(encoding="utf-8"))
        if not isinstance(sources, list) or any(not isinstance(u, str) for u in sources):
            raise ValueError("FEEDS_CONFIG_MUST_BE_URL_LIST")
        result = poll_feeds(sources, args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
