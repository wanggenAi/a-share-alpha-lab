# A-Share Alpha Lab

Evidence-driven A-share research, **not a brokerage trading bot**.

## Purpose
Start with one transparent hypothesis: a rising MA20/MA60 trend, a recent pullback, and a close that starts to recover. Test it using next-session execution, transaction costs, T+1, conservative same-bar stop-first assumptions, and data checks. No historical or live BUY should be described as proven before independent evaluation.

## Quick start (Python 3.11+)
1. Create an environment and run: `python -m pip install -e ".[dev]"`
2. Test: `pytest -q`
3. Optional actual market download: `python -m pip install -e ".[data]"`
4. Download one symbol: `alpha-lab fetch --symbol 600519 --start 20220101 --end 20261023 --out data/600519.csv`
5. Research trades: `alpha-lab backtest --csv data/600519.csv --out output/research.json`
6. Optional manually configured RSS: copy `config/feeds.example.json` to `config/feeds.json`, insert sources whose permissions and access you have verified, then run `alpha-lab news --feeds config/feeds.json --out data/news.jsonl`.

Nothing here places a brokerage order. The backtest reports *experimental trade statistics*, not verified annualized returns. The downloaded daily data are **unadjusted**: corporate actions must be handled before trusting long-history results. The simplified 10% limit model supports only ordinary Shanghai/Shenzhen main-board shares and is not a complete matching engine. No future-data lookups are permitted for signals.

## Operating rules
- One canonical research result per run. Research signals are NOT executable trading recommendations.
- Missing or invalid price data: fail closed. No synthetic substitute in production.
- Explicit event source, publication time (or unknown), collection time, and URL. Headlines are not automatically 'bullish' or 'bearish'.
- No secrets, actual account details, positions, private data, or licensed scraped content in the repo. **The repository is currently public.**
- Initially **CI only**. Do not activate hourly news scheduling until sources, persistence and cost constraints have passed verification.

## Structure
- `src/alpha_lab/data.py` — historical daily data validation, CSV and optional AKShare ingestion
- `src/alpha_lab/strategy.py` — candidate signal from only known bars
- `src/alpha_lab/backtest.py` — single-symbol research trade simulator
- `src/alpha_lab/intelligence.py` — bounded, opt-in RSS/Atom collection with deduplication
- `src/alpha_lab/cli.py` — executable entry points
- `tests/` — synthetic, deterministic regression tests

## Required before real decisions
(1) verified point-in-time ticker universe and delistings, (2) corporate-action-adjusted total-return prices without forward leakage, (3) realistic limit/suspension and order execution, (4) walk-forward out-of-sample experiments with fixed search budgets and holdout, (5) portfolio-level equity curves and benchmarks, (6) live feed provenance and freshness, (7) a human-reviewed execution dashboard.

Development gates: **data integrity → credible backtest → forward paper trading → advisory dashboard**. Never optimize solely for forcing BUY signals.

## V0.2 offline candidate scan and dashboard

This reads **local CSV files only** (same schema as `alpha-lab fetch`), without downloading or fabricating prices:

```bash
alpha-lab scan --input-dir data --asof 2026-10-28 --max-age-days 5 \
  --out output/scan.json --markdown output/dashboard.md
```

It creates **one canonical JSON report** and a human-readable Markdown view. Files with invalid schema, stale/future dates, insufficient history, recent zero volume, or duplicate tickers are explicitly rejected, not silently omitted. `WATCH_SIGNAL` means a technical *research* pattern matched, `WAIT_PRICE` means a rising trend is near MA20 without confirmation, and `REJECT` means the setup or data checks failed. None is a verified `BUY` signal.

* The scan requires explicit `--asof` and only reads `*.csv` at the supplied directory's top level.
* `--max-age-days` measures **calendar days**, not trading sessions; long public holidays may cause conservative stale rejections.
* No fundamentals, PE/PB, cash flow, ST status, corporate action adjustments, or live order book are yet validated.
* Never commit private holdings or downloaded/paid market feeds to this public repository. The default `data/` and `output/` directories are git-ignored.
* Next gate: verified adjusted point-in-time data, walk-forward evaluation, and portfolio-level evidence, **before** any executable investment recommendation.

## V0.3 fixed-rule chronological holdout

```bash
alpha-lab evaluate --csv data/600519.csv --warmup 120 --window 60 --out output/evaluation.json
```

Non-overlapping 60-observation holdout windows use 120 earlier observations
for indicator warmup. Each experiment sees **no bars beyond its own test end**.
Transactions are initiated only from signals dated inside the holdout window.
Open positions at fold end are censored; trades are not carried across folds.
Statistics are descriptive, **not** statistically significant evidence of edge.
The passive close-change is a *reference*, not a total-return benchmark.
This fixed-rule run is **not fitting/re-optimizing a model** and does not
address survivorship bias, corporate actions or point-in-time universes.
