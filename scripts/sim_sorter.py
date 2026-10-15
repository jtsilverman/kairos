#!/usr/bin/env python3
"""thesis-exemplars: grade the sim's UNGRADED dossiers, blind.

`sort_exemplars` marshals and records the tuning cohort: the ~100 names per
date that were drawn, graded and joined to a realized window. The full sim
runs every layer-1 survivor (133/168/157), so on each date roughly a third
of the names have no grade at all and cannot be tiered. Reporting layer 2's
keep rates over only the graded two thirds measures a subset and reads as if
it measured the run.

This module is the other two thirds. It writes sorter args for exactly the
names a date is missing, and records the returned grades to
`sim-grades-<as_of>.json`.

Two things it deliberately does NOT do.

It does not touch `exemplars-<as_of>.json`. That file is the reference set of
record, its rows carry a realized window, and `record()` refuses a ticker
outside the cohort draw. An ungraded survivor has no outcome row, so folding
it in would either fail or force a fabricated one.

It does not assign a class. `class` is dossier quality crossed with what the
price did; these names have no outcome. The grades alone are what the funnel
could see live, and the tier a name lands in is computed from them by
`score_sim_layer2.dossier_quality`.

CLI:
    sim_sorter.py prepare --as-of <date> [--root data]
    sim_sorter.py record  --as-of <date> --rows <sorter-out.json> [--root data]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT / "code" / "src"))
sys.path.insert(0, str(_HERE))

import four_tests  # noqa: E402
import sort_exemplars  # noqa: E402

DEFAULT_ROOT = sort_exemplars.DEFAULT_ROOT


class NothingUngradedError(RuntimeError):
    """Every sim name already carries a grade; there is nothing to prepare."""


def grades_path(as_of: str, root: Path | str = DEFAULT_ROOT) -> Path:
    return Path(root) / f"sim-grades-{as_of}.json"


def _sim_names(as_of: str, root: Path) -> list[str]:
    p = root / f"panel-args-real-sim-{as_of}.json"
    if not p.exists():
        raise FileNotFoundError(f"{p}: the sim's layer-2 args; write them first")
    return [n["ticker"] for n in json.loads(p.read_text())["names"]]


def _already_graded(as_of: str, root: Path) -> set[str]:
    """Names carrying a grade from either file. Both count, so a rerun is a
    no-op rather than a second pass over names already read."""
    graded: set[str] = set()
    ex = sort_exemplars.exemplars_path(as_of, root)
    if ex.exists():
        graded |= {r["ticker"] for r in json.loads(ex.read_text())["rows"]}
    sim = grades_path(as_of, root)
    if sim.exists():
        graded |= {r["ticker"] for r in json.loads(sim.read_text())["rows"]}
    return graded


def ungraded(as_of: str, *, root: Path | str = DEFAULT_ROOT) -> list[str]:
    root = Path(root)
    return sorted(set(_sim_names(as_of, root)) - _already_graded(as_of, root))


def sorter_args(as_of: str, *, root: Path | str = DEFAULT_ROOT, live: bool = False) -> dict:
    """The blind sorter's args for the ungraded names. No outcome field."""
    root = Path(root)
    names = ungraded(as_of, root=root)
    if not names:
        raise NothingUngradedError(f"{as_of}: every sim name is already graded")
    dname = as_of if live else f"rewind-{as_of}"
    ddir = root / "dossiers" / dname
    manifest = {r["ticker"]: r for r in
                json.loads((ddir / "manifest.json").read_text())}
    out = []
    for t in names:
        row = manifest.get(t)
        if row is None or not (ddir / f"{t}.md").exists():
            raise sort_exemplars.MissingDossierError(
                f"{t}@{as_of}: in the sim but no dossier compiled")
        out.append({"ticker": t, "docIds": " ".join(row["doc_ids"])})
    res = {"asOf": as_of, "root": str(root.resolve()), "names": out}
    if live:
        res["dossierDir"] = dname
    return res


def record(as_of: str, rows: list[dict], *, root: Path | str = DEFAULT_ROOT) -> dict:
    """Merge returned grades into `sim-grades-<as_of>.json`.

    Merges rather than overwrites: the fan-out runs in batches, and a whole
    write would drop every batch but the last.
    """
    root = Path(root)
    sim_names = set(_sim_names(as_of, root))
    path = grades_path(as_of, root)
    merged: dict[str, dict] = {}
    if path.exists():
        merged = {r["ticker"]: r for r in json.loads(path.read_text())["rows"]}
    for r in rows:
        t = r["ticker"]
        if t not in sim_names:
            raise sort_exemplars.UnknownTickerError(
                f"{t}@{as_of}: graded but not in the sim")
        merged[t] = {"ticker": t, "as_of": as_of,
                     "grades": {k: r["tests"][k]["grade"] for k in four_tests.KEYS},
                     "tests": r["tests"], "driver": r["driver"],
                     "summary": r["summary"]}
    out = {"as_of": as_of, "n": len(merged),
           "note": "blind grades for sim names outside the tuning cohort; no "
                   "class and no outcome, because these names have no realized "
                   "window in outcomes-<as_of>.json",
           "rows": [merged[t] for t in sorted(merged)]}
    path.write_text(json.dumps(out, indent=1))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=("prepare", "record", "count"))
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--rows", type=Path, help="record: the sorter workflow's rows")
    ap.add_argument("--live", action="store_true", help="read dossiers/<as_of>/ (a live compile)")
    a = ap.parse_args(argv)
    root = Path(a.root)
    if a.stage == "count":
        names = ungraded(a.as_of, root=root)
        print(f"{a.as_of}: {len(names)} ungraded of "
              f"{len(_sim_names(a.as_of, root))} sim names")
        print(" ".join(names))
        return 0
    if a.stage == "prepare":
        out = sorter_args(a.as_of, root=root, live=a.live)
        p = root / f"sim-sorter-args-{a.as_of}.json"
        p.write_text(json.dumps(out, indent=1))
        print(f"{a.as_of}: {len(out['names'])} ungraded names -> {p}")
        return 0
    if not a.rows:
        ap.error("record needs --rows")
    payload = json.loads(a.rows.read_text())
    rows = payload["rows"] if isinstance(payload, dict) else payload
    out = record(a.as_of, rows, root=root)
    print(f"{a.as_of}: {out['n']} graded -> {grades_path(a.as_of, root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
