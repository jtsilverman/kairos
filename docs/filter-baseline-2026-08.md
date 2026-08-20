# Filter baseline: what the market and the screen actually did

Measured 2026-08-15/17, before any filter change. Every number here is the
pre-tuning baseline the `funnel-loop` spec is read against. Scripts lived in the
session scratchpad and are reproducible from the method notes below; the numbers
are the record.

Source for all of it: Polygon grouped-daily (`fetch_grouped_daily`, cached in
`code/data/polygon-cache.sqlite`, which is `polygon.DEFAULT_CACHE_PATH`; a
`data/polygon-cache.sqlite` written by scratch scripts run from the repo root
was stale and is deleted). A name appears iff it traded that day, so
later-delisted names are present on their live dates and the sample is
survivorship-clean.

**Liquid universe definition used throughout:** close >= $5, close x volume >=
$5M on the entry session, ticker alphabetic and <= 4 characters (drops warrants,
units, preferreds). ETFs remain in the universe: named caveat, not corrected.

**Alpha definition:** matches `scripts/score_rewind.py`. Entry = first session
strictly after the as-of date. Exit = first session on/after as-of + horizon.
alpha = ticker return - SPY return over that window.

---

## 1. Market base rate: how many stocks beat SPY at all

22 monthly blocks, first of month 2024-09-01 through 2026-06-01. Windows overlap
(monthly starts, 8-week windows), so 22 blocks hold roughly 11 independent
windows.

| Horizon | Blocks | Name-blocks | Pooled beat rate | Range across blocks | Median stock alpha |
|---|---|---|---|---|---|
| 56 days | 22 | 80,901 | **0.4361** | 0.254 to 0.624 | -1.58% |
| 84 days | 21 | 76,455 | **0.4163** | 0.267 to 0.617 | -2.64% |

**Reading.** Fewer than half of liquid US stocks beat SPY over 2 to 3 months,
and the median stock trails the index. Right skew: a few large winners carry the
index above the typical stock. Any pool that beats SPY more than ~44% of the
time over 8 weeks is already above the market.

## 2. Does the current screen help? Matched dates, screen vs market

Same as-of date, same horizon, screen survivors against the whole liquid
universe. "Top-decile lift" = the screen's share of names landing in the
market's top 10% of alpha, divided by 0.10. Lift 1.0 = no information.

| Cohort | H | Screen beat | Market beat | Screen mean alpha | Top-decile lift |
|---|---|---|---|---|---|
| 2026-02-02 | 56 | 0.404 | 0.540 | -0.010 | 1.75 |
| 2026-02-02 | 84 | 0.509 | 0.361 | +0.111 | 3.68 |
| 2026-03-02 | 56 | 0.733 | 0.330 | +0.143 | 4.40 |
| 2026-03-02 | 84 | 0.640 | 0.274 | +0.199 | 4.67 |
| 2026-04-01 | 56 | 0.548 | 0.254 | +0.035 | 1.92 |
| 2026-04-01 | 84 | 0.507 | 0.342 | +0.055 | 2.74 |
| 2026-05-01 | 56 | 0.559 | 0.516 | +0.061 | 2.15 |
| 2026-05-01 | 84 | 0.258 | 0.441 | -0.064 | 0.97 |
| 2026-06-01 | 56 | 0.175 | 0.624 | -0.156 | 0.31 |

Market n per date: 3,845 to 4,172. Screen n: 57 to 97.

**Reading.** The screen's edge sits in the tail, not the hit rate. It lands
1.75x to 4.67x its share of the market's top decile in 7 of 9 closed windows.
February at 56 days shows the shape: the screen's hit rate TRAILS the market
(0.404 vs 0.540) while its top-decile lift is 1.75. Fewer winners, bigger ones.

**The failure mode is a whole-month inversion.** June 2026: the market beat rate
ran 0.624 and the screen returned 0.175 with a 0.31 lift. The screen is a bet on
momentum's sign holding, and June is the month momentum reversed.

## 3. Full-survivor beat rates on the rewind screens

Every survivor, not the drawn cohort. Supersedes the drawn-20 numbers in
`docs/feature-study-rewind.md` for population-level reads.

| Cohort | Survivors | 8wk beat | 12wk beat | Delta |
|---|---|---|---|---|
| 2026-02-02 | 57 | 23/57 = 0.404 | 29/57 = 0.509 | +0.105 |
| 2026-03-02 | 75 | 55/75 = 0.733 | 48/75 = 0.640 | -0.093 |
| 2026-04-01 | 73 | 40/73 = 0.548 | 37/73 = 0.507 | -0.041 |
| 2026-05-01 | 93 | 52/93 = 0.559 | 24/93 = 0.258 | -0.301 |
| 2026-06-01 | 97 | 17/97 = 0.175 | open until 2026-08-24 | n/a |
| **pooled** | 395 | 187/395 = **0.4734** | 138/298 = **0.4631** | -0.010 |

**Reading.** Pooled, 8 weeks and 12 weeks are near-identical (0.473 vs 0.463).
Per cohort they differ a lot and the sign flips: May drops 0.30. Switching the
frozen horizon from 8 weeks to 12 buys nothing pooled and costs a scorer re-pin
plus a February re-run. The horizon stays at 56 days.

The screen pools to 0.473 against the market's 0.436. The hit-rate edge is 3.7
points.

## 4. Does any price feature predict alpha stably?

22 monthly blocks, ~80,000 name-blocks, Spearman of each entry-known feature vs
forward 56-day alpha. Price and liquidity features only: grouped daily carries no
fundamentals.

| Feature | Mean rho | Median | % same sign | Min | Max |
|---|---|---|---|---|---|
| `ret_21d` | +0.032 | +0.026 | 68% | -0.266 | +0.194 |
| `ret_63d` | +0.017 | +0.010 | 55% | -0.301 | +0.246 |
| `ret_126d` | +0.029 | +0.026 | 64% | -0.273 | +0.256 |
| `ret_252d` | +0.056 | +0.088 | 68% | -0.253 | +0.223 |
| `log_dollar_vol` | +0.004 | +0.003 | 55% | -0.065 | +0.105 |
| `price` | +0.012 | +0.011 | 59% | -0.121 | +0.111 |

**Reading.** Nothing holds. The largest mean correlation is `ret_252d` at
+0.056, and sign stability tops out at 68%, near a coin flip. The block-to-block
swing dwarfs the mean: `ret_63d` runs -0.301 to +0.246 around a mean of +0.017.

The one consistent fact is that momentum's SIGN is set by the regime. June 2026
shows every momentum window at -0.25 to -0.30, which is the month the screen
returned 0.175.

This confirms the U6 finding (`docs/feature-study-rewind.md`, 60 names) at
1,300x the sample size. **No numeric feature ranks stably. A filter change
justified by one block's correlation is fitting noise.**

## 5. Is there a cheap EXCLUSION rule? Yes, exactly one.

6 blocks, 10-week (70-day) windows, starts every two months 2025-07-01 through
2026-05-01. ~3,400 to 3,900 liquid names per block. Each feature split into
deciles at entry; "capture" = that decile's share of names landing in the
market's top alpha decile. 0.10 = no information. Sum of capture across deciles
= 1.0, so capture IS the share of all big winners living in that decile.

Volatility proxy = mean daily (high - low) / close over 8 sampled sessions in
the prior 56 days.

**vol_proxy**

| Decile | Mean capture | Worst block | Best block | Mean beat rate |
|---|---|---|---|---|
| D1 low | **0.000** | 0.000 | **0.003** | 0.236 |
| D2 | **0.006** | 0.000 | **0.025** | 0.419 |
| D3 | 0.026 | 0.005 | 0.049 | 0.423 |
| D4 | 0.029 | 0.020 | 0.041 | 0.401 |
| D5 | 0.054 | 0.029 | 0.096 | 0.409 |
| D6 | 0.086 | 0.065 | 0.110 | 0.438 |
| D7 | 0.133 | 0.103 | 0.167 | 0.430 |
| D8 | 0.169 | 0.137 | 0.225 | 0.458 |
| D9 | 0.219 | 0.173 | 0.256 | 0.482 |
| D10 high | 0.277 | 0.210 | 0.347 | 0.462 |

**ret_252d** (U-shaped, cannot exclude)

| Decile | Mean capture | Mean beat rate |
|---|---|---|
| D1 worst | 0.149 | 0.389 |
| D2 | 0.108 | 0.406 |
| D3 | 0.069 | 0.331 |
| D4 | 0.044 | 0.319 |
| D5 | 0.045 | 0.363 |
| D6 | 0.050 | 0.450 |
| D7 | 0.059 | 0.431 |
| D8 | 0.083 | 0.477 |
| D9 | 0.149 | 0.494 |
| D10 best | 0.245 | 0.495 |

**ret_63d** is the same U shape: D1 0.132, D5 0.039, D10 0.244.

**dollar_vol** is flat: 0.071 to 0.119 across all ten deciles. No exclusion.

**price** tilts the wrong way for a floor: D1 (cheapest) captures 0.193, D10
captures 0.083. A price floor costs big winners.

**Reading.**

1. **Volatility is a real exclusion rule.** The bottom 20% by daily range holds
   0.6% of all big winners and its worst single block reached 2.5%. The bottom
   30% holds 3.2%. Cutting vol D1-D3 removes 30% of the field and keeps 96.8% of
   the big winners. D1 also beats SPY only 23.6% of the time, below the market's
   ~43.6%: those names both cannot move and lose more often.
2. **Momentum cannot exclude, because it is U-shaped.** `ret_252d` D1 (the worst
   12-month losers) captures 0.149, the second-richest decile after D10's 0.245.
   The screen's RS >= 90 admission takes only D10 and discards the D1 tail.
   D1's beat rate is 0.389, BELOW the market's 0.436, so admitting it would raise
   big-winner recall and LOWER the pool's base rate. Rejected on 2026-08-17
   (see `specs/vision.md` decision log): the target is winners inside the pool,
   not market-wide recall.
3. **Size and price cannot exclude.**

## 6. Premove screen: the revisions gate

Live screen 2026-07-10 only. Removing the revisions gate roughly doubles the
premove pool.

| Exclusion reason | Names | Passes without the gate |
|---|---|---|
| survivors today | 60 | already passing |
| `revisions_negative` | 24 | yes |
| `data_error:MissingEstimatesError` | 35 | yes |
| `data_error:MissingFactError` | 57 | no |
| `fundamentals` | 22 | no |
| `industry` | 17 | no |
| `rs_not_rising` | 92 | no |
| `rs_prior_unrankable` | 1 | no |

Without the gate: 60 + 24 + 35 = **119** names.

**Partial outcome read, NOT the 8-week number.** Entry 2026-07-13, last close
2026-08-13 (31 days), SPY +3.9%. Eight weeks closes 2026-09-04; twelve weeks
closes 2026-10-02.

| Group | n | Beat SPY | Mean alpha | p10 to p90 |
|---|---|---|---|---|
| gate PASS | 60 | 0.367 | -0.020 | -0.133 to +0.163 |
| cut: `revisions_negative` | 24 | 0.333 | -0.052 | -0.212 to +0.123 |
| cut: `estimates_missing` | 35 | **0.657** | **+0.014** | -0.022 to +0.069 |

**Reading.** The gate separates PASS from `revisions_negative` in the right
direction and weakly: 0.034 on hit rate at n=60 vs n=24 is noise. The 35 names
with no analyst coverage beat at 0.657 with positive mean alpha and a narrow
spread, which points at a liquidity effect rather than a verdict on the gate.
Re-run at the real 8-week close on 2026-09-04 before drawing any conclusion.

**Hard constraint:** the premove screen CANNOT be rewound. Its defining gate is
`snap.positive` in `run_premove_screen`, the estimate-revisions gate, and no
historical vintage of estimates exists at any accessible provider. Rewinding it
means applying today's revisions to a past field, which is lookahead. A real
premove base rate arrives live on 2026-10-02.

---

## 7. The 15-block run of record (2026-08-17, `scripts/score_filter.py`)

The first measurement of the screen OUTSIDE the 2026 window. Sections 2 and 3
scored five cohorts, all from Feb to Jun 2026. This scores 13 blocks from
2024-09 to 2025-11 under PIT gates. Market universe excludes ETFs (the
steering read); the ETF-included reproduction matches sections 2 and 3 exactly.

| Block | Role | n | market n | lift | beat | mkt beat | compl |
|---|---|---|---|---|---|---|---|
| 2024-09-03 | train | 51 | 2420 | 1.96 | 0.588 | 0.387 | 0.980 |
| 2024-10-01 | train | 57 | 2449 | 2.28 | 0.702 | 0.487 | 0.965 |
| 2024-11-01 | train | 51 | 2529 | 2.55 | 0.627 | 0.342 | 0.961 |
| 2024-12-02 | train | 71 | 2597 | 1.27 | 0.338 | 0.375 | 0.986 |
| 2025-01-02 | train | 48 | 2547 | 0.83 | 0.354 | 0.483 | 0.979 |
| 2025-02-03 | train | 58 | 2573 | **0.00** | 0.190 | 0.440 | 0.983 |
| 2025-03-03 | train | 35 | 2712 | 0.57 | 0.486 | 0.465 | 1.000 |
| 2025-04-01 | train | 28 | 2487 | 0.71 | 0.250 | 0.377 | 1.000 |
| 2025-05-01 | train | 43 | 2504 | 0.93 | 0.372 | 0.387 | 1.000 |
| 2025-08-01 | holdout | 58 | 2607 | 1.90 | 0.621 | 0.481 | 1.000 |
| 2025-09-02 | holdout | 51 | 2700 | 3.53 | 0.627 | 0.317 | 1.000 |
| 2025-10-01 | holdout | 57 | 2758 | 1.40 | 0.474 | 0.410 | 1.000 |
| 2025-11-03 | holdout | 54 | 2796 | 1.11 | 0.444 | 0.546 | 1.000 |

**Summary (equal-per-block, the steering rule).**

| Set | Blocks | Lift | Screen beat | Market beat |
|---|---|---|---|---|
| train | 9 | **1.23** | 0.434 | 0.416 |
| hold-out | 4 | **1.99** | 0.542 | 0.438 |
| all 13 | 13 | **1.46** | 0.474 | 0.423 |

**Reading. The section 2 picture was a window effect.** Sections 2 and 3 read
"1.75x to 4.67x in 7 of 9 windows" off five cohorts drawn from a single
five-month stretch of 2026. Across 2024-09 to 2025-11 the screen's lift is
1.46, and a six-block run from 2024-12 to 2025-05 sits at or below 1.0 on five
of six: 1.27, 0.83, 0.00, 0.57, 0.71, 0.93. Lift 1.0 means no information.

2025-02-03 is worse than any month recorded before it: lift **0.00**, meaning
not one of 58 survivors reached the market's top alpha decile, on a 0.190 beat
rate against a 0.440 market. June 2026's inversion (0.31) was not the tail
case; it was the second-worst of fourteen.

**The screen's edge is real but regime-gated, and the regime is off more often
than section 2 suggested.** Nine of fourteen measured windows clear lift 1.0;
five do not.

**Consequences for the funnel-loop.**

1. The AC10 bar is the current filter's hold-out lift, **1.99** on the four
   hold-out blocks. Read once, for bar-setting, as Open question 4 requires.
2. Train sits at 1.23 while hold-out sits at 1.99, so the tuning set is the
   harder regime. A variant that lifts train may still fail the hold-out bar.
3. Survivor counts run 28 to 71, never above the 100 cap, so W5 (the triage
   stage) stays unbuilt and AC10's under-100 clause is already satisfied.
4. Evidence completeness never drops below 0.961, so the INVARIANT-1 veto has
   a high bar and real teeth.

Reproducible: `code/.venv/bin/python scripts/score_filter.py --variant current`.
Two runs are byte-identical; every block reports zero provider misses.

## What this baseline commits the filter work to

1. The bar to clear: the current filter pools to **0.4734** at 8 weeks against a
   market base rate of **0.4361**. Jake's target is a pooled rate above 0.50.
2. ~~The one measured exclusion rule available is the **volatility floor**.~~
   **ANSWERED 2026-08-17: the volatility floor does not bind. Variant 1 is
   dead before it ran.** Measured with `scripts/score_filter.py`'s candidate
   table on four blocks, placing each survivor in the market's own
   `vol_proxy` decile for that block:

   | Block | Survivors | in D1-D3 | in D1-D5 | Lowest decile reached |
   |---|---|---|---|---|
   | 2025-10-01 | 57 | 0 (0.0%) | 1 (1.8%) | D5 |
   | 2025-11-03 | 54 | 0 (0.0%) | 0 (0.0%) | D6 |
   | 2026-03-02 | 75 | 0 (0.0%) | 1 (1.3%) | D5 |
   | 2026-06-01 | 97 | 0 (0.0%) | 0 (0.0%) | D6 |

   Section 5's exclusion zone is D1-D3. The screen has never admitted a single
   name from it, on any block measured. RS >= 90 plus a rising trend template
   already selects the top half of the volatility distribution, so the floor
   removes nothing and cannot change any number. This frees one slot in the
   five-variant budget.
3. No filter change may be justified by a single block's correlation. Section 4
   is the evidence: nothing holds.
4. The frozen horizon stays 56 days. Section 3 is the evidence: 12 weeks buys
   nothing pooled.
