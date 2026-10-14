#!/usr/bin/env python3
"""Split a triage packet across scripts that fit the workflow size cap, and
merge their returns into one cascade result.

A Workflow script is capped at 524,288 bytes. A cohort's spliced packet grew
past it (2026-10-06: 299 rows, 584,785 bytes). Triage is per row and
independent under TWO_NO, so splitting the packet changes nothing about any
name's verdict; the merge sums the counts and concatenates keeps and rows.

CLI:
    cascade_parts.py split --as-of D --out-prefix data/scratch/cascade-D-p
    cascade_parts.py merge --as-of D --out-prefix data/scratch/cascade-out-D-p --dest data/scratch/cascade-out-D.json
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_cascade_run  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent
CAP = 524_288
HEADROOM = 0.9   # stay well under the cap


class PartsError(RuntimeError):
    pass


def split(as_of: str, packet: list[dict], src: str, out_prefix: str) -> list[str]:
    n = 1
    while True:
        size = -(-len(packet) // n)
        parts = [packet[i:i + size] for i in range(0, len(packet), size)]
        texts = [gen_cascade_run.generate(src, as_of, p) for p in parts]
        if max(len(t.encode()) for t in texts) <= CAP * HEADROOM:
            break
        n += 1
        if n > 20:
            raise PartsError(f"{as_of}: cannot fit {len(packet)} rows under the cap")
    out = []
    for k, t in enumerate(texts, start=1):
        p = f"{out_prefix}{k}.js"
        Path(p).write_text(t)
        out.append(p)
    return out


def merge(as_of: str, results: list[dict], packet: list[dict]) -> dict:
    if not results:
        raise PartsError(f"{as_of}: no part returns")
    rules = {r["rule"] for r in results}
    if len(rules) != 1:
        raise PartsError(f"{as_of}: parts ran different rules {rules}")
    rows = [row for r in results for row in r["rows"]]
    slugs = [row["slug"] for row in rows]
    want = [row["slug"] for row in packet]
    if len(slugs) != len(set(slugs)) or sorted(slugs) != sorted(want):
        raise PartsError(f"{as_of}: merged rows {len(slugs)} differ from the packet's {len(want)}")
    counts = {}
    for r in results:
        for k, v in r["counts"].items():
            counts[k] = counts.get(k, 0) + v
    return {"asOf": as_of, "rule": rules.pop(), "counts": counts,
            "keeps": [k for r in results for k in r["keeps"]], "rows": rows,
            "parts": len(results)}


def _result(path: str) -> dict:
    o = json.loads(Path(path).read_text())
    return o if "keeps" in o else o["result"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("split", "merge"))
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--out-prefix", required=True)
    ap.add_argument("--dest")
    a = ap.parse_args(argv)
    packet = json.loads((_ROOT / "data" / f"triage-packet-{a.as_of}.json").read_text())
    if a.cmd == "split":
        src = (_ROOT / "scripts" / "cascade_workflow.js").read_text()
        paths = split(a.as_of, packet, src, a.out_prefix)
        print(f"{a.as_of}: {len(packet)} rows in {len(paths)} parts")
        return 0
    files = sorted(glob.glob(f"{a.out_prefix}*.json"), key=lambda p: int(re.search(r"-p(\d+)\.json$", p).group(1)))
    res = merge(a.as_of, [_result(f) for f in files], packet)
    Path(a.dest).write_text(json.dumps(res))
    print(f"{a.as_of}: merged {res['parts']} parts, {res['counts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
