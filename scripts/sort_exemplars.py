#!/usr/bin/env python3
"""thesis-exemplars unit 2: marshal the blind sorter, then sort the cohort.

The reference set is built in two steps that never touch. `prepare` writes
the sorter workflow's args: each drawn name's REAL dossier path and doc ids,
and nothing about what happened after. `record` takes the sorter's blind
grades back, joins each to the realized window in `outcomes-<as_of>.json`,
applies the mechanical "thesis visible" rule from docs/four-tests-record.md, and
sorts the name into one of four classes:

    visible & beat     EXEMPLAR
    visible & !beat    THESIS_NOT_FOLLOWED
    !visible & beat    LUCK
    !visible & !beat   NOTHING

Jake signs EXEMPLAR rows by flipping `signed` in the file; `record` keeps a
signature already given. The killed labeller's blind conviction read rides
along as a cross-check column when its files exist, never as the label.

CLI:
    sort_exemplars.py prepare --as-of <date> [--root data]
    sort_exemplars.py record  --as-of <date> --rows <sorter-out.json> [--root data]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_HERE))

import four_tests  # noqa: E402

DEFAULT_ROOT = _ROOT / "data"
CLASSES = ("EXEMPLAR", "THESIS_NOT_FOLLOWED", "LUCK", "NOTHING")


class MissingDossierError(RuntimeError):
    """A drawn name with no compiled dossier. Dropping it shrinks the cohort."""


class MissingGradeError(RuntimeError):
    """A drawn name the sorter never graded."""


class UnknownTickerError(RuntimeError):
    """A grade for a name outside the cohort draw."""


class BadGradeError(ValueError):
    """A grade outside the rubric's four."""


def visible(tests: dict) -> bool:
    """docs/four-tests-record.md "Thesis visible": strong on all four tests.
    Mechanical on purpose. AMENDED 2026-09-11 from three-of-four-adequate,
    which 98 of 100 February names passed: the screen already admits sound
    companies, so the bar sat below the population. All-four-strong picks 27
    of 100 there and 25 of 100 in March, and those tiers beat SPY 70% and 64%
    against cohort rates of 45% and 48%; every lower tier sat at or under the
    cohort rate."""
    grades = []
    for k in four_tests.KEYS:
        g = tests[k]["grade"]
        if g not in four_tests.GRADES:
            raise BadGradeError(f"{k}: {g!r} is not one of {four_tests.GRADES}")
        grades.append(g)
    return all(g == "strong" for g in grades)


def classify(vis: bool, beat: bool) -> str:
    if vis:
        return "EXEMPLAR" if beat else "THESIS_NOT_FOLLOWED"
    return "LUCK" if beat else "NOTHING"


def _outcomes(as_of: str, root: Path) -> dict[str, dict]:
    p = root / f"outcomes-{as_of}.json"
    if not p.exists():
        raise FileNotFoundError(f"{p}: the cohort draw and its window; build it first")
    return json.loads(p.read_text())


def _manifest(as_of: str, root: Path) -> dict[str, dict]:
    p = root / "dossiers" / f"rewind-{as_of}" / "manifest.json"
    if not p.exists():
        raise FileNotFoundError(f"{p}: no rewind compile for {as_of}")
    return {r["ticker"]: r for r in json.loads(p.read_text())}


def exemplars_path(as_of: str, root: Path | str = DEFAULT_ROOT) -> Path:
    return Path(root) / f"exemplars-{as_of}.json"


def sorter_args(as_of: str, *, root: Path | str = DEFAULT_ROOT) -> dict:
    """What the sorter workflow fans out over. No outcome field, by design."""
    root = Path(root)
    outcomes = _outcomes(as_of, root)
    manifest = _manifest(as_of, root)
    # Compact on purpose: 100 names of full paths and id arrays is ~25KB of
    # args pasted through the driving session per launch. The workflow
    # derives `<root>/dossiers/rewind-<asOf>/<ticker>.md` and splits the ids.
    ddir = root / "dossiers" / f"rewind-{as_of}"
    names = []
    for t in sorted(outcomes):
        row = manifest.get(t)
        if row is None or not (ddir / f"{t}.md").exists():
            raise MissingDossierError(f"{t}@{as_of}: drawn but no dossier compiled")
        names.append({"ticker": t, "docIds": " ".join(row["doc_ids"])})
    return {"asOf": as_of, "root": str(root.resolve()), "names": names}


def _labeller_columns(as_of: str, root: Path) -> dict[str, dict]:
    """The killed labeller's blind read, keyed by ticker, when its files exist."""
    slugs = root / f"panel-slugs-{as_of}.json"
    buckets = root / f"buckets-{as_of}.json"
    if not (slugs.exists() and buckets.exists()):
        return {}
    mapping = json.loads(slugs.read_text())
    out = {}
    for r in json.loads(buckets.read_text())["rows"]:
        t = mapping.get(r["slug"])
        if t:
            out[t] = {"labeller_read": r["dossier_read"], "labeller_bucket": r["bucket"],
                      "labeller_cause": r.get("cause")}
    return out


def record(as_of: str, rows: list[dict], *, root: Path | str = DEFAULT_ROOT) -> dict:
    root = Path(root)
    outcomes = _outcomes(as_of, root)
    cross = _labeller_columns(as_of, root)
    path = exemplars_path(as_of, root)
    signed_before: dict[str, bool] = {}
    if path.exists():
        signed_before = {r["ticker"]: bool(r.get("signed"))
                         for r in json.loads(path.read_text())["rows"]}

    by_ticker = {}
    for r in rows:
        t = r["ticker"]
        if t not in outcomes:
            raise UnknownTickerError(f"{t}@{as_of}: graded but not in the cohort draw")
        if t in by_ticker:
            raise UnknownTickerError(f"{t}@{as_of}: graded twice")
        by_ticker[t] = r
    missing = sorted(set(outcomes) - set(by_ticker))
    if missing:
        raise MissingGradeError(f"{as_of}: {len(missing)} drawn names have no grade: "
                                f"{' '.join(missing)}")

    out_rows = []
    counts = {c: 0 for c in CLASSES}
    for t in sorted(by_ticker):
        r, o = by_ticker[t], outcomes[t]
        vis = visible(r["tests"])
        cls = classify(vis, bool(o["beat"]))
        counts[cls] += 1
        row = {"ticker": t, "as_of": as_of, "class": cls, "visible": vis,
               "beat": bool(o["beat"]), "alpha": round(o["alpha"], 4),
               **({"beat_2q": bool(o["beat_2q"]), "alpha_2q": round(o["alpha_2q"], 4)}
                  if "alpha_2q" in o else {}),
               "grades": {k: r["tests"][k]["grade"] for k in four_tests.KEYS},
               "tests": r["tests"], "driver": r["driver"], "summary": r["summary"],
               "signed": signed_before.get(t, False)}
        row.update(cross.get(t, {}))
        out_rows.append(row)
    out = {"as_of": as_of, "n": len(out_rows), "counts": counts,
           "rule": "visible = strong on all four tests (amended 2026-09-11); "
                   "class = visible x beat SPY over the window in outcomes-<as_of>.json",
           "rows": out_rows}
    path.write_text(json.dumps(out, indent=1))
    return out


def add_two_quarter_window(as_of: str, *, root: Path | str = DEFAULT_ROOT,
                           horizon_days: int = 182) -> dict[str, dict]:
    """Unit 7: write `alpha_2q` / `beat_2q` beside the frozen one-quarter
    fields in outcomes-<as_of>.json. The 91-day constant is untouched; the
    longer horizon is passed explicitly."""
    import datetime as dt
    import score_rewind
    root = Path(root)
    p = root / f"outcomes-{as_of}.json"
    outcomes = json.loads(p.read_text())
    end = (dt.date.fromisoformat(as_of) + dt.timedelta(days=horizon_days + 21)).isoformat()
    spy = score_rewind._closes("SPY", as_of, end)
    for t in sorted(outcomes):
        o = score_rewind.outcome(score_rewind._closes(t, as_of, end), spy,
                                 as_of=as_of, horizon_days=horizon_days)
        outcomes[t]["alpha_2q"] = o["alpha"]
        outcomes[t]["beat_2q"] = o["beat"]
        outcomes[t]["exit_date_2q"] = o["exit_date"]
    p.write_text(json.dumps(outcomes, indent=1))
    return outcomes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=("prepare", "record", "outcomes-2q"))
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--rows", type=Path, help="record: the sorter workflow's rows")
    args = ap.parse_args(argv)
    root = Path(args.root)
    if args.stage == "outcomes-2q":
        out = add_two_quarter_window(args.as_of, root=root)
        beats = sum(o["beat_2q"] for o in out.values())
        print(f"{args.as_of}: two-quarter window written for {len(out)} names, {beats} beat SPY")
        return 0
    if args.stage == "prepare":
        out = sorter_args(args.as_of, root=root)
        p = root / f"sorter-args-{args.as_of}.json"
        p.write_text(json.dumps(out, indent=1))
        print(f"{args.as_of}: {len(out['names'])} names -> {p}")
        return 0
    if not args.rows:
        ap.error("record needs --rows")
    payload = json.loads(args.rows.read_text())
    rows = payload["rows"] if isinstance(payload, dict) else payload
    out = record(args.as_of, rows, root=root)
    print(f"{args.as_of}: {out['n']} sorted {out['counts']} -> {exemplars_path(args.as_of, root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
