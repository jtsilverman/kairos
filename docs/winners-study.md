# Winners study: what A-tier looked like, backwards (2026-07-12)

Retrospective calibration exercise for the A-tier definition (Jake, 2026-07-12).
Four historical dates, the CURRENT coded screen run as-of each (RS >= 90, trend
template, $10/$25M/$500M floors, revenue growth > 0 + OCF > 0, no biotech),
survivors bucketed by forward alpha vs SPY to 2026-07-10, then one qualitative
pattern agent per horizon contrasting winners vs losers vs neutrals with a
mandatory anti-hindsight check (a pattern that also fired on the other bucket
dies or gets qualified). Dimensions used as a guide, not a map.

**Method caveats.** Pattern agents worked from model knowledge of the entry
dates; multiples are from-memory approximations (flagged in the raw reports),
EDGAR gates in the historical screens used current facts (minor leak, bars
gates are PIT-correct). This calibrates ANCHOR LANGUAGE, not scored thresholds;
pull entry-date consensus data before freezing any numeric threshold. Raw
per-horizon reports (bucket lists, per-name snapshots, per-pattern anti-
hindsight checks): session artifacts, distilled here; buckets + screens JSON in
the 2026-07-12 session scratchpad `winners-study/`.

## The cohorts

| entry | horizon | SPY | survivors | winners / neutral / losers (thresholds) |
|---|---|---|---|---|
| 2024-07-08 | 24mo | +36.0% | 82 | 32 / 9 / 27 (alpha >= +50% / abs <= 12% / <= -20%) |
| 2025-01-07 | 18mo | +28.3% | 68 | 20 / 6 / 28 (>= +40% / <= 12% / <= -20%) |
| 2025-07-07 | 12mo | +21.6% | 79 | 28 / 7 / 33 (>= +30% / <= 10% / <= -15%) |
| 2025-11-07 | 8mo  | +12.5% | 66 | 39 / 8 / 12 (>= +25% / <= 10% / <= -15%) |

Structure findings before any pattern: (1) outcomes are BIMODAL — the screen's
RS>=90 names either keep working or crash; neutrals are the smallest bucket at
every horizon. (2) Entry point dominates identity: PLTR +322% from 2024-07,
-30% and -41% from the two 2025 entries; same for APP, IREN, VST, CVNA, CEG.
The screen measures motion; it cannot tell acceleration from terminal velocity.

## Convergent patterns (present in >= 3 of 4 horizons, each anti-hindsight-checked)

1. **Multiple-on-WHAT-earnings, never multiple-level.** Trough/depressed
   earnings + estimates inflecting won even when optically expensive (STX, MU,
   LITE, CIEN, COHR, WDC); peak earnings lost even when optically cheap (ANF
   ~15x peak apparel margins, CALM peak egg prices, QCOM peak handset EPS, MLI
   peak copper spreads). The question is "P/E on trough or peak", not "what
   P/E". Qualifier (24mo FUN): the trough needs a structural demand kicker plus
   rising estimates, not leverage plus a stagnant end market.
2. **Revisions-led vs multiple-led RS — the single sharpest discriminator.**
   Winners' price rose WITH estimates (FIX, GEV, CRDO, AGX, MU: revision
   drivers externally observable — contract price tapes, backlog records,
   raised capex guides). Losers' price rose on multiple expansion over a
   static or decelerating estimate base (PLTR 2025: estimates +35-40% trailing
   year, stock +400%; MIR: ~10% grower re-rated to 40x on theme flows; ORCL,
   ZS, SHAK, LMB). This one check separates the 2024 PLTR/CVNA/VST entries
   (winners) from the 2025 entries (losers). No horizon found a
   skeptically-priced revisions-led loser.
3. **Booked, dated demand vs thematic tag.** Winners had invoices: sold-out
   HBM (MU), disclosed AI-server backlog (DELL), signed GW order (BE), record
   contracted backlog (AGX, FIX, GEV slot scarcity). Losers had press-release
   themes: GDDY Airo, ASAN AI Studio, QCOM AI-PC, LEU 2027+ HALEU, SYM
   deployment promises, VST/CEG hoped-for PPAs, CRK "gas for AI". Test: does
   the theme appear in the income statement/backlog or only in the press
   release. Leak (12mo): AMSC and DRS billed real revenue and lost — this
   gates eligibility, it does not confer A.
4. **Payer quality.** Hyperscaler capex, aero/defense budgets, power scarcity
   = winner payers. US consumer, SMB software, policy hope, funding-window
   customers (small-biotech CROs, reimbursement, single-counterparty Walmart)
   = loser payers. Exception route for weak payers: single-digit multiple PLUS
   a mechanical capital-return catalyst (TPR: 10x + $2B deal-break buyback —
   the lone consumer winner shape).
5. **A live business-bear case still unconverted = the energy source of the
   win.** Winners' bear cases required business deterioration and were
   publicly disbelieved ("HDDs are dead", "fuel cells never work", "casual
   dining is dead", "CVNA is a zombie") — refutation repriced the stock.
   Losers' bear case was only the multiple (COST, AXON, FICO, CRWD) — nobody
   left to convert, no right tail. Perfection-priced quality that DELIVERS
   still returns ~zero alpha (LLY +30% growth met, ~0 alpha; AVGO/APH neutral
   at the 2025-11 entry after full re-rating — the alpha-decay endpoint of a
   prior winner). Qualifier: skepticism pays only AFTER the inflection has
   printed (KD, FUN lost on promised inflections; EAT, CVNA, TEVA won on
   printed ones).
6. **Neutrals = correctly priced, in every cohort.** Fair-priced quality
   delivering as guided earns beta (BWXT, ULS, SNOW, TT, LLY); cheap with no
   revision engine earns beta (CAKE, FTDR, URBN). A-tier is a MISPRICING
   claim, never a quality claim.

## Kill rules (auto-veto shapes; zero winners matched across all horizons)

- **Consumer discretionary/staples > ~30x lapping peak comps** (24mo: 0
  winners, 9 losers — CAVA, WING, ELF, DECK, OLLI, FRPT, VITL, COST, TXRH).
- **Cyclical at peak earnings wearing a low P/E** (CALM, SKYW, AAL, CRK, ANF,
  MLI). The screen manufactures these — RS + growth + OCF all fire at the
  cycle top.
- **Theme in the press release, not the P&L** (ASAN, GDDY, PEGA, QCOM AI-PC).
- **Dilution-funded pivot entered days after a euphoric gap** (IREN 2025-11,
  four days post-Microsoft-deal parabola; U). Same pivot self-funded by an
  existing P&L qualified (DOCN).
- **Catalyst that changed the mood, not the math** (GEO/LRN/MIR election and
  policy hope, RH viral quarter vs GSAT Apple-bought-20%, TPR buyback, BE
  signed GW).
- **Borrowed momentum**: consumer RS earned in a factor rotation during an
  industrial-capex regime (SHAK, CBRL, RCL, URBN, EYE cohort: 0-for-8 on
  positive alpha at 12mo).

## Killed non-patterns (checked and rejected in >= 2 horizons)

- Raw run length / extension / distance from high (MU, DELL, HWM, FIX, GEV
  won extended; the discriminator is #2, not the run).
- Management quality alone (COST, DECK, FICO, CRWD: excellent managements,
  worst outcomes).
- Crowding alone (AMD, BE crowded winners; WGS, ATEC under-covered losers —
  amplifier, not signal).
- Valuation level alone (PLTR/CRDO/ANET won expensive; MOS/ANF/CALM lost
  cheap).

## Implications for the v13 A-tier definition

The current judge A ("opposing case answered or immaterial") grades case
completeness. The evidence here says grade the MISPRICING:

- **A requires an articulable expectations gap**: one falsifiable sentence for
  why the market's current model of this business is wrong, with the
  refutation evidence already printing (in reported numbers or signed
  backlog, never only promised).
- **A requires the winner shape**: evidence-led repricing (estimates rising
  with or ahead of price), demand booked and dated, payer durable, earnings
  base trough-or-reasonable rather than peak.
- **Upheld risk findings block A only if uncompensated**: a risk that is
  priced (the skepticism IS the discount) is the energy source, not the
  disqualifier. A risk that requires no bad news (multiple-only bear) caps at
  B/C regardless of quality.
- **Kill rules above are A-vetoes** regardless of case quality.
- Codeable dossier candidates (post-v13, separate spec): RS decomposition
  line (trailing price change vs [R1] estimate change), multiple percentile
  vs own history (from [Q1] series + bars), story age (sessions since first
  RS>=90 attainment).

Forward ledger stays the unbiased grader; this study only writes the anchor
language the ledger will then score.
