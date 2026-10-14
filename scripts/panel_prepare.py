#!/usr/bin/env python3
"""thesis-exemplars unit 8: compact real-name args for the funnel workflow.

`run_panel.py` scrubs every dossier and hands the panel a `CO-nnn` slug.
This spec reads real names, as production will, so this writes the compact
args `{asOf, root, names: [{ticker, docIds}]}` from the cohort draw
(`data/outcomes-<as_of>.json`) and the rewind manifest. Every seat reads
the full dossier by path, which the workflow derives from `root`, `asOf`
and the ticker, so the args stay about 11KB per hundred names.

`--sample <contrast-sample.json> --lists good,edge` restricts the names to
the sample's lists at that date (layer 1 runs on GOOD plus EDGE, layer 2 on
GOOD plus BAD); the sample's classes and alphas never enter the args.

CLI:
    panel_prepare.py --as-of <date> [--root data] [--sample <json> --lists good,edge]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = _ROOT / "data"


class MissingDossierError(RuntimeError):
    """A drawn name with no compiled dossier."""


class UnknownSampleNameError(RuntimeError):
    """A sample name that is not in the cohort draw at that date."""


def prepare(as_of: str, *, root: Path | str = DEFAULT_ROOT,
            sample: Path | None = None, lists: tuple[str, ...] = (),
            names_from: Path | None = None, live: bool = False) -> dict:
    root = Path(root)
    # A live date compiles to dossiers/<as_of>/ (no --rewind); past dates to rewind-<as_of>/.
    dname = as_of if live else f"rewind-{as_of}"
    ddir = root / "dossiers" / dname
    if names_from is not None:
        # The full sim runs every layer-1 survivor, not the graded cohort.
        # `outcomes-<as_of>.json` holds only the ~100 names that were drawn and
        # scored, so gating on it would silently shrink a 458-name sim to 282.
        # Outcomes are a SCORING input, needed after the shortlist exists, not
        # a precondition for reading a dossier.
        wanted = set(json.loads(Path(names_from).read_text()))
        tickers = sorted(wanted)
    else:
        outcomes_p = root / f"outcomes-{as_of}.json"
        if not outcomes_p.exists():
            raise FileNotFoundError(f"{outcomes_p}: the cohort draw; build it first")
        tickers = sorted(json.loads(outcomes_p.read_text()))
        if sample is not None:
            picks = json.loads(Path(sample).read_text())
            wanted = {r["ticker"] for name in lists for r in picks[name] if r["as_of"] == as_of}
            absent = sorted(wanted - set(tickers))
            if absent:
                raise UnknownSampleNameError(f"{as_of}: sample names not in the cohort draw: {' '.join(absent)}")
            tickers = [t for t in tickers if t in wanted]
    manifest = {r["ticker"]: r for r in json.loads((ddir / "manifest.json").read_text())}
    names = []
    for t in tickers:
        row = manifest.get(t)
        if row is None or not (ddir / f"{t}.md").exists():
            raise MissingDossierError(f"{t}@{as_of}: drawn but no dossier compiled")
        names.append({"ticker": t, "docIds": " ".join(row["doc_ids"])})
    out = {"asOf": as_of, "root": str(root.resolve()), "names": names}
    if live:
        out["dossierDir"] = dname
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--sample", type=Path, help="data/contrast-sample.json")
    ap.add_argument("--lists", default="", help="comma-separated lists of the sample: good,edge")
    ap.add_argument("--names-from", type=Path,
                    help="JSON list of tickers to run (the full sim's layer-1 "
                         "survivors); bypasses the graded cohort draw")
    ap.add_argument("--tag", default="", help="output filename tag, e.g. sim")
    ap.add_argument("--live", action="store_true", help="read dossiers/<as_of>/ (a live compile), not rewind-<as_of>/")
    a = ap.parse_args(argv)
    lists = tuple(x for x in a.lists.split(",") if x)
    if bool(a.sample) != bool(lists):
        ap.error("--sample and --lists go together")
    if a.names_from and (a.sample or lists):
        ap.error("--names-from is its own name source; it takes no --sample/--lists")
    args = prepare(a.as_of, root=Path(a.root), sample=a.sample, lists=lists,
                   names_from=a.names_from, live=a.live)
    tag = a.tag and f"-{a.tag}" or (f"-{'-'.join(lists)}" if lists else "")
    out = Path(a.root) / f"panel-args-real{tag}-{a.as_of}.json"
    out.write_text(json.dumps(args, indent=1))
    print(f"{a.as_of}: {len(args['names'])} names -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
