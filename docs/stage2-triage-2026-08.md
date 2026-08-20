# Stage 2: the agent triage, 2026-08-17

Results of record. Reproduce with the commands at the bottom.

Stage 2 asks a cheap agent whether a name that cleared the mechanical screen
still carries a fundamental case. It is a rule-out stage, so it never ranks.

## The funnel

| Stage | Names |
|---|---|
| price-strength top third of the ranked field | 768 |
| screen of record, 8 rules (`docs/ruleout-screen-2026-08.md`) | 342 |
| stage 1, event rule-outs (`kairos.events`) | 336 |
| **stage 2, agent triage** | **207** |

207 sits above the panel ceiling of 100. That gap is a count problem, not a
precision problem, and it has no screening solution
(`wiki/concepts/rule-out-screen-design.md`).

## How the verdict is reached

1. Each name gets a fact sheet: its filed annual series, margins, revenue
   CAGR, dilution, net debt over operating cash flow, interest coverage, and
   a STALE SERIES block. `kairos.factsheet`.
2. The sheet is **anonymized**. It carries no ticker, no market cap, no
   price and no price strength.
3. Three independent Sonnet seats read it and answer yes or no.
   `.claude/agents/screen-triage.md`.
4. A name all three agree on is settled.
5. A 2-1 split goes to one Opus seat, which reads the sheet plus the three
   verdicts and rules for itself. `.claude/agents/screen-adjudicator.md`.

## Precision

| Measure | Value |
|---|---|
| unanimous across three passes | 316 of 336 (94.0%) |
| split 2-1 | 20 of 336 (6.0%) |
| of the splits, Opus kept | 16 |
| of the splits, Opus cut | 4 (ACAD, KTB, REAL, S) |

**6.0% is the measured run-to-run instability** of a single Sonnet pass on an
identical sheet with an identical prompt. Any single-pass triage result
carries that error bar. Three passes plus adjudication removes it.

## Why anonymized

A named run's yes-rate climbed monotonically with market cap: 23% under $2B,
55% at $2-10B, 60% at $10-50B, 81% over $50B, on sheets that never state
market cap. Re-running the identical sheets anonymized moved 24 verdicts, 23
of them from yes to no, and never moved a name under $2B.

Pure variance accounts for about 5.1 of those 7.2 points, so most of the
apparent effect was noise. The direction was one-sided, so a small real bias
existed. Anonymizing costs nothing and removes the question.

## Three sheet bugs the adjudicator found

The Opus seats caught all three by reading the raw series against the
computed ratios. They corrupted 142 of 336 sheets, and every count above is
from the corrected sheets.

| Bug | Evidence | Fix |
|---|---|---|
| interest coverage printed with the filer's sign | ATRO read `-3.3x` for 3.3x cover, 54 names | divide by the magnitude, keep the earnings sign |
| net-debt ratio built from a dead XBRL tag | ARMK's debt series stops at 2019, so it read as net cash while paying $364M of annual interest, 76 names | every ratio input comes from the latest revenue period, or the ratio is omitted |
| a margin off a stale row labelled "latest" | ANF's gross margin came from 2024-02-03, 29 names | the margin prints its own period |

A verdict resting on a computed ratio must be audited against the series the
ratio came from. Three Sonnet passes agreeing did not catch any of these.

## Two prompt corrections, from reading the first run's cuts

**Debt alone is not a rule-out.** The first run cut MTD (negative equity from
years of buybacks, debt at 2.2x cash flow), CSW (a debt-funded acquisition)
and CSCO (borrowing for Splunk). The seat had a debt balance and no
denominator. Adding the two ratios and naming the three rescuable patterns
reversed 20 of 112 debt-driven cuts; the rest moved to defensible reasons.

**Banks are not manufacturers.** Seven of eleven financial cuts (PNC, MTB,
ZION, CFR, CDP, ECPG, VIRT) cited cash conversion. For a bank, operating cash
flow moves with loan origination and the trading book. The seat is now told
to judge banks, insurers and REITs on revenue, net income and book equity.

## The 207

    ABNB ACIW ADEA ADI AEIS AFRM AGX AGYS AIT AIZ
    ALL AMAT AMD AME AMGN ANET ANF APH ATRC ATRO
    AVPT BAC BCRX BILL BJRI BKNG BMRN BOX BPOP BRZE
    BURL CACI CAH CAKE CARG CART CASY CATY CFG CFR
    CLS COCO COKE CPAY CRDO CVCO CVLT DAL DASH DAVE
    DDOG DELL DOCN DT DXCM EAT ECG ENVA ESTC EWBC
    EXPE FBP FCFS FDS FFIV FIGS FIVE FIVN FIX FLEX
    FLYW FN FROG FRPT FRSH FSLY FTDR FTNT GCT GE
    GEV GL GOOGL GRMN GSAT GTLB GWRE HALO HCI HEI
    HIMS HQY HRB HST HURN IBKR IESC IMAX INCY IOT
    IPAR IRDM JAZZ JLL JNJ KEYS KFY KLAC KNSA KRYS
    LAUR LFST LIVN LLY LRCX LTH LYFT MANH MCY MDB
    MEDP MGNI MMSI MRK MRVL MSGE MTB MTSI MU NDSN
    NET NTAP NTRA NVT OKTA PACS PANW PATH PAY PAYC
    PAYX PCTY PGY PLTR PLXS PNC POWL PRI PSMT PWR
    PYPL QLYS RELY RGA RNG ROKU ROST RTX SANM SEIC
    SHOP SITM SKWD SKY SN SNDK SNOW SNX STT STX
    SXI TEAM TENB THG TOST TPC TRV TTMI TVTX TWLO
    TXG UAL UFPT UNP URI USB USFD VCTR VCYT VEEV
    VICR VIRT VRNS VRT VRTX WAB WDAY WDC WGS WK
    WSFS WT WTS XYZ ZETA ZION ZM

## Reproduce

```
code/.venv/bin/python scripts/ruleout_screen.py 2026-08-17
code/.venv/bin/python scripts/compile_factsheets.py 2026-08-17
code/.venv/bin/python scripts/anonymize_factsheets.py 2026-08-17
```

Then the triple-pass triage over the anonymized slugs, `write_priors.py` on
the splits, and the adjudication pass. Full keep and cut lists land in
`data/stage2-2026-08-17.json` (gitignored).
