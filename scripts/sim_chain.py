#!/usr/bin/env python3
"""The mechanical joints of an unattended sim chain: split args, merge returns.

Every hand-off between fan-out stages used to be a session typing Python. The
two operations are always the same, so they live here, tested once:

    split  -- copy a parent args object into batch files of at most 8 names,
              optionally setting `layer`.
    merge  -- read every batch return (either saved shape), refuse a drop, a
              duplicate, a short batch or a name outside the args, and write
              one `{asOf, summary}` results file.
    rows   -- the sorter's returns, merged the same way into a `{rows}` file.

CLI:
    sim_chain.py split --args A.json --prefix data/scratch/x-b [--layer middle]
    sim_chain.py merge --args A.json --prefix data/scratch/x-b --out-prefix data/scratch/x-out-b --dest R.json
    sim_chain.py rows  --args A.json --out-prefix data/scratch/s-out-b --dest rows.json
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path

BATCH = 8


def _num(p: str) -> int:
    return int(re.search(r"-b(\d+)\.json$", p).group(1))


def split(args: dict, prefix: str, layer: str | None = None) -> int:
    names = args["names"]
    parent = dict(args, **({"layer": layer} if layer else {}))
    n = 0
    for i in range(0, len(names), BATCH):
        n += 1
        Path(f"{prefix}{n}.json").write_text(json.dumps(dict(parent, names=names[i:i + BATCH])))
    return n


def _result(path: str) -> dict:
    obj = json.loads(Path(path).read_text())
    return obj["result"] if isinstance(obj.get("summary"), str) or ("result" in obj and "summary" not in obj and "rows" not in obj) else obj


class ChainError(RuntimeError):
    pass


def merge(args: dict, prefix: str, out_prefix: str) -> dict:
    want = [n["ticker"] for n in args["names"]]
    batches = sorted(glob.glob(f"{prefix}*.json"), key=_num)
    recs = []
    for b in batches:
        o = f"{out_prefix}{_num(b)}.json"
        if not Path(o).exists():
            raise ChainError(f"no return for {b}")
        r = _result(o)
        if r.get("dropped"):
            raise ChainError(f"{o}: dropped {r['dropped']}; relaunch those names alone")
        n_args = len(json.loads(Path(b).read_text())["names"])
        if len(r["summary"]) != n_args:
            raise ChainError(f"{o}: {len(r['summary'])} records for {n_args} names")
        recs += r["summary"]
    got = [r["slug"] for r in recs]
    if len(got) != len(set(got)) or sorted(got) != sorted(want):
        raise ChainError(f"slugs differ from args: missing {sorted(set(want) - set(got))}, "
                         f"extra {sorted(set(got) - set(want))}, dup {len(got) - len(set(got))}")
    return {"asOf": args["asOf"], "summary": recs}


def rows(args: dict, out_prefix: str) -> dict:
    want = sorted(n["ticker"] for n in args["names"])
    out = []
    for o in sorted(glob.glob(f"{out_prefix}*.json"), key=_num):
        r = _result(o)
        if r.get("dropped"):
            raise ChainError(f"{o}: dropped {r['dropped']}")
        out += r.get("rows") or r.get("graded") or []
    got = sorted(r["ticker"] for r in out)
    if got != want:
        raise ChainError(f"sorter rows differ from args: missing {sorted(set(want) - set(got))}")
    return {"rows": out}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("split", "merge", "rows"))
    ap.add_argument("--args", required=True)
    ap.add_argument("--prefix")
    ap.add_argument("--out-prefix")
    ap.add_argument("--layer")
    ap.add_argument("--dest")
    a = ap.parse_args(argv)
    args = json.loads(Path(a.args).read_text())
    if a.cmd == "split":
        print(f"{split(args, a.prefix, a.layer)} batches")
    elif a.cmd == "merge":
        res = merge(args, a.prefix, a.out_prefix)
        Path(a.dest).write_text(json.dumps(res))
        print(f"{len(res['summary'])} records -> {a.dest}")
    else:
        res = rows(args, a.out_prefix)
        Path(a.dest).write_text(json.dumps(res))
        print(f"{len(res['rows'])} rows -> {a.dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
