#!/usr/bin/env python3
"""thesis-exemplars unit 11: layer-2 args from middle-layer results.

The verdict layer (editor, then the verdict seat) reads each name's bull
case, bear case and rulings. Those run to 10 KB or more per name and the
workflow's args must stay small, so each name's `cases` goes to
`data/cases-<as_of>/<ticker>.json` (the editor reads it with the Read tool
after the dossier) and the args carry `casesPath` plus the small parts the
workflow needs in code: the four ruling words and the overall word. Every
name given runs editor and verdict, pass or not (layer 2's force-pass).

CLI:
    verdict_prepare.py --as-of <date> --results r1.json [r2.json ...] --args data/panel-args-real-<date>.json
                       [--sample data/contrast-sample.json --lists good,bad] [--root data]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = _ROOT / "data"


def prepare(as_of: str, results: list[Path], *, root: Path | str = DEFAULT_ROOT,
            doc_ids: dict[str, str], only: set[str] | None = None) -> dict:
    root = Path(root)
    cdir = root / f"cases-{as_of}"
    cdir.mkdir(parents=True, exist_ok=True)
    names = []
    for rp in results:
        res = json.loads(Path(rp).read_text())
        for r in res["summary"]:
            if r["as_of"] != as_of or (only is not None and r["slug"] not in only):
                continue
            path = cdir / f"{r['slug']}.json"
            path.write_text(json.dumps(r["cases"], indent=1))
            names.append({"ticker": r["slug"], "docIds": doc_ids[r["slug"]],
                          "casesPath": str(path), "rulings": r["rulings"], "overall": r["overall"]})
    return {"asOf": as_of, "root": str(root.resolve()), "layer": "verdict", "names": names}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--results", nargs="+", required=True)
    ap.add_argument("--args", required=True, help="a panel-args file; doc ids per ticker come from it")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--sample", type=Path)
    ap.add_argument("--lists", default="")
    a = ap.parse_args(argv)
    doc_ids = {n["ticker"]: n["docIds"] for n in json.loads(Path(a.args).read_text())["names"]}
    only = None
    if a.sample:
        picks = json.loads(a.sample.read_text())
        only = {r["ticker"] for name in a.lists.split(",") if name for r in picks[name] if r["as_of"] == a.as_of}
    args = prepare(a.as_of, [Path(p) for p in a.results], root=Path(a.root), doc_ids=doc_ids, only=only)
    out = Path(a.root) / f"panel-args-verdict-{a.as_of}.json"
    out.write_text(json.dumps(args, indent=1))
    print(f"{a.as_of}: {len(args['names'])} names, cases under cases-{a.as_of}/ -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
