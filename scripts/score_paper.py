#!/usr/bin/env python3
"""live-paper: the paper ledger and its 6, 12 and 24-week scorer.

`open` writes `data/paper/<as_of>.json` once, from a finished live run: every
shortlisted name with the verdict's number, driver and rating basis, and the
blind dossier tier, plus every other layer-2 entrant as the comparison group.
It refuses to overwrite: the picks of a month are a record, not a draft.

`score` fills each horizon's window the first day its exit close exists,
through the frozen `score_rewind.outcome`, and leaves an unclosed window
`pending`. A filled window is never recomputed, so the ledger is append-only.

Windows are anchored on the ledger's `entry_after` date (entry = first close
strictly after it), which defaults to `as_of`. A run whose dossiers were
compiled after its as-of date anchors on the compile date instead, so the paper
entry never precedes information the seats read. `set-entry` records that
anchor once, and only while every window is still pending.

CLI:
    score_paper.py open  --as-of 2026-10-07 [--entry-after 2026-10-12]
    score_paper.py set-entry --as-of 2026-10-07 --entry-after 2026-10-12
    score_paper.py score [--as-of 2026-10-07 ...]    (default: every ledger)
    score_paper.py report
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score_rewind  # noqa: E402
from score_sim_layer2 import dossier_tier, load_grades  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = _ROOT / "data"
HORIZONS = {"6w": 42, "12w": 84, "24w": 168}


class LedgerExistsError(RuntimeError):
    pass


class EntryLockedError(RuntimeError):
    """The anchor moves only before any window is filled."""


def ledger_path(as_of: str, root: Path) -> Path:
    return root / "paper" / f"{as_of}.json"


def _check_entry_after(as_of: str, entry_after: str) -> str:
    if dt.date.fromisoformat(entry_after) < dt.date.fromisoformat(as_of):
        raise ValueError(f"entry_after {entry_after} precedes as_of {as_of}")
    return entry_after


def open_ledger(as_of: str, *, root: Path | str = DEFAULT_ROOT,
                entry_after: str | None = None) -> dict:
    root = Path(root)
    p = ledger_path(as_of, root)
    if p.exists():
        raise LedgerExistsError(f"{p} exists; a month's picks are written once")
    entry_after = _check_entry_after(as_of, entry_after or as_of)
    mid = json.loads((root / f"panel-results-sim-middle-{as_of}.json").read_text())["summary"]
    l3 = {r["slug"]: r for r in json.loads((root / f"panel-results-sim-l3-{as_of}.json").read_text())["summary"]}
    grades = load_grades(as_of, root=root)

    def tier(t):
        g = grades.get(t)
        return dossier_tier(g["grades"]) if g else None
    picks, rest = [], []
    for r in mid:
        t = r["slug"]
        v = l3.get(t)
        if v and v.get("shortlist") is True:
            picks.append({"ticker": t, "p_judge": v.get("p_judge"), "thesis": v.get("thesis"),
                          "rating_basis": v.get("rating_basis"), "tier": tier(t), "windows": {}})
        else:
            rest.append({"ticker": t, "ruler_pass": bool(r.get("ruler_pass")), "tier": tier(t), "windows": {}})
    led = {"as_of": as_of, "entry_after": entry_after, "opened": dt.date.today().isoformat(),
           "horizons": HORIZONS,
           "note": "paper only; nothing bought. picks = every shortlisted name, equal weight; "
                   "rest = every other layer-2 entrant, the comparison group",
           "picks": sorted(picks, key=lambda x: x["ticker"]), "rest": sorted(rest, key=lambda x: x["ticker"])}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(led, indent=1))
    return led


def set_entry(led: dict, entry_after: str) -> dict:
    """Move the window anchor. Refused once any window holds a result."""
    filled = [r["ticker"] for r in led["picks"] + led["rest"]
              if any(isinstance(w, dict) for w in r["windows"].values())]
    if filled:
        raise EntryLockedError(f"{len(filled)} rows already have a filled window; the anchor is fixed")
    led["entry_after"] = _check_entry_after(led["as_of"], entry_after)
    return led


def fill(led: dict, closes) -> int:
    """Fill every pending window whose exit close exists. `closes(ticker, start, end)`
    returns ascending (date, close). Returns the number of windows filled."""
    anchor, n = led.get("entry_after", led["as_of"]), 0
    today = dt.date.today()
    for label, days in led["horizons"].items():
        exit_day = dt.date.fromisoformat(anchor) + dt.timedelta(days=days)
        if exit_day > today:
            continue
        end = (exit_day + dt.timedelta(days=10)).isoformat()
        spy = None
        for row in led["picks"] + led["rest"]:
            if row["windows"].get(label) not in (None, "pending"):
                continue
            spy = spy if spy is not None else closes("SPY", anchor, end)
            try:
                o = score_rewind.outcome(closes(row["ticker"], anchor, end), spy, as_of=anchor, horizon_days=days)
                row["windows"][label] = o
                n += 1
            except score_rewind.IncompleteWindowError:
                row["windows"][label] = "pending"
    for row in led["picks"] + led["rest"]:
        for label in led["horizons"]:
            row["windows"].setdefault(label, "pending")
    return n


def summary(rows: list[dict], label: str) -> dict | None:
    a = [r["windows"][label]["alpha"] for r in rows if isinstance(r["windows"].get(label), dict)]
    if not a:
        return None
    return {"n": len(a), "mean": statistics.mean(a), "median": statistics.median(a), "beat": sum(x > 0 for x in a)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("open", "set-entry", "score", "report"))
    ap.add_argument("--as-of", nargs="*")
    ap.add_argument("--entry-after", default=None)
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    a = ap.parse_args(argv)
    root = Path(a.root)
    if a.cmd == "open":
        led = open_ledger(a.as_of[0], root=root, entry_after=a.entry_after)
        print(f"{led['as_of']}: {len(led['picks'])} paper picks, {len(led['rest'])} in the comparison group, "
              f"entry after {led['entry_after']}")
        return 0
    if a.cmd == "set-entry":
        if not a.as_of or len(a.as_of) != 1 or not a.entry_after:
            ap.error("set-entry needs exactly one --as-of and --entry-after")
        p = ledger_path(a.as_of[0], root)
        led = set_entry(json.loads(p.read_text()), a.entry_after)
        p.write_text(json.dumps(led, indent=1))
        print(f"{a.as_of[0]}: entry after {led['entry_after']}")
        return 0
    dates = a.as_of or sorted(p.stem for p in (root / "paper").glob("*.json"))
    for d in dates:
        p = ledger_path(d, root)
        led = json.loads(p.read_text())
        if a.cmd == "score":
            n = fill(led, score_rewind._closes)
            p.write_text(json.dumps(led, indent=1))
            print(f"{d}: {n} windows filled")
        for label in led["horizons"]:
            s, r = summary(led["picks"], label), summary(led["rest"], label)
            if s is None:
                print(f"  {d} {label}: pending")
                continue
            print(f"  {d} {label}: picks {s['n']} mean {s['mean']:+.1%} median {s['median']:+.1%} "
                  f"beat {s['beat']}/{s['n']} | rest mean {r['mean']:+.1%} ({r['n']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
