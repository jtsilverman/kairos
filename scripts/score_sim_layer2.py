#!/usr/bin/env python3
"""thesis-exemplars: score a sim run's layer-2 rulings against the reference set.

WHY THIS EXISTS. Session analysis kept re-deriving tiers inline, and one
ad-hoc formula ("bad = two or fewer strong grades") labelled 16 clean
two-strong/two-adequate dossiers BAD and then reported layer 2 as letting
weak dossiers through. It was not: of 18 names that formula called weak,
only 2 carried any weak-or-absent grade, and the ruler caught both. Tiers
belong in code with the repo's own definitions, not in an analysis cell.

THE TWO AXES, kept separate on purpose.

`sort_exemplars.classify` is the reference set's own joint label: dossier
quality crossed with what the price then did (EXEMPLAR / THESIS_NOT_FOLLOWED
/ LUCK / NOTHING, where "visible" is strong on all four tests). That is the
end-to-end read.

Dossier quality alone needs its own scale, because "not visible" spans a
clean all-adequate dossier and one with two absent tests. This module grades
it on the WORST grade present, never on a count of strong ones:

    clean   no grade below adequate
    holed   exactly one weak-or-absent grade
    weak    two or more weak-or-absent grades

CLI:
    score_sim_layer2.py --as-of <date> [--root data] [--results <json>]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import sort_exemplars  # noqa: E402

DEFAULT_ROOT = sort_exemplars.DEFAULT_ROOT

#: Ordered worst to best, so `min` over a row's grades is the row's quality.
GRADE_RANK = {"absent": 0, "weak": 1, "adequate": 2, "strong": 3}
QUALITIES = ("weak", "holed", "clean")

#: The tier Jake reads, from the dossier ALONE (2026-09-23). Outcome is never
#: part of the label: live, the funnel sees only the dossier, so a tier that
#: folded in the realized window would grade the funnel against information it
#: will never have. The realized window rides along as a CHECK on the rubric
#: (do good dossiers beat SPY more often than mid ones?), never as the label.
TIERS = ("good", "mid", "bad")


def dossier_tier(grades: dict[str, str]) -> str:
    """good: strong on all four. mid: nothing below adequate. bad: a hole.

    `dossier_quality` answers "is the record whole"; this answers "how good is
    the thesis", which is the question the funnel is tuned on. They split
    differently: an all-adequate dossier is `clean` but only `mid`.
    """
    q = dossier_quality(grades)
    if q != "clean":
        return "bad"
    return "good" if all(g == "strong" for g in grades.values()) else "mid"


def load_grades(as_of: str, *, root: Path | str = DEFAULT_ROOT) -> dict[str, dict]:
    """Every graded name for a date, from BOTH grade files.

    `exemplars-<as_of>.json` holds the ~100-name tuning cohort (graded and
    joined to a realized window); `sim-grades-<as_of>.json` holds the layer-1
    survivors the draw never took. Reading only the first tiers two thirds of
    a sim date and reads as if it tiered the run.
    """
    root = Path(root)
    out: dict[str, dict] = {}
    ex = root / f"exemplars-{as_of}.json"
    if ex.exists():
        for r in json.loads(ex.read_text())["rows"]:
            out[r["ticker"]] = {"grades": r["grades"], "source": "cohort"}
    sim = root / f"sim-grades-{as_of}.json"
    if sim.exists():
        for r in json.loads(sim.read_text())["rows"]:
            out.setdefault(r["ticker"], {"grades": r["grades"], "source": "sim"})
    return out


class NoGradesError(RuntimeError):
    """A row whose grades are missing or carry an unknown word."""


def dossier_quality(grades: dict[str, str]) -> str:
    """Grade a dossier on its WORST test, not on how many tests are strong.

    Counting strong grades conflates "unspectacular but sound" with "has a
    hole": a two-strong/two-adequate dossier has nothing wrong with it, while
    one weak test is a named gap in the record. The funnel's ruler reads the
    gap, so the scale has to see it too.
    """
    if not grades:
        raise NoGradesError("no grades; a quality over zero tests is not 'weak'")
    unknown = sorted(set(grades.values()) - set(GRADE_RANK))
    if unknown:
        raise NoGradesError(f"unknown grade(s): {' '.join(unknown)}")
    holes = sum(1 for g in grades.values() if GRADE_RANK[g] <= GRADE_RANK["weak"])
    if holes == 0:
        return "clean"
    return "holed" if holes == 1 else "weak"


def visible(grades: dict[str, str]) -> bool:
    """Strong on all four tests (docs/four-tests-record.md, amended 2026-09-11).

    `sort_exemplars.visible` reads the sorter's raw per-test objects
    (`{grade, evidence, cite}`); the recorded `exemplars-<as_of>.json` rows
    carry the flat word per test, so the rule is applied here against that
    shape rather than reaching for a function expecting the other one.
    """
    if not grades:
        raise NoGradesError("no grades; visibility over zero tests is not False")
    return all(g == "strong" for g in grades.values())


def bear_wins(rulings: dict[str, str]) -> int:
    """Tests the bear won outright. The ruler's collapsed word is `bear`."""
    return sum(1 for v in rulings.values() if v == "bear")


def score(as_of: str, *, root: Path | str = DEFAULT_ROOT,
          results: Path | None = None) -> dict:
    """Layer 2's keep rate per dossier tier, plus the rubric's own check.

    Tiers come from the dossier alone. The realized window is reported beside
    them, never inside them: `tier_beat_rate` is the CHECK on the rubric (good
    dossiers should beat SPY more often than mid, or the grading is wrong), and
    `mean_alpha` says what the kept names went on to do.
    """
    root = Path(root)
    res_p = results or root / f"panel-results-sim-middle-{as_of}.json"
    recs = json.loads(Path(res_p).read_text())["summary"]
    graded_rows = load_grades(as_of, root=root)
    o_p = root / f"outcomes-{as_of}.json"
    outcomes = json.loads(o_p.read_text()) if o_p.exists() else {}

    by_tier: dict[str, list[dict]] = {t: [] for t in TIERS}
    by_quality: dict[str, list[dict]] = {q: [] for q in QUALITIES}
    ungraded = []
    for rec in recs:
        row = graded_rows.get(rec["slug"])
        if row is None:
            ungraded.append(rec["slug"])
            continue
        o = outcomes.get(rec["slug"], {})
        item = {"ticker": rec["slug"], "kept": bool(rec["ruler_pass"]),
                "alpha": o.get("alpha"), "beat": o.get("beat"),
                "bear_wins": bear_wins(rec["rulings"]),
                "source": row["source"],
                "tier": dossier_tier(row["grades"]),
                "quality": dossier_quality(row["grades"])}
        by_tier[item["tier"]].append(item)
        by_quality[item["quality"]].append(item)

    def block(items: list[dict]) -> dict:
        kept = [i for i in items if i["kept"]]
        cut = [i for i in items if not i["kept"]]
        alphas = [i["alpha"] for i in items if i["alpha"] is not None]
        k_alphas = [i["alpha"] for i in kept if i["alpha"] is not None]
        beats = [i["beat"] for i in items if i["beat"] is not None]
        return {"n": len(items), "kept": len(kept),
                "keep_rate": len(kept) / len(items) if items else None,
                "with_outcome": len(alphas),
                "tier_beat_rate": (sum(beats) / len(beats)) if beats else None,
                "mean_alpha": statistics.mean(alphas) if alphas else None,
                "mean_alpha_kept": statistics.mean(k_alphas) if k_alphas else None,
                "mean_bear_wins_kept": statistics.mean(
                    [i["bear_wins"] for i in kept]) if kept else None,
                "mean_bear_wins_cut": statistics.mean(
                    [i["bear_wins"] for i in cut]) if cut else None,
                "cut_names": sorted(i["ticker"] for i in cut),
                "kept_names": sorted(i["ticker"] for i in kept)}

    return {"as_of": as_of, "records": len(recs),
            "graded": len(recs) - len(ungraded), "ungraded": sorted(ungraded),
            "by_tier": {t: block(by_tier[t]) for t in TIERS if by_tier[t]},
            "by_quality": {q: block(by_quality[q]) for q in QUALITIES if by_quality[q]},
            "tier_counts": Counter(i["tier"] for v in by_tier.values() for i in v)}


def _pct(x) -> str:
    return "     n/a" if x is None else f"{x:+7.1%}"


def _rate(x) -> str:
    return "    n/a" if x is None else f"{x:6.0%}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", required=True, nargs="+")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--results", type=Path)
    ap.add_argument("--names", action="store_true",
                    help="list the cut good names and the kept bad ones")
    a = ap.parse_args(argv)
    for as_of in a.as_of:
        s = score(as_of, root=Path(a.root), results=a.results)
        print(f"\n=== {s['as_of']}: {s['records']} names into layer 2, "
              f"{s['graded']} graded, {len(s['ungraded'])} ungraded ===")
        print(f"  {'tier':6}{'n':>4}{'kept':>6}{'keep':>7}"
              f"{'beat SPY':>10}{'alpha':>9}{'kept a':>9}{'bw kept':>9}{'bw cut':>8}")
        for t in TIERS:
            b = s["by_tier"].get(t)
            if not b:
                continue
            bw_k = "    n/a" if b["mean_bear_wins_kept"] is None else f"{b['mean_bear_wins_kept']:7.2f}"
            bw_c = "   n/a" if b["mean_bear_wins_cut"] is None else f"{b['mean_bear_wins_cut']:6.2f}"
            print(f"  {t:6}{b['n']:>4}{b['kept']:>6}{b['keep_rate']:>7.0%}"
                  f"{_rate(b['tier_beat_rate']):>10}{_pct(b['mean_alpha']):>9}"
                  f"{_pct(b['mean_alpha_kept']):>9}{bw_k:>9}{bw_c:>8}")
        if s["ungraded"]:
            print(f"  ungraded (no tier): {' '.join(s['ungraded'][:12])}"
                  f"{' ...' if len(s['ungraded']) > 12 else ''}")
        if a.names:
            good, bad = s["by_tier"].get("good"), s["by_tier"].get("bad")
            if good and good["cut_names"]:
                print(f"  GOOD cut : {' '.join(good['cut_names'])}")
            if bad and bad["kept_names"]:
                print(f"  BAD kept : {' '.join(bad['kept_names'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
