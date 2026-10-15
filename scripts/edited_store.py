#!/usr/bin/env python3
"""One durable store of the opus editor's checked cases, per date.

The editor is the expensive seat, and its output is reusable by every later
verdict, ranker or rulings experiment on the same name and date. Each run used
to leave it in a different place (a verdict record's `edited_cases`, an
editor-only batch file), so a later run could not find it and paid again.

`collect` sweeps every known location into `data/edited/<as_of>.json`
({ticker: edited_cases}); it never overwrites an entry already stored, so the
first checked read of a name is the one every later run reuses. `missing`
prints which of a list of tickers still need the editor.

CLI:
    edited_store.py collect [--root data]
    edited_store.py missing --as-of <date> --tickers A B C [--root data]
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = _ROOT / "data"


def _records(path: Path) -> list[dict]:
    """Records from a results file or a batch return, either saved shape."""
    obj = json.loads(path.read_text())
    if isinstance(obj.get("summary"), str):
        obj = obj["result"]
    return obj.get("summary") or []


def _sources(root: Path) -> list[Path]:
    pats = ["panel-results-*.json", "scratch/sim-ed-out-*.json", "scratch/unruled/ed-out-*.json",
            "scratch/unruled/out-*.json"]
    return sorted(Path(p) for pat in pats for p in glob.glob(str(root / pat)))


def load(as_of: str, *, root: Path | str = DEFAULT_ROOT) -> dict[str, dict]:
    p = Path(root) / "edited" / f"{as_of}.json"
    return json.loads(p.read_text()) if p.exists() else {}


def collect(*, root: Path | str = DEFAULT_ROOT) -> dict[str, int]:
    root = Path(root)
    found: dict[str, dict[str, dict]] = {}
    for src in _sources(root):
        for rec in _records(src):
            ec, as_of, slug = rec.get("edited_cases"), rec.get("as_of"), rec.get("slug")
            if ec and as_of and slug:
                found.setdefault(as_of, {}).setdefault(slug, ec)
    counts = {}
    (root / "edited").mkdir(exist_ok=True)
    for as_of, new in found.items():
        store = load(as_of, root=root)
        added = 0
        for slug, ec in new.items():
            if slug not in store:
                store[slug] = ec
                added += 1
        (root / "edited" / f"{as_of}.json").write_text(json.dumps(store, sort_keys=True))
        counts[as_of] = len(store)
        print(f"{as_of}: {len(store)} names stored ({added} new)")
    return counts


def missing(as_of: str, tickers: list[str], *, root: Path | str = DEFAULT_ROOT) -> list[str]:
    store = load(as_of, root=root)
    return [t for t in tickers if t not in store]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--root", default=str(DEFAULT_ROOT))
    m = sub.add_parser("missing")
    m.add_argument("--as-of", required=True)
    m.add_argument("--tickers", nargs="+", required=True)
    m.add_argument("--root", default=str(DEFAULT_ROOT))
    a = ap.parse_args(argv)
    if a.cmd == "collect":
        collect(root=Path(a.root))
    else:
        print(" ".join(missing(a.as_of, a.tickers, root=Path(a.root))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
