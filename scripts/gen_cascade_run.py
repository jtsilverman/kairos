#!/usr/bin/env python3
"""Generate one cohort's runnable copy of `cascade_workflow.js`.

A workflow script has no filesystem access, so a triage packet can only reach
the seats two ways: through the Workflow tool's `args`, or inside the script's
own text. `args` passes through the driving session's context, and one cohort
of anonymized fact sheets is roughly 0.4 MB. Three cohorts read and re-emitted
is the same wall the inline dossier was.

So the packet is spliced into a per-cohort copy of the workflow, exactly as
`gen_embedded.py` splices agent bodies. Every splice rests on a NAMED exact
string anchor: a `cascade_workflow.js` edit that moves a splice point errors
by anchor name, never silently generates a script that fans out over an empty
packet and reports a cohort with zero keeps.

Usage:
    code/.venv/bin/python scripts/gen_cascade_run.py --as-of 2026-02-02 \\
        [--packet data/triage-packet-2026-02-02.json] --out <scratch>/run.js
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


class GenError(Exception):
    """Named anchor or packet failure; the message carries the name."""


#: name -> (anchor, replacement template). `{packet}` and `{as_of}` are filled
#: per cohort. The anchors are the two lines that read the runtime `args`.
_SPLICES = {
    "packet": ("const packet = args?.packet ?? []",
               "const packet = {packet}"),
    "as-of": ("const asOf = args?.asOf",
              "const asOf = {as_of}"),
    "meta-name": ("  name: 'cascade-triage',",
                  "  name: 'cascade-triage-{as_of_bare}',"),
}


def generate(src: str, as_of: str, packet: list[dict]) -> str:
    """Splice one cohort's packet into the workflow source.

    Refuses an empty packet and refuses a row carrying a ticker: the packet is
    the anonymized artefact, and the named A/B moved 24 verdicts, 23 of them
    yes to no.
    """
    if not packet:
        raise GenError(f"{as_of}: packet is empty; run run_cascade.py first")
    for row in packet:
        extra = set(row) - {"slug", "sheet"}
        if extra:
            raise GenError(
                f"{as_of}: packet row {row.get('slug')} carries {sorted(extra)}; "
                "the triage seat must see a slug and a sheet, never a ticker")

    for name, (anchor, template) in _SPLICES.items():
        if anchor not in src:
            raise GenError(f"anchor {name} not found in cascade_workflow.js; "
                           "the source drifted, update _SPLICES")
        src = src.replace(anchor, template.format(
            packet=json.dumps(packet), as_of=json.dumps(as_of),
            as_of_bare=as_of), 1)
    return src


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--packet", default=None,
                    help="defaults to data/triage-packet-<as-of>.json")
    ap.add_argument("--src", default=str(_ROOT / "scripts" / "cascade_workflow.js"))
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    packet_path = Path(args.packet or
                       _ROOT / "data" / f"triage-packet-{args.as_of}.json")
    try:
        packet = json.loads(packet_path.read_text())
        out_text = generate(Path(args.src).read_text(), args.as_of, packet)
    except GenError as e:
        print(f"gen_cascade_run FAILED: {e}", file=sys.stderr)
        return 2
    Path(args.out).write_text(out_text)
    print(f"{args.as_of}: {len(packet)} rows spliced -> {args.out} "
          f"({len(out_text)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
