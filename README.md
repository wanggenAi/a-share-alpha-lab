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

## V0.4 local holdings + persistent research cockpit

Private input `data/holdings.json` (LOCAL ONLY — NOT in GitHub):

```json
{
  "asof": "2026-10-28",
  "cash": 1000,
  "positions": [
    {"symbol": "600519", "shares": 100, "cost_basis_per_share": 10}
  ]
}
```

**The numbers above are a synthetic schema example, NOT actual market prices or positions.**

```bash
alpha-lab cockpit --scan output/scan.json --holdings data/holdings.json \
  --out output/cockpit.json --markdown output/cockpit.md
# For next as-of report, preserve candidates using:
alpha-lab cockpit --scan output/next_scan.json --holdings data/next_holdings.json \
  --previous output/cockpit.json --out output/next_cockpit.json \
  --markdown output/next_cockpit.md
```

The cockpit shows local holdings with marked values *only when every holding
has a usable price*, review-only action labels, a 30%-weight concentration
flag, and a candidate queue that does not vanish when a technical setup expires.
The `--previous` input must point to an earlier local cockpit; archive it
before overwriting. No market-wide coverage, fundamental research, adjusted
total-return series, broker reconciliation or execution is provided.
**Keep all position information and cockpit outputs out of this public repo.**

## V0.5 dated fundamental evidence (offline/manual)

For an optional dated financial source, create local `data/fundamentals.json`
using `config/fundamentals.SYNTHETIC.example.json` **only as schema guidance**;
the example has fabricated figures and links, deliberately NOT real issuer data.
Run with `alpha-lab cockpit ... --fundamentals data/fundamentals.json`.

Inputs explicitly distinguish `fiscal_end` from `published_at`: a filing
is unavailable to earlier snapshots even if it covers an earlier period.
All figures use **CNY yuan**, with `FY`, `Q1`, `H1`, or `9M` reporting
periods. Similar-period prior-year revenue/profit comparisons are made only
when both dated filings were available as-of. Reported cash conversion,
liability ratio, and optional **FY-only** PE/PB are *descriptive review metrics*.
No forward-filled filings, guesswork for missing values, TTM inference,
corporate-action restatements, or independent link/content verification.
Negative-profit PE and missing valuation information remain unknown.

**Review flags are not company ratings**. The financial source URLs and
the user-supplied figures are *declared*, not verified by this program;
verify against primary exchange/issuer filings and relevant accounting units
before any real investment decision. Never use synthetic example amounts for investing.

## V0.6 open the local HTML investment research cockpit

Once you have actual **permitted, user-verified daily CSV inputs** in
`data/prices/`, and a local `data/holdings.json` for the same as-of date,
generate a whole, immutable private snapshot in **one command**:

```bash
alpha-lab run --input-dir data/prices --asof 2026-10-28 \
  --holdings data/holdings.json --out-dir output/2026-10-28 \
  --fundamentals data/fundamentals.json
```

The optional `--fundamentals` argument may be omitted. Open
`output/2026-10-28/cockpit.html` locally in a browser. Also produced:
`scan.json`, `cockpit.json`, `cockpit.md`. The output directory **must not
already exist**: this prevents silent edits to archived decisions.
For the following day's snapshot, pass
`--previous output/2026-10-28/cockpit.json`, use the following date's holdings
and input CSVs, and choose a new output directory. Save historical snapshots.

HTML is local-only and embeds no remote scripts/assets or account integrations;
all user/data text is escaped. It is NOT a live hosted financial app, and it
does not fetch current market/issuer data or execute orders. The above commands
are procedural examples, NOT evidence that 2026-10-28 market feeds were loaded.

## V0.7 bounded opt-in batch market data input

Prepare an **untracked local** `data/symbols.json`, for example
`["600519", "000001"]` (these are ticker **identifiers**, not stock picks).

After *you* have reviewed AKShare/upstream provider access terms:

```bash
alpha-lab ingest --symbols data/symbols.json --start 20220101 --end 20261028 \
  --out-dir data/2026-10-28-prices --source-terms-confirmed
```

Only up to 30 explicit symbols per call; minimum 0.5 second interval,
default 2 seconds. Each new snapshot has CSVs and a local SHA256 manifest
with requested symbols, retrieval time, source label and any failures.
**PARTIAL_BLOCKED** manifest prevents the scanner from silently accepting
an incomplete batch. Tampered or additional/missing files are detected.
Unmanaged legacy CSV files remain usable but are visibly labeled unverified.

Use `--input-dir data/2026-10-28-prices` in `alpha-lab run`. The downloader
remains **unadjusted, opt-in and unscheduled**. AKShare is an optional dependency
(`pip install -e ".[data]"`), not a guaranteed or licensed market-data
subscription. This is NOT point-in-time verified historical fundamental data
and is not a substitute for proper adjusted data/benchmark validation.
