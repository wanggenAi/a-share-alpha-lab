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
- V0.9 experimental multi-symbol portfolio cash, marked equity, realized/unrealized P&L, T+1 and order/skip audit ledger with strict aligned-session and price-gap gates.
- V0.10 optional single-command integration of historical portfolio research into the local HTML cockpit, clearly separated from actual user holdings.
- V0.11 bounded non-overlapping chronological *fixed-rule* portfolio folds with independent cash/equity accounting and no future-bar leakage assertions.
- V0.12 optional manually dispatched PUBLIC ticker research workflow with terms acknowledgement, strict limited inputs and a short-retention artifact; no private holdings or cron.
- V0.13 opt-in per-session as-known-before-preopen trading-status/corporate-action audit and strict fail-closed portfolio gates, with **declared-unverified** source classification.
- V0.14 immutable incremental daily CSV refresh with bounded overlap checks, lineage hashes, partial-batch gating and opt-in data-rights confirmation.

## Important constraints
- Repo is PUBLIC. Never commit local `data/`, `output/`, positions, API keys or paid datasets.
- Unadjusted AKShare bars may have dividend/split distortions. No "validated annualized return" claim.
- No point-in-time universe including delistings, ST, corporate actions, corporate filings, or
  audited fundamentals yet; technical research states MUST NOT become true BUY/SELL advice.
- Time isolation is tested; portfolio accounting is hypothetical, not PIT-universe verified or independently proven profitable.
- No authenticated market/news source has been enabled for hourly unattended collection.
- Strategy and backtest cannot place orders.

## Next priority gates (do not skip)
1. Authentic **source-verified** security status (not operator-declared JSON), true exchange calendar and PIT corporate-action adjustments; V0.13 only enforces declared evidence and abstains on missing records.
2. Authenticate PIT issuer filings (not only user-declared URLs/figures), handle corrections,
   true units, consolidated reporting, share dilution and annual/cumulative comparability.
3. Adjusted-data portfolio backtest with cash/equity curve, benchmarks and realistic session limits;
   independent holdout across PIT universe incl. delistings.
4. Verify permissioned providers and real-world connectivity; implement monitored durable ingestion and a safe opt-in scheduler (V0.14 only supports manual incremental refresh)
   before enabling hourly jobs.
5. Product UI (local dashboard), paper-trading journal and tracked candidate explanations.
6. External independent review before any advisory BUY label.

## Development rule
Before claiming completion: confirm tests on main SHA, source freshness, realistic scope and
non-invention of market returns. Do not force a BUY signal, chase overfitting or use synthetic
market prices outside tests. Keep the sole canonical report as the source of dashboard views.
