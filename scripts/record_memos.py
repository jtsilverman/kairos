#!/usr/bin/env python3
"""Record thesis-workflow output into the journal DB, PIT. Validates the
mechanical output contract per memo (fail-loud; v7 payloads additionally
recompute the 3-judge ensemble in code); the scorer pin (agent-file hashes
+ per-role effort + model alias) is computed at record time.

Usage:
    .venv/bin/python scripts/record_memos.py --workflow-out results.json \
        --manifest data/dossiers/2026-07-07/manifest.json \
        --model-alias opus \
        --efforts analyst=max,adversary=max,judge=xhigh [--db data/kairos.db]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "code" / "src"))

from kairos.thesis import memo

# Both v9 judge seats share thesis-judge.md; the per-seat MODEL in the pin
# (--models) is what tells them apart. Roles per run inferred from the
# workflow-out's judge count (memo.judge_seat_roles).
_ROLE_FILES = {
    "analyst": _ROOT / ".claude" / "agents" / "thesis-analyst.md",
    "adversary": _ROOT / ".claude" / "agents" / "thesis-adversary.md",
    "judge": _ROOT / ".claude" / "agents" / "thesis-judge.md",
    "judge_opus": _ROOT / ".claude" / "agents" / "thesis-judge.md",
    "judge_fable": _ROOT / ".claude" / "agents" / "thesis-judge.md",
    # v17 (thesis-rewind-eval): three lens seats, per-seat prompt files
    "analyst_fundamentals": _ROOT / ".claude" / "agents" / "thesis-fundamentals.md",
    "analyst_catalyst": _ROOT / ".claude" / "agents" / "thesis-catalyst.md",
    "challenger": _ROOT / ".claude" / "agents" / "thesis-challenger.md",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow-out", required=True,
                    help="thesis workflow result JSON ({records: [...]})")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--model-alias", required=True)
    ap.add_argument("--efforts", required=True,
                    help="per-role effort, e.g. analyst=max,adversary=max,judge=xhigh"
                         " (v9 runs: ...,judge_opus=xhigh,judge_fable=xhigh)")
    ap.add_argument("--models", default=None,
                    help="per-role model for heterogeneous seats, e.g. "
                         "judge_opus=opus,judge_fable=fable; REQUIRED for a "
                         "2-seat (v9) run, refused otherwise")
    ap.add_argument("--market-context", default=None,
                    help="data/market/<date>.md the run's judges saw; journals "
                         "text + sha256 on every memo (omit when no block)")
    ap.add_argument("--db", default=str(_ROOT / "data" / "kairos.db"))
    args = ap.parse_args()

    records = json.loads(Path(args.workflow_out).read_text())["records"]
    roles = memo.judge_seat_roles(records)
    if ("judge_opus" in roles) != bool(args.models):
        raise SystemExit("--models judge_opus=...,judge_fable=... is required "
                         "for a 2-seat run and refused for a v8 run "
                         f"(roles inferred: {roles})")
    efforts = dict(kv.split("=") for kv in args.efforts.split(","))
    models = (dict(kv.split("=") for kv in args.models.split(","))
              if args.models else None)
    pin = memo.scorer_pin({r: _ROLE_FILES[r] for r in roles},
                          efforts=efforts, models=models)

    market_context = None
    if args.market_context:
        from kairos.thesis.market_context import load_block
        block = load_block(args.market_context)
        market_context = {"text": block.text, "sha256": block.sha256}

    manifest = {m["ticker"]: m for m in json.loads(Path(args.manifest).read_text())}

    conn = sqlite3.connect(args.db)
    memo.ensure_schema(conn)
    written, violations = 0, []
    for wf in records:
        t = wf["ticker"]
        if t not in manifest:
            raise SystemExit(f"{t}: not in manifest {args.manifest}")
        rec = memo.from_workflow(wf, manifest[t], model_alias=args.model_alias,
                                 agent_hashes=pin, market_context=market_context)
        try:
            memo.record_memo(conn, rec)
            written += 1
            judges = wf["judge"].get("judges")
            # era-aware readout: v16 judges carry p, not tier — a tier-keyed
            # f-string would KeyError inside the record loop
            if judges and all("p_outperform" in j for j in judges):
                detail = " ".join(
                    f"{j.get('seat', '?')}:{j['p_outperform']}" for j in judges)
            elif judges:
                detail = " ".join(f"{j['tier']}/{j['direction']}"
                                  for j in judges)
            else:
                detail = "single-judge"
            # per-seat readout: the RA-constancy tripwire reads these lines
            # at cohort readout; v16 seats print p, older seats print
            # direction/tier ("-" when absent)
            seat_pairs = (
                (("fundamentals", wf["fundamentals"]),
                 ("catalyst", wf["catalyst"]),
                 ("challenger", wf["challenger"]))
                if "challenger" in wf else
                (("analyst", wf["analyst"]), ("risk-averse", wf["adversary"])))
            seats = "; ".join(
                (f"{label} p={seat['p_outperform']}"
                 if "p_outperform" in seat else
                 f"{label} {seat.get('direction', '-')}/{seat.get('tier', '-')}")
                for label, seat in seat_pairs)
            print(f"{t}: recorded {rec.direction} {rec.conviction_tier} "
                  f"(judges: {detail}; {seats})")
        except memo.ContractViolation as e:
            violations.append((t, str(e)))
            print(f"{t}: CONTRACT VIOLATION — {e}", file=sys.stderr)
    conn.close()

    print(f"\n{written} memos recorded PIT -> {args.db}")
    if violations:
        print(f"{len(violations)} memo(s) REJECTED (fix + rerun those names): "
              f"{[t for t, _ in violations]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
