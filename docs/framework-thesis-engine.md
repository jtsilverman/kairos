# Framework candidate: thesis engine (qualitative conviction + technical timing)

**Status: CANDIDATE, v1 — pending Jake sign-off on the spec (`specs/thesis-engine.md`).
Forward-test only; no live capital until the evidence gate passes and Jake arms.**

v1 is **shares-only, long-only**. The options expression and the short side are
parked phase-2 extensions (see Parked, bottom) — they activate only by explicit
re-spec after the v1 forward test reads out.

## Edge claim (named, falsifiable)

An LLM reading a company's full public record (transcripts, filings, news, analyst
revisions, product reality) can identify expectations gaps — prices implying less
than the evidence supports — in liquid mid-caps where analyst coverage is thin and
narrative digests slowly; technical entry timing then confines capital to the
subset of those theses the market has BEGUN to reprice. The counterparty is the
slow updater: anchoring at prior highs (George & Hwang 2004) and sticky
expectations on improving delivery.

Known hostile priors (null ledger, `docs/framework.md`): the technical layer alone
is adjacent to two killed families (momentum long calls; gap-open breakout). This
framework survives only if the THESIS layer adds selection alpha — which is why the
no-thesis control book exists (Evidence gate).

## The funnel

```
~5,000 US stocks
  └─ 1. mechanical screen (weekly, code) ............ ~50 candidates
       └─ 2. thesis engine (LLM deep read) .......... memos
            └─ pool: memos ≥ conviction threshold ... 10-25 live theses
                 └─ 3. entry watch (daily, code+judgment) ... 0-3 entries
                      └─ 4. position management ..... exits per rules
```

## 1. Mechanical screen (code, weekly)

REDESIGNED 2026-07-08 (Jake): no market-cap band, no admission tracks/archetypes,
no ranking composite. All filters are hard binary gates; every survivor goes to
the thesis engine. Each gate traces to a named failure mode:

1. **Price ≥ $10 AND 20d median dollar-volume ≥ $25M AND market cap ≥ $500M
   (checked at profile stage)** — junk-quality floor + tight spreads; the mcap
   floor blocks low-float squeeze names that print RS 99 on huge dollar volume
   (fable-advisor 2026-07-08). No share-count ADV gate (biased against
   high-priced names: measured 2026-07-08, a 1M-share ADV floor excluded ~400
   liquid high-priced stocks the dollar-vol floor admits). No UPPER mcap cap:
   the rubric is size-agnostic; the old $30B cap encoded a thin-coverage thesis
   Jake rejected.
2. **Trend template (Minervini-lite): close > 50d MA > 200d MA, 200d MA rising
   (vs 21 sessions ago)** — a memo has ~13-week shelf life; a name in a downtrend
   is months from clearing the entry gates, so its memo is dead spend.
3. **RS ≥ 90** (see RS spec) — confirmed leaders only; the LLM adjudicates which
   have fundamental substance behind the move vs junk momentum. Screen re-runs
   weekly, so a name crossing 90 enters then (later, never blind).
4. **Revenue growth > 0 (latest annual vs prior) AND operating cash flow > 0
   (latest annual)** — a real, growing, self-funding business; the rubric needs
   improving delivery to cite.
5. **Excluded: biotech binary-event names** (FDA lotteries defeat fundamental
   reading) **and IPOs < 12 months** (no delivery record for dimension 3).

Forensic accrual ratios — AR growth vs revenue growth (TTM), NI > OCF persistence
(consecutive years), share dilution %/yr — are COMPUTED at screen time and handed
to the thesis engine as dimension-7 inputs, NOT gates: each false-fires without
context (annual-billing SaaS, financials/REITs, SBC-heavy tech). A flagged ratio
must be explicitly addressed in the memo (explained-benign, cited, or thesis dead).

Output: the full survivor list (unranked) to the thesis engine. Expected ~20-80
names; > 100 survivors in a week is a surfaced anomaly (arm no silent cap).

## 2. Thesis engine (LLM, per name)

Inputs per name: last 4 earnings-call transcripts, latest 10-K + 10-Qs, trailing
news, analyst estimate history, insider transactions, product/pricing/competitor
reality.

**The 7-dimension rubric** (each scored, each cited to evidence):
1. **Business quality** — moat, unit economics, customer concentration.
2. **Growth trajectory** — revenue/EPS acceleration; mechanical sub-signal:
   estimate-revision breadth + magnitude.
3. **Management credibility** — guidance-vs-delivery record (trailing 4-8 quarters,
   quantified), call-tone shift vs prior calls (verbosity/evasiveness = negative
   tell), opportunistic open-market insider BUYS only (10b5-1 plan trades ignored).
4. **Valuation vs expectations** — reverse-DCF style: what growth does the price
   imply, vs what the evidence supports. "Cheap at 15x" is banned language; the
   claim must be an implied-vs-supported gap. Undervalued = market pricing a
   specific fear the evidence contradicts, or trailing improving delivery.
5. **Repricing horizon** — the catalyst calendar (dated events; quarterly earnings
   floor means the max gap is ~13 weeks) + expected time-to-repricing. Catalyst
   absence never disqualifies; horizon/expression mismatch does. Rumors are never
   thesis evidence and never open a position.
6. **Bear-case steelman + tripwire** — strongest opposing argument, then the
   pre-registered invalidation: "this thesis is wrong if Y", Y observable and
   dated. REQUIRED: scored by a separate fresh-context adversarial pass (LLMs are
   measurably lenient grading their own theses).
7. **Capital allocation** — ROIC vs cost of capital trend, FCF/NI cash conversion,
   red-flag scan.

**Memo output contract:** direction (long) — conviction tier — the specific
mispricing claim — repricing horizon + catalyst calendar — invalidation tripwire —
review date. Written to the journal PIT. A challenge from Jake triggers
re-analysis; the engine never blocks on him.

**Pool:** memos above conviction threshold, target 10-25 names. Maintenance:
tripwire hit or review date passed without re-affirmation → out, regardless of
price. Event triggers (earnings print, guidance change, >15% single-day move on a
pool or candidate name) force a memo refresh.

**Memo cost rule (2026-07-08):** the weekly screen re-run memos NEW admissions
only; a name already in the pool (or already memoed and below threshold, still
inside its review date) is not re-read. Refreshes happen via event triggers and
review dates, never via weekly re-admission.

## 3. Entry (daily watch on pool names only)

**RS spec:** RS_raw = 0.4×r_63d + 0.3×r_126d + 0.3×r_252d; RS = percentile rank of
RS_raw across the BROAD liquid field (price ≥ $5, 20d median dollar volume ≥ $5M),
computed weekly. The percentile field is deliberately wider than the screen's
admission floors so RS ≈ "top decile of tradeable US stocks", not "top decile of
the already-filtered pool". (Mcap ≥ $500M dropped from the field definition
2026-07-08: no mcap in the bars feed, never implemented.)

**Firm gates (code, binary — judgment may veto a pass, never override a fail):**
1. Price above 50d MA; 200d MA rising (vs 21 sessions ago).
2. RS ≥ 70 AND RS > its value 21 sessions ago.
3. Objective trigger only (per class, below): qualifying CLOSE + volume.
4. Chase limit: no entry above 1.05 × trigger anchor.
5. Stop price defined before entry; max $ risk per trade enforced (Sizing).
6. Live memo, tripwire intact — no memo, no trade.
7. One attempt per structure; failed structure resets; one retest max.

**Two entry classes:**

| | Base breakout | Leader pullback |
|---|---|---|
| Qualifier | Coiled consolidation; pivot near 52wk high | 52wk high printed within trailing 40 sessions |
| Trigger | Close > pivot, vol ≥ 1.5 × 50d avg | Close back above touched 20d/50d MA, vol ≥ 1.2 × 50d avg |
| Chase anchor | pivot | the reclaimed MA |
| Stop | base low | pullback low |

**Judgment layer (LLM reads code-computed facts; guidance bands, not cliffs):**
base quality — duration (~15-65d), depth (~≤20%), final-10d tightness (~≤10% of
price), volume dry-up (10d MEDIAN vs 50d avg, ~≤80%), pivot proximity to 52wk high
(~≤15%); pullback quality — orderly drift on fading volume vs distribution, depth
(~≤15% from swing high), prior pullback behavior in the run. Every entry note logs
the measurements + the read + the class, PIT.

**Archetype × class matrix:** archetype 1 uses both classes; archetype 2
realistically only base-breakout (a recovery name cannot print a fresh 52wk high
until it has effectively graduated to archetype 1). The rolling 52wk-high window
is the built-in patience enforcer for archetype 2 — no per-archetype knobs.

## 4. Exits (shares)

1. **Structure stop (hard):** close below the entry structure's stop level.
2. **Thesis tripwire (hard):** memo invalidation condition hit → exit regardless
   of price.
3. **Review-date time stop:** review date passes without re-affirmed memo → exit.
4. Profit-taking: judgment-layer (scale-out into strength permitted); no frozen
   profit-target numbers in v1 — the journal accumulates evidence for v2 rules.

## Sizing (v1, capital base = config.TRADING_CAPITAL $6k)

- Max position: $2,000 (⅓ of capital). Concurrent positions: ≤ 3.
- Max risk-at-stop per trade: $300 (5% of capital). Position size =
  min($2,000, $300 / stop_distance_pct).
- Forward-test halt: portfolio drawdown ≥ 15% of capital → halt entries, full
  review with Jake before resuming.

## Evidence gate (forward, journal-based — no backtest claim)

- **Mode:** paper (journal-logged simulated fills at next-day open after signal
  close; slippage logged honestly). No live order until this gate + Jake arms.
- **Control book (the decoration test):** every day, the same code logs what the
  ENTRY LAYER ALONE would have traded from the screen's candidate list without any
  thesis filter (same gates, same sizing). If the thesis pool doesn't beat the
  no-thesis control, the LLM layer is decoration and the family dies — this is the
  random-K lesson applied forward.
- **Readout:** after ≥ 20 closed trades or 6 months, whichever first: hit rate,
  avg R, expectancy, vs SPY same-period and vs the control book. Pre-committed
  kill: expectancy ≤ 0 vs SPY, or indistinguishable from control book → kill or
  re-spec. Pass → Jake decides paper→small-live.
- **Scorer pinning:** memos and entry judgments carry the model id + prompt
  version. Model swap → flagged in journal; evidence windows don't silently mix
  scorers.

## Ops cadence

- Weekly (weekend): screen refresh, RS recompute, pool review, memo re-affirmations.
- Daily (post-close): entry watch on pool, position checks (stops, tripwires,
  review dates), journal entries.
- Event-driven: earnings/guidance/±15% moves on pool names → memo refresh.

## Frozen numbers (change only via journal evidence, named in a re-spec)

Screen (redesigned 2026-07-08): $10 floor, $25M dollar-vol, trend template
(50d/200d/200d-rising), RS ≥ 90 admission, revenue TTM > 0, OCF TTM > 0,
forensic-ratio thresholds (as LLM inputs). RS: 0.4/0.3/0.3 over 63/126/252d,
entry gates 70 + rising over 21 sessions.
Premove cohort (cohort 2, specs/premove-cohort.md, frozen 2026-07-14): same
funnel with the admission rule swapped — RS percentile [70, 90) half-open
AND rising (percentile > its own value 21 sessions ago, t-21-consistent
$5/$5M field eligibility) AND RevisionSnapshot.positive (net_up_30d >= 0
AND trend_delta_90d > 0) as a hard gate; PREMOVE_NET_UP_FLOOR = 0 (no extra
breadth floor — Jake 2026-07-14, all-60 bootstrap accepted); missing
yfinance coverage = counted exclusion (probe 2026-07-10: 0% at the gate).
Cadence: ad hoc, NOT weekly (Jake 2026-07-14); output
data/screen/premove/<as_of>.json; same dossiers, same prompts, memo rows
tagged cohort='premove'; memo-cost rule (new-admissions-only) applies
whenever it runs.
Entry: vol 1.5x / 1.2x, chase 1.05x, judgment guidance bands as listed. Sizing:
$2,000 / $300 / 3 / 15%. Evidence: 20 trades / 6 months.

## Parked (phase-2, each needs explicit re-spec; do NOT build in v1)

- **Foreign filers (ADRs: ASML/AZN/STM class):** silently excluded in v1 —
  they file 20-F not 10-K, often under IFRS tags, so `edgar.annual_series`
  returns MissingFactError. Admitting them = 20-F form acceptance + IFRS tag
  fallbacks in the EDGAR wrapper. Jake ok'd deferral 2026-07-08.
- **Believability-weighted judging (Dalio):** v1's thesis-judge weighs evidence
  only; per-agent verdict track records accumulate in the journal so weights
  can be MEASURED at the evidence-gate readout, never invented at t=0.
- **Options expression:** shares remain default; a trade may escalate to a deep-ITM
  call (delta 0.70-0.80, DTE ≥ 2-3x expected hold) only on ALL of: dated catalyst
  3-8 weeks out, IV rank < 25, chain OI ≥ 500 + spread ≤ 10% of mid, top-tier
  conviction, no earnings inside DTE unless deliberate pre-event with pre-print
  exit. Constant dollar risk: premium ≤ the shares-version risk-at-stop. Dual-book
  logging measures the wrapper tax.
- **Short side (long puts):** asymmetric entry grammar (failed-rally rollover, not
  breakdown-chasing); VRP tax means it must clear its own gate, never ride the
  long book's pass.
- **Contraction normalization:** relative-to-own-volatility tightness check, only
  if the journal shows quiet names chronically failing the absolute band.
