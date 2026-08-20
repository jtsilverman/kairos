# kairos

A multi-agent equity research pipeline. It screens the US equity universe down to a working
candidate set, then runs each candidate through a panel of agents that build, cross-check and
stress-test an evidence-cited investment thesis.

**Status: in beta.** The screen and the thesis engine both run end to end. The full test suite
passes. Research use only, and nothing here places a trade.

This repository is the research half of a larger private project. Execution, position management,
and the trade journal are not included.

## The funnel

Results of record, 2026-08-17. Reproduce with the commands in `docs/stage2-triage-2026-08.md`.

| Stage | Names | What it does |
|---|---|---|
| US universe | 9,563 | Every listed common share with a filed record |
| Price strength | 768 | Top third of the ranked field |
| Rule-out screen, 8 rules | 342 | Facts no fundamental thesis survives |
| Event rule-outs | 336 | `kairos.events` |
| Agent triage | 207 | Three blind agent seats read an anonymized fact sheet |
| Thesis panel | 5-10 live theses | Deep read, adversarial review, conviction ranking |

## The screen rules out, it never ranks

Every gate is a hard binary. A name either carries a fact that kills any fundamental thesis or it
does not. The screen is judged on what it rules out, never on the returns of its survivors.

The eight rules, in `docs/ruleout-screen-2026-08.md`: has revenue, revenue growing year over year,
funds itself on operating cash flow, share count not up more than 20% in a year, not deteriorating,
and a sector deny-list for businesses whose results are set by a price nobody at the company
controls.

The deterioration test splits by business type, because the metrics do. Non-financial companies are
cut only when earnings fell more than 25% and neither capex nor research spend rose, since a modest
dip is ordinary noise and a collapse with no investment behind it is not. Financial companies are
required to grow both earnings and book value per share, because banks, insurers and REITs report
no capex and no research line, so the non-financial test would cut them by accident. Twelve of the
first twenty-one cuts under the old test were financials with no path available to them.

## The agent triage is blind on purpose

Stage 2 asks whether a name that cleared the mechanical screen still carries a fundamental case.

1. Each name gets a fact sheet: filed annual series, margins, revenue CAGR, dilution, net debt over
   operating cash flow, interest coverage, and a stale-series block. `kairos.factsheet`.
2. The sheet is **anonymized**. No ticker, no market cap, no price, no price strength.
   `kairos.thesis.anonymize`.
3. Three independent agent seats read it and answer yes or no.
   `.claude/agents/screen-triage.md`.
4. A name all three agree on is settled. A split goes to an adjudicator.
   `.claude/agents/screen-adjudicator.md`.

Anonymization is what makes the vote worth counting. An agent that can see the ticker is reasoning
about the company it already knows, not about the filed record in front of it.

## The thesis panel

Each surviving candidate is read by a panel of role-specialized agents, defined in `.claude/agents/`:

| Agent | Role |
|---|---|
| `thesis-analyst` | Builds the case from the public record |
| `thesis-fundamentals` | Checks the numbers behind the case |
| `thesis-catalyst` | Names what has to happen and by when |
| `thesis-challenger` | Argues the other side |
| `thesis-adversary` | Attacks the thesis's weakest load-bearing claim |
| `thesis-judge` | Scores conviction against the evidence actually cited |

The ensemble logic is in `kairos.thesis.ensemble`; the memo format and its citation rules are in
`kairos.thesis.memo`; open theses and their review triggers live in `kairos.thesis.ledger`.

Every claim in a memo carries a citation to the filing, transcript, or data series it came from. A
claim with no source does not enter the memo.

## Data sources

| Module | Source |
|---|---|
| `kairos.data.edgar` | SEC EDGAR company facts and filings |
| `kairos.data.transcripts` | Earnings call transcripts |
| `kairos.data.estimates` | Analyst estimate revisions |
| `kairos.data.finra` | Short interest |
| `kairos.data.fred` | Macro series for the regime read |
| `kairos.data.polygon` | Price and volume bars |
| `kairos.data.universe` | The listed universe |

## Run it

```
cd code
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest        # 330 tests
```

Set `KAIROS_CONTACT` before any live fetch. SEC EDGAR and FINRA both reject an anonymous
User-Agent and ask for a contact address in it:

```
export KAIROS_CONTACT="your-project you@example.com"
```

`POLYGON_API_KEY` is read from the environment at call time for price data.

## Layout

```
code/src/kairos/
  screen.py       The mechanical screen
  ruleout.py      The eight rule-out gates
  events.py       Event rule-outs
  factsheet.py    The anonymizable fact sheet
  data/           SEC, transcripts, estimates, FINRA, FRED, Polygon, universe
  signals/        Relative strength, opening range, story age
  thesis/         Dossiers, ensemble, memo, ledger, regime, market context
code/tests/       330 tests
scripts/          Runnable entry points for each stage
.claude/agents/   The screening and thesis agent definitions
docs/             The screen of record, the thesis framework, validation methodology
```

## Known limits

The screen's survivor count runs well above the panel's capacity: 207 names against a panel ceiling
of 100. That is a count problem rather than a precision problem, and it has no screening solution.
Tightening the rule-out gates to hit a target count would convert a rule-out screen into a ranking
screen, which is the design the docs argue against.
