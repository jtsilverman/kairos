#!/usr/bin/env python3
"""The whole funnel's cohort walk for a sim date, on dossier-only tiers.

Per tier (from `score_sim_layer2.dossier_tier`): names entered layer 2, passed
the ruler, shortlisted by the verdict. Then the realized check, kept separate
from the tiers: mean alpha and beat count for the shortlist against every
other layer-2 entrant. There is no cap here; every shortlisted name counts.

CLI:
    score_sim_funnel.py --as-of 2026-06-01 [2026-05-01 ...] [--root data]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score_sim_layer2 import TIERS, dossier_tier, load_grades  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = _ROOT / "data"


def walk(as_of: str, *, root: Path | str = DEFAULT_ROOT) -> dict:
    root = Path(root)
    mid = json.loads((root / f"panel-results-sim-middle-{as_of}.json").read_text())["summary"]
    l3 = json.loads((root / f"panel-results-sim-l3-{as_of}.json").read_text())["summary"]
    grades = load_grades(as_of, root=root)
    o_p = root / f"outcomes-{as_of}.json"
    outcomes = json.loads(o_p.read_text()) if o_p.exists() else {}
    short = {r["slug"] for r in l3 if r.get("shortlist") is True}
    passed = {r["slug"] for r in mid if r.get("ruler_pass") is True}
    if not short <= passed:
        raise AssertionError(f"{as_of}: shortlisted names the ruler cut: {sorted(short - passed)}")
    tiers = {t: {"entered": 0, "passed": 0, "shortlisted": 0} for t in TIERS}
    ungraded = []
    for r in mid:
        g = grades.get(r["slug"])
        if g is None:
            ungraded.append(r["slug"])
            continue
        c = tiers[dossier_tier(g["grades"])]
        c["entered"] += 1
        c["passed"] += r["slug"] in passed
        c["shortlisted"] += r["slug"] in short

    def side(names):
        a = [outcomes[t]["alpha"] for t in names if isinstance(outcomes.get(t), dict) and "alpha" in outcomes[t]]
        return {"n": len(a), "mean_alpha": statistics.mean(a) if a else None,
                "beat": sum(x > 0 for x in a)}
    rest = [r["slug"] for r in mid if r["slug"] not in short]
    return {"as_of": as_of, "entered": len(mid), "passed": len(passed), "shortlisted": sorted(short),
            "tiers": tiers, "ungraded": ungraded, "short": side(short), "rest": side(rest)}


def _fmt(side: dict) -> str:
    if not side["n"]:
        return "no outcomes"
    return f"{side['n']} with outcome, mean alpha {side['mean_alpha']:+.1%}, {side['beat']} beat SPY"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", nargs="+", required=True)
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    a = ap.parse_args(argv)
    for d in a.as_of:
        w = walk(d, root=Path(a.root))
        print(f"\n=== {d}: {w['entered']} entered layer 2, {w['passed']} passed the ruler, "
              f"{len(w['shortlisted'])} shortlisted ===")
        print(f"  {'tier':6}{'entered':>9}{'passed':>8}{'short':>7}")
        for t in TIERS:
            c = w["tiers"][t]
            print(f"  {t:6}{c['entered']:>9}{c['passed']:>8}{c['shortlisted']:>7}")
        if w["ungraded"]:
            print(f"  ungraded (no tier): {len(w['ungraded'])}")
        print(f"  shortlist: {_fmt(w['short'])}")
        print(f"  the rest : {_fmt(w['rest'])}")
        print(f"  names: {' '.join(w['shortlisted'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
