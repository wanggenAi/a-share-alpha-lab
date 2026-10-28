# TASK_STATE — A-Share Alpha Lab

Updated: 2026-10-28

## Goal
One practical, auditable research-and-investment decision cockpit:
positions first, persistent long-term candidate queue, concise market/cycle radar,
time-stamped evidence, valuation/financial quality, risk controls and repeatable
data collection. This is decision support, **not an autonomous brokerage bot**.

## Landed
- V0.1 daily OHLCV validation, fixed trend hypothesis, T+1 research simulator, opt-in RSS, offline CI.
- V0.2 local multi-ticker CSV scanning and canonical JSON + Markdown report, fail-closed data screening.
- V0.3 chronological fixed-rule holdout experiments (non-overlapping windows, no future signals).
- V0.4 local holdings, concentration review, persistent research candidates and unified offline cockpit.
- V0.5 optional dated, manually declared filing evidence with as-of publication guards and cash-flow / debt / comparable-period metrics.
- V0.6 atomic one-command offline snapshot workflow with local static HTML dashboard, no overwrites and escaping.
- V0.7 bounded opt-in batch AKShare ingestion with SHA256 manifest and strict partial-data rejection.
- V0.8 optional local benchmark-index technical trend context in the unified cockpit.

## Important constraints
- Repo is PUBLIC. Never commit local `data/`, `output/`, positions, API keys or paid datasets.
- Unadjusted AKShare bars may have dividend/split distortions. No "validated annualized return" claim.
- No point-in-time universe including delistings, ST, corporate actions, corporate filings, or
  audited fundamentals yet; technical research states MUST NOT become true BUY/SELL advice.
- Time isolation is tested; predictive outperformance and true portfolio simulation are NOT proven.
- No authenticated market/news source has been enabled for hourly unattended collection.
- Strategy and backtest cannot place orders.

## Next priority gates (do not skip)
1. Data provenance schema and persistent local storage; true trading calendar and PIT corporate actions.
2. Authenticate PIT issuer filings (not only user-declared URLs/figures), handle corrections,
   true units, consolidated reporting, share dilution and annual/cumulative comparability.
3. Adjusted-data portfolio backtest with cash/equity curve, benchmarks and realistic session limits;
   independent holdout across PIT universe incl. delistings.
4. Opt-in verifiable sources, rate limits/retention, ingestion monitoring and safe scheduler
   before enabling hourly jobs.
5. Product UI (local dashboard), paper-trading journal and tracked candidate explanations.
6. External independent review before any advisory BUY label.

## Development rule
Before claiming completion: confirm tests on main SHA, source freshness, realistic scope and
non-invention of market returns. Do not force a BUY signal, chase overfitting or use synthetic
market prices outside tests. Keep the sole canonical report as the source of dashboard views.
