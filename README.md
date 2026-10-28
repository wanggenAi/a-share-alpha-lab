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

## V0.8 optional benchmark-index technical radar

If you have **permissioned locally verified index data** in the same
`symbol,date,open,high,low,close,volume` CSV format, put one index per file
in `data/benchmarks/` (1–10 files). Then:

```bash
alpha-lab radar --input-dir data/benchmarks --asof 2026-10-28 \
  --out output/radar.json

alpha-lab run --input-dir data/prices --asof 2026-10-28 \
  --holdings data/holdings.json --benchmark-dir data/benchmarks \
  --out-dir output/2026-10-28
```

The HTML dashboard will show how many supplied indices exhibit rising,
falling, or mixed MA20/MA60 technical trends. If any input index is stale or
blocked, the **aggregate trend is unavailable**. It does not scrape indices,
verify ticker names, infer industry rotation or predict an economic cycle.
An arbitrary sample of 1–10 indices must not be described as market-wide breadth.

## V0.9 multi-symbol experimental portfolio accounting

The research command uses a **locally stored**, aligned, main-board-only OHLCV panel. Example (the start date must actually occur in all input series, after at least 65 prior observations):

```bash
alpha-lab portfolio --input-dir data/prices-20261027 \
  --first-trade-date 2024-01-02 --starting-cash 100000 \
  --max-positions 5 --allocation-fraction 0.20 \
  --out output/portfolio-research.json
```

The report includes next-open **hypothetical** buys from prior-close signals, failed/skipped orders with reasons, T+1 exits, 100-share lots, buy/sell fees, capital and cash occupation, open positions, daily marked equity, realized/unrealized P&L, drawdown and turnover. The system validates cash/P&L reconciliation on **every observed session**. No intraday sell proceeds are used to buy at the same day's open. Optional `--benchmark-csv` adds only an **unadjusted price reference**, not a total-return alpha comparison. It never places orders.

**Hard limits:** all stock series must share the same set of exact daily sessions; missing real suspension rows block the experiment. Only selected Shanghai/Shenzhen main-board identifiers and a simplified 10% price limit are included; ST, IPO and special no-limit sessions are **unverified**. Unexplained >10.5% gaps are blocked as possible unmodeled corporate actions. No dividends/splits, PIT security master/delisting population, credible executable stop fills, portfolio-level walk-forward fitting or independent out-of-sample profitability claim. Synthetic tests are **not evidence of profitable investment performance**.

## V0.10 single-cockpit integration for hypothetical portfolio study

When all daily ticker CSVs have the **same verified trading dates** and the
most recent observed session matches `--asof`, the offline snapshot can
optionally include V0.9 research in the same HTML cockpit:

```bash
alpha-lab run --input-dir data/prices --asof 2026-10-28 \
  --holdings data/holdings.json \
  --portfolio-first-trade-date 2024-01-02 \
  --portfolio-starting-cash 100000 \
  --portfolio-max-positions 5 \
  --portfolio-allocation-fraction 0.20 \
  --out-dir output/2026-10-28-with-research
```

**All dates in the example are illustrative**: first-trade date must actually
exist in the data and provide 65 observed warmup sessions. The optional
settings create an archived `portfolio_research.json` ledger and show
a **separately labeled hypothetical research** equity curve in the
canonical `cockpit.json`, `cockpit.md` and local `cockpit.html`.
The visible simulation summary is deliberately distinct from user-provided
**actual holdings**, market value and cash. Never confuse simulated strategy
performance with your broker account or evidence of a profitable edge.

The standalone `alpha-lab cockpit` command accepts
`--portfolio-report output/portfolio-research.json` as an alternative
to executing the simulation in `alpha-lab run`.
Reports must end on the exact snapshot as-of date; mismatches, invalid equity
or future-dated simulation results are rejected.

## V0.11 fixed multi-symbol chronological portfolio folds

```bash
alpha-lab portfolio-evaluate --input-dir data/prices \
  --warmup 120 --window 60 --starting-cash 100000 \
  --max-positions 5 --allocation-fraction 0.20 \
  --out output/portfolio-folds.json
```

This provides a set of **non-overlapping, independent historical experiments**
with frozen strategy parameters. Every fold sees only observations through its
own final session, starts from the same cash balance, uses earlier sessions
for indicator warmup, and reports its own marked equity curve, drawdown,
closed trades and open (unliquidated) positions. The mean fold return
is **not compounded and not annualized**.

This is strictly an additional temporal reliability check, **not** a proven
investment strategy, not parameter-fitting walk-forward optimization,
and not a proper investable benchmark comparison. The user-provided ticker
universe can still exhibit survivorship bias; it lacks point-in-time
delisting, issuer corporate actions, ST/IPO status and independently
audited adjusted prices. Never treat non-overlapping folds on a
hindsight-selected universe as genuine market-wide out-of-sample proof.

## V0.12 manual PUBLIC market-research workflow

After this workflow is merged into the default branch, open the repository
**Actions → Manual public A-share research → Run workflow**. Enter up to
10 **PUBLIC** six-digit ticker identifiers, start date `YYYYMMDD`, optional
end date, and manually check the provider-terms acknowledgement.
This is a **manual-only** workflow. It has **NO scheduled cron** and
**NO broker execution**, and it does not accept private holdings, account
details or secrets.

If the upstream AKShare market feed responds and all symbols pass the manifest
checks, the workflow publishes a short-retention ZIP artifact with
`scan.json`, `dashboard.md`, `dashboard.html` and provenance metadata.
If any ticker download fails, it marks the batch incomplete and does **not**
produce a misleading finished dashboard; the partial manifest can help debug.

**Public repository warning:** workflow inputs, logs and downloadable
artifacts may be visible to others. Never enter personal holdings,
private watchlists, passwords, licensed confidential data or client secrets.
All datasets are unadjusted and not independently validated. A green offline
CI test does **not** prove this manual workflow will fetch current market
data: provider connectivity, rate limits and access rights must be checked in
a real manually dispatched workflow run. Running GitHub Actions may consume
account quota. See the separate private/local cockpit workflow for holdings.


## V0.13 opt-in point-in-time **declared** trading-status audit

A research file is not proof that shares were tradable. On your **private
local** machine, collect exchange/issuer evidence for **every symbol/date**
in the downloaded OHLCV panel. Keep it under ignored \`data/\`. Example
**synthetic single session** (NOT a real verified issuer status):

```json
{
  "schema_version": "1",
  "sessions": [
    {
      "symbol": "600519",
      "date": "2025-01-02",
      "state": "REGULAR",
      "corporate_action": "NONE_DECLARED",
      "observed_at": "2025-01-02T09:00:00+08:00",
      "source_url": "https://example.com/synthetic-status"
    }
  ]
}
```

A real ledger needs **one record for every stock session** in the input price
series. For studies, the program requires operator-declared evidence available
before **09:15 China time** that session. Missing, later-published, ST,
suspended, delisted or IPO-special statuses, or a declared dividend/split/
unknown action, block the strict portfolio research. This **does not**
automatically adjust cash dividends or infer full listing histories.
It also does NOT certify that the user-declared source URLs are genuine.

```bash
alpha-lab audit-eligibility --input-dir data/prices \
  --ledger data/eligibility.json --out output/eligibility-audit.json

alpha-lab portfolio --input-dir data/prices \
  --first-trade-date 2025-05-08 \
  --eligibility-ledger data/eligibility.json \
  --out output/portfolio-gated.json

# Also works for portfolio-evaluate and for alpha-lab run with --portfolio-first-trade-date
```

**Fail closed**: even one missing/unsafe session blocks portfolio simulation
when \`--eligibility-ledger\` is supplied. Without a ledger, legacy
hypothetical reports remain possible but explicitly say
\`NOT_PROVIDED_UNVERIFIED\`. The audit JSON lists exactly which
dates/symbols lack or contradict eligibility declarations. A zero-block
**declared** ledger is not independently source-verified and not investable.
Any calendar or corporate-action evidence of real trading requires
verification against authoritative exchange/issuer records.
