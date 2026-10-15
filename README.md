# kairos

A fundamental stock picker built as a multi-agent research funnel. Each month it reads the public
record of every US company that survives a rule-out screen, argues the bull and bear case for each,
fact-checks both, and writes a rated thesis for the names it would own. Shares, long only.

**Status: forward paper test.** Nothing here places a trade. The first live run (as of 2026-10-06)
is recorded as an equal-weight paper basket, scored against SPY at 6, 12 and 24 weeks. Execution
and position management are a separate private part of the project and are not in this repository.

## The goal

A monthly shortlist where each name carries a clear, strong fundamental thesis: a sound business
case, good fundamentals, a demand case where one applies, and a company clearly positioned for it.
The prompts are calibrated to the soundness of the thesis. Beating SPY over a quarter to a year is
the check on the method, never the target the prompts are fitted to.

## The funnel

| Stage | What it does | Model | 2026-10-06 |
|---|---|---|---|
| Rule-out screen | Hard binary rules: facts no fundamental thesis survives | none | 801 → 299 |
| Layer 1: triage | Reads an anonymized fact sheet; a name is cut only when two passes both say no | `claude-sonnet-5` | 299 → 205 |
| Dossier | Filings, transcripts, estimates, revisions, insider and short-interest data, every source dated on or before the as-of date | none | 205 |
| Layer 2: bull, bear, ruler | A bull and a bear argue four tests; the ruler reads the dossier and rules whether the bull case outweighs the bear | `claude-sonnet-5` | 205 → 134 |
| Layer 3: editor, verdict | The editor checks every claim in both cases against the dossier; the verdict seat writes the thesis and rates it | `claude-opus-4-8`, `claude-fable-5` | 134 → 55 |

The four tests every case is argued on: business case, fundamentals, demand case, positioning
(`docs/four-tests.md`). Every seat names a versioned model id, never a bare alias, so a model
release cannot silently change the funnel.

A blind sorter grades every layer-2 entrant's dossier on the same four tests, without seeing any
seat's output. Those grades are the reference the funnel is judged against: of the strong
dossiers, how many survived; of the weak ones, how many were stopped.

## What the past dates showed

Tuned on three past dates (2026-02-02, 03-16, 05-01) with models whose training cutoff precedes
them, then read once on a held-out date (2026-06-01):

- The funnel sorted dossiers as intended: no weak-tier dossier reached the June shortlist.
- The sort lost money that quarter. The 39-name shortlist trailed SPY by 9.9 points over
  2026-06-02 to 2026-08-31, while the weak-tier dossiers beat it. A July selloff in AI and
  infrastructure names, plus company-specific misses, hit exactly the strong-dossier names.
  `docs/june-return-audit.md` has the numbers, including two split-adjustment errors in the price
  cache that had overstated the loss.

One quarter cannot separate a wrong rubric from a hostile tape, which is why the method moved to a
forward paper test rather than more tuning on the same past dates.

## Running it

Requirements: Python 3.12, a Polygon key with stock aggregates, and Claude Code with the Workflow
tool (the agent stages run as Claude Code workflows driven by headless `claude -p` children).

```
cd code && python -m venv .venv && .venv/bin/pip install -e . pytest
cp .env.example .env   # POLYGON_API_KEY, KAIROS_CONTACT
cd code && .venv/bin/pytest -q
```

Generate the workflow scripts from the committed seat bodies, then run a live date:

```
code/.venv/bin/python scripts/gen_funnel_workflow.py --out data/scratch/funnel-sim.js
code/.venv/bin/python scripts/gen_sorter_workflow.py --out data/scratch/sim-sorter.js
bash scripts/live_paper_run.sh <last completed trading day>
```

The chain runs one Claude child at a time in batches of eight names, skips any batch whose output
exists, and stops on the first failure, so rerunning it unchanged resumes. `scripts/mem_guard.sh`
pauses it under memory pressure. The paper basket is written once to `data/paper/<as_of>.json`;
`scripts/score_paper.py score` fills each window once its exit close exists.

## Layout

| Path | What |
|---|---|
| `.claude/agents/` | Seat bodies: triage, bull, bear, ruler, editor, verdict, sorter |
| `scripts/gen_*_workflow.py`, `scripts/cascade_workflow.js` | Workflow generators; seat bodies are embedded by value |
| `scripts/live_paper_run.sh`, `scripts/prompts/` | The live chain and its child prompts |
| `scripts/score_paper.py` | The paper basket and its 6/12/24-week scorer |
| `code/src/kairos/` | Screen, fact sheets, dossier compiler, data clients |
| `docs/` | The four tests, the screen rules, triage method, validation method, the June audit |

## Data sources

SEC EDGAR (filings, XBRL facts, Form 4), Polygon (prices), FINRA (short interest), FRED (macro),
earnings transcripts and analyst estimates. EDGAR and FINRA require a contact string in the
User-Agent: set `KAIROS_CONTACT` in `.env`.
