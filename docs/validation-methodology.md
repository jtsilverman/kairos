# Validation methodology (how to test + deploy any candidate strategy)

Family-agnostic statistical methodology behind the deploy gate in `docs/framework.md`.
Source-backed (Bailey & Lopez de Prado; skfolio CPCV), adopted 2026-07-04 from a
Perplexity Pro consult on validating small-sample, regime-dependent, lottery-convex
options strategies; proven in the gap-open honest re-measure (implementation template:
`scripts/archive/validation_*.py`). Numbers below assume the standing data constraints
(~2yr real options marks, one regime; 11.5yr stock daily) — re-check them per candidate.

## 1. Out-of-sample estimation (never a single split)

- **PRIMARY: purged walk-forward**, 3-4 non-overlapping chronological segments, with
  PURGE (drop train trades whose holding period overlaps a test trade in calendar time)
  + EMBARGO (small buffer after each test fold). Multiple real OOS reads instead of one
  lucky path.
- **SECONDARY: block bootstrap of TRADE-level P&L** (resample contiguous blocks, e.g.
  calendar quarters, preserving serial dependence) → CIs on CAGR / maxDD / tail-ratio.
  Answers "how much does the result depend on WHEN the rippers landed."
- **CPCV/CSCV: light, only to compute PBO.** Full CPCV as the primary estimator is
  overkill at ~2yr and easy to mis-implement.

## 2. Overfitting quantification (tuning knobs = overfitting)

- **PBO (Probability of Backtest Overfitting)** via CSCV over the searched grid: how
  often the in-sample-best config fails to stay top-half OOS. Gate: **PBO ≤ 0.30**.
- **Deflated Sharpe Ratio**: corrects Sharpe for trials tried, sample length, fat tails.
  Track EVERY config tried; cluster correlated ones for the effective trial count.
  REPORTED, never gated (near-zero power on lottery-convex books).
- **Cap independent knobs at 2-3.** More than ~10-20 distinct configs on a 2yr sample =
  assume high overfit; lean on PBO to filter. Freeze tail-truncation knobs (profit-take
  levels) at lock — tuning the tail on short samples is a classic trap.

## 3. Metrics (Sharpe is NOT primary for a convex book)

Sharpe reflects the many small stops, not the rare rippers that make the money. Use:
- **Total return vs SPY buy-hold** (excess return + maxDD) — the real bar.
- **Tail ratio** (95th pct / |5th pct|) > 1, **gain-to-pain** > 1, **skew > 0**.
- **Block-bootstrap of the trade-return distribution** → P(underperform SPY), P(ruin).
Keep Sharpe/DSR as overfit checks, not targets.

## 4. Synthetic (long-history stock) data

VALID for regime characterization and stress-testing the LOGIC across 2015/2018/2020/2022.
DANGEROUS as a performance claim: BS single-vol ignores skew/term-structure/vol-crush,
mid fills ignore spread, today's-winners universes are survivorship-biased. Treat
synthetic CAGR/tail as an UPPER BOUND; only real-marks results pass the gate.

## 5. Deploy bar (backtest → live)

- Backtest bar: walk-forward positive on the convexity metrics + PBO ≤ 0.30.
- Then a **3-6 month paper OR small-size forward test** — the only true OOS is live.
  Log fills + slippage-vs-mark where the backtest lies most.
- **Pre-committed KILL thresholds frozen at lock time**: forward CAGR / gain-to-pain
  below the 5-10% worst bootstrap quantile; forward maxDD >> backtest worst; tail-ratio
  < 1 or skew turns negative; systematic fills at bid not mid. Any → disarm.
- Scale to full size in steps only after the forward test aligns with the bootstrap CIs.
