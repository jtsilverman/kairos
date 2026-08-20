# The rule-out screen: four months

Measured 2026-08-18 with `scripts/ruleout_screen.py`. This supersedes the
alpha-graded framing in `docs/filter-baseline-2026-08.md`; the screen is judged
on what it rules out, never on the returns of its survivors.

## What the screen is

**Rule-outs.** Facts no fundamental thesis survives.

1. Has revenue. A real operating business.
2. Revenue growing year over year.
3. Funds itself. Operating cash flow positive.
4. Share count not up more than 20% in a year.
5. Not deteriorating, and the test differs by business type because the
   metrics do (revised 2026-08-18).

   **Non-financial companies.** Cut only when earnings fell more than 25% AND
   neither capex nor research spend rose. A modest earnings dip is ordinary
   business noise; a collapse with no investment behind it is not. The earlier
   version cut on any decline and took Booking Holdings with it at -8%, a
   capital-light business that returns cash through buybacks. Cuts 3 of 288:
   Baxter, Fortrea, Knight-Swift.

   **Financial companies.** Require earnings growth AND book value per share
   growth, both. Banks, insurers and REITs report no capex and no research
   line, so the non-financial test would cut them by accident: 12 of the first
   21 cuts were financials with no path available to them. Book value per share
   is what these businesses actually compound and it is computable for all 66.
   Cuts 25 of 66, taking the managed-care group (UnitedHealth -16%, Centene
   -302%, Oscar -1842%), the shrinking asset managers (Franklin, Invesco) and
   the distressed REITs (SL Green, Macerich, Pebblebrook). Keeps Bank of
   America, US Bancorp, PNC, Travelers, Allstate, State Street, Interactive
   Brokers.

6. Sector deny-list. Cut businesses whose results are set by a price nobody at
   the company controls: mining and oil and gas (SIC 1000-1499), steel and
   aluminium (3300-3399), utilities (4900-4999), shipping (4400-4499),
   hospitals (8062), oilfield machinery (3533), freight forwarding (4731).
   Found independently by eight blind readers of the 382-name August list.
   Financials are NOT on this list: measured over the trailing year they beat
   SPY 86% of the time against 76% for everything else, so cutting them costs
   real candidates. Cuts 26.

7. Revenue growth computed off a base under $20M is arithmetic noise, not a
   trend. Cuts Arrowhead (a $3.6M base producing 23,258%) and Anterix.

8. One ticker per filer. Alphabet listed twice as GOOGL and GOOG took two
   panel slots.

**Trimming.** Practical limits, not judgments.

6. Price over $10, 20-day median dollar volume over $25M.
7. Market cap over $500M.
9. Price strength in the top third of the ranked field (Jake, 2026-08-18,
   down from the top tenth). **The dial stops here.** Tightening to the top
   quarter drops 84 names including Alphabet at strength 68, Johnson & Johnson,
   Palantir, GE, Vertex (earnings +838%), Guidewire (+1244%) and Toast
   (+1700%). Price strength ranks how much a stock has already moved, so
   sorting by it drops large high-quality compounders first, because size damps
   price movement.

10. Market cap uses a split-adjusted share count. Grouped-daily closes are
    split-adjusted and filed share counts are not, so a company that split
    since its last filing had its market cap wrong by the split ratio. Booking
    Holdings read $6.9B against a real $173.2B after a 1-for-25 split on
    2026-04-06. Fixed by `polygon.split_factor` feeding
    `screen.pit_market_cap`.

**Deleted 2026-08-18: the biotech label rule.** Rules 1 and 3 remove every
pre-revenue clinical name directly. The label wrongly cut Vertex and Regeneron,
and its source field has no historical vintage, so a rewind applied today's
labels to a past market.

## Counts

| Month | Top third | Survivors |
|---|---|---|
| 2025-11-03 | 738 | 226 |
| 2026-02-02 | 787 | 237 |
| 2026-05-01 | 773 | 298 |
| 2026-08-17 | 768 | 382 |

## What each rule removed

| Removed by | 2025-11-03 | 2026-02-02 | 2026-05-01 | 2026-08-17 |
|---|---|---|---|---|
| no filings | 149 | 142 | 130 | 79 |
| no revenue | 153 | 182 | 131 | 106 |
| revenue not growing | 108 | 138 | 118 | 108 |
| does not fund itself | 65 | 46 | 46 | 46 |
| deteriorating, not investing | 13 | 20 | 25 | 25 |
| share count exploding | 9 | 12 | 14 | 13 |
| too small | 13 | 6 | 6 | 4 |
| no share count | 2 | 4 | 5 | 5 |

Every rule fires in every month. None is dead weight, none swings wildly.

## Reading

1. The count runs 226 to 382 against a panel ceiling of 100. The gap is a
   ranking problem: no disqualifying fact remains among the survivors.
2. Turnover is high. Only 55 companies survive all four months, so
   roughly half the list is new each run.
3. "No revenue" plus "no usable filings" removes about a third of the pool.
   That is ETFs, trusts and foreign filers, janitorial work rather than judgment.

Reproduce: `code/.venv/bin/python scripts/ruleout_screen.py 2025-11-03 2026-02-02 2026-05-01 2026-08-17`
