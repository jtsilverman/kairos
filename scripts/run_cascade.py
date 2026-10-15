"""prompt-tuning unit 3: the cascade orchestrator, one as-of date at a time.

Stage 2 ran by hand from a session on 2026-08-17 and left nothing to call, so
rewinding it across ten cohorts had no entry point. This owns the half a CLI
can own: screen, fact sheets, split, anonymize, and the adjudication write.

The three triage passes and the adjudicator are NOT here. Agent fan-outs
launch through the Workflow tool from inside a session, never from a shell
CLI, so `scripts/cascade_workflow.js` owns them. This module hands that
workflow a triage packet and consumes its verdicts.

Every path derives from the as-of date. `ruleout_screen.py` wrote a hardcoded
`/tmp/ruleout_all.json` and `write_priors.py` hardcoded `2026-08-17`; either
one silently rewrites another cohort's artefacts on the second run, which is
exactly the failure a ten-cohort rewind would hit and not notice.

CLI:
    run_cascade.py <as-of> [--root data] [--stage mechanical|packet|adjudicate]
    run_cascade.py <as-of> --stage adjudicate --keeps <keeps.json>
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT / "code" / "src"))
sys.path.insert(0, str(_HERE))

DEFAULT_ROOT = _ROOT / "data"


class UnmappedSlugError(RuntimeError):
    """A keep slug with no ticker behind it.

    Dropping it would shrink the cohort by one name with nothing on disk
    saying why, which is the failure the whole fail-loud discipline exists
    for.
    """


class EmptyCascadeError(RuntimeError):
    """No anonymized sheets for this as-of date.

    An empty packet returned quietly reads downstream as "the panel rejected
    every name" rather than "the cascade never ran". Fail loud instead.
    """


@dataclasses.dataclass(frozen=True)
class CascadePaths:
    """Every artefact one cohort writes. Two cohorts share none of them."""

    as_of: str
    root: Path
    screen: Path          # the rule-out screen's survivors, stage-1 applied
    factsheets: Path      # {ticker: {sheet, mcap_b, sic, rs}}
    sheets_dir: Path      # one .txt per ticker
    anon_dir: Path        # one .txt per anonymized slug
    anon_map: Path        # slug -> ticker
    packet: Path          # what the triage workflow fans out over
    votes: Path           # the three triage passes' verdicts
    priors_dir: Path      # one .txt per split name, for the adjudicator
    verdicts: Path        # the settled keep/cut list
    cohort_screen: Path   # the screen JSON the cohort draw consumes


def cascade_paths(as_of: str, *, root: Path | str = DEFAULT_ROOT) -> CascadePaths:
    root = Path(root)
    return CascadePaths(
        as_of=as_of,
        root=root,
        screen=root / f"ruleout-{as_of}.json",
        factsheets=root / f"factsheets-{as_of}.json",
        sheets_dir=root / f"factsheets-{as_of}",
        anon_dir=root / f"factsheets-anon-{as_of}",
        anon_map=root / f"factsheets-anon-{as_of}-map.json",
        packet=root / f"triage-packet-{as_of}.json",
        votes=root / f"triage-votes-{as_of}.json",
        priors_dir=root / f"priors-{as_of}",
        verdicts=root / f"stage2-{as_of}.json",
        cohort_screen=root / "screen" / "rewind" / f"{as_of}.json",
    )


def _run(script: str, *args: str) -> None:
    """Each stage stays its own process: they were written as scripts, they
    are the record of how the 2026-08-17 funnel was produced, and rewriting
    them into importable functions would change the thing being reproduced."""
    cmd = [sys.executable, str(_HERE / script), *args]
    subprocess.run(cmd, check=True, cwd=_ROOT)


def stage_screen(as_of: str, paths: CascadePaths) -> None:
    _run("ruleout_screen.py", as_of, "--out", str(paths.screen))


def stage_compile_factsheets(as_of: str, paths: CascadePaths) -> None:
    _run("compile_factsheets.py", as_of, str(paths.screen))


def stage_split_factsheets(as_of: str, paths: CascadePaths) -> None:
    _run("split_factsheets.py", as_of)


def stage_anonymize_factsheets(as_of: str, paths: CascadePaths) -> None:
    _run("anonymize_factsheets.py", as_of)


#: Order matters: each stage's output is the next stage's input. A reordering
#: that still "succeeds" reads a stale artefact from a previous run.
MECHANICAL_STAGES = (
    stage_screen,
    stage_compile_factsheets,
    stage_split_factsheets,
    stage_anonymize_factsheets,
)


def run_mechanical(as_of: str, *, root: Path | str = DEFAULT_ROOT) -> CascadePaths:
    paths = cascade_paths(as_of, root=root)
    paths.root.mkdir(parents=True, exist_ok=True)
    for stage in MECHANICAL_STAGES:
        # Resolved by name so a test can substitute one stage; a captured
        # function reference would ignore the substitution.
        globals()[stage.__name__](as_of, paths)
    return paths


def triage_packet(as_of: str, *, root: Path | str = DEFAULT_ROOT) -> list[dict]:
    """What `cascade_workflow.js` fans out over: one row per anonymized slug.

    The row carries the slug and the sheet, never the ticker. A packet that
    leaked the real ticker would defeat the anonymization the sheets exist
    for, and the seat would be reading its memory of the company again.
    """
    paths = cascade_paths(as_of, root=root)
    rows = [
        {"slug": p.stem, "sheet": p.read_text()}
        for p in sorted(paths.anon_dir.glob("N*.txt"))
    ]
    if not rows:
        raise EmptyCascadeError(
            f"no anonymized sheets under {paths.anon_dir}; the cascade did not run"
        )
    paths.packet.write_text(json.dumps(rows, indent=1))
    return rows


def write_cohort_screen(as_of: str, *, root: Path | str = DEFAULT_ROOT) -> Path:
    """Reshape the funnel's own output into what `draw_cohorts.py` consumes.

    The funnel keys by date and carries its stage counts; the draw wants
    `{as_of, survivors:[{ticker, rs, ...}]}`. `rs` has to survive the trip:
    a survivor that loses it still draws, silently unstratified.
    """
    paths = cascade_paths(as_of, root=root)
    block = json.loads(paths.screen.read_text())[as_of]
    survivors = block["survivors"]
    missing = [s["ticker"] for s in survivors if s.get("rs") is None]
    if missing:
        raise ValueError(f"{as_of}: {len(missing)} survivors carry no rs: {missing[:5]}")

    paths.cohort_screen.parent.mkdir(parents=True, exist_ok=True)
    paths.cohort_screen.write_text(json.dumps({
        "as_of": as_of,
        "survivors": survivors,
        "stages": block["stages"],
        "exclusions": block.get("cuts", {}),
    }, indent=1))
    return paths.cohort_screen


def record_verdicts(as_of: str, keep_slugs: list[str], *,
                    root: Path | str = DEFAULT_ROOT) -> dict:
    """Turn the triage workflow's keep list into this cohort's screen.

    The workflow returns SLUGS, because the seats never saw a ticker.
    Everything downstream fetches closes and filings by ticker, so the slug
    map is the seam. The cohort screen is written filtered to the keeps:
    `thesis_dossiers.py --rewind` compiles every survivor in the screen it is
    handed, so handing it the pre-cascade screen compiles the names the
    cascade ruled out.
    """
    paths = cascade_paths(as_of, root=root)
    if not keep_slugs:
        raise EmptyCascadeError(
            f"{as_of}: no keep slugs; the workflow result was never wired in")

    mapping = json.loads(paths.anon_map.read_text())
    unmapped = [s for s in keep_slugs if s not in mapping]
    if unmapped:
        raise UnmappedSlugError(
            f"{as_of}: {len(unmapped)} keep slugs have no ticker: {unmapped[:5]}")

    kept = {mapping[s] for s in keep_slugs}
    block = json.loads(paths.screen.read_text())[as_of]
    survivors = block["survivors"]
    keep = [s["ticker"] for s in survivors if s["ticker"] in kept]
    cut = [s["ticker"] for s in survivors if s["ticker"] not in kept]

    out = {"as_of": as_of, "keep": keep, "cut": cut,
           "stages": {"screen_survivors": len(survivors),
                      "cascade_keeps": len(keep)}}
    paths.verdicts.write_text(json.dumps(out, indent=1))

    paths.cohort_screen.parent.mkdir(parents=True, exist_ok=True)
    paths.cohort_screen.write_text(json.dumps({
        "as_of": as_of,
        "survivors": [s for s in survivors if s["ticker"] in kept],
        "stages": {**block["stages"], "cascade_keeps": len(keep)},
        "exclusions": block.get("cuts", {}),
    }, indent=1))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("as_of", help="ISO date, the cohort's entry session")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--stage", default="mechanical",
                    choices=("mechanical", "packet", "adjudicate"))
    ap.add_argument("--keeps", type=Path,
                    help="adjudicate: JSON list of the workflow's keep slugs")
    args = ap.parse_args()

    if args.stage == "mechanical":
        paths = run_mechanical(args.as_of, root=args.root)
        rows = triage_packet(args.as_of, root=args.root)
        print(f"{args.as_of}: {len(rows)} anonymized sheets -> {paths.packet}")
        print("next: scripts/cascade_workflow.js over that packet "
              "(three triage passes + the adjudicator on the splits)")
    elif args.stage == "packet":
        rows = triage_packet(args.as_of, root=args.root)
        print(f"{args.as_of}: {len(rows)} rows")
    else:
        if not args.keeps:
            raise SystemExit("--keeps is required for --stage adjudicate")
        out = record_verdicts(args.as_of, json.loads(args.keeps.read_text()),
                              root=args.root)
        paths = cascade_paths(args.as_of, root=args.root)
        print(f"{args.as_of}: {out['stages']['screen_survivors']} survivors -> "
              f"{out['stages']['cascade_keeps']} keeps -> {paths.cohort_screen}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
