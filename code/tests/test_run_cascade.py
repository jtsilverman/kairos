"""prompt-tuning unit 3: the cascade orchestrator.

Stage 2 ran by hand from a session on 2026-08-17 and left no orchestrator, so
rewinding it across ten cohorts had nothing to call. These tests pin the
contract of `scripts/run_cascade.py`: every path derives from the as-of date,
nothing is hardcoded to `/tmp` or to a single date, and the mechanical stages
run in an order where each one's output is the next one's input.

The three triage passes and the adjudicator are NOT here. Agent fan-outs
launch through the Workflow tool from inside a session, never from a shell
CLI, so `scripts/cascade_workflow.js` owns them. This module covers the half
a CLI can own.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import run_cascade  # noqa: E402


AS_OF = "2025-11-03"


def test_every_path_derives_from_the_as_of_date(tmp_path):
    p = run_cascade.cascade_paths(AS_OF, root=tmp_path)

    for name, path in vars(p).items():
        if not isinstance(path, Path):
            continue
        assert tmp_path in path.parents or path == tmp_path, (
            f"{name} escaped the run root: {path}"
        )
        assert "/tmp/" not in str(path), f"{name} still points at /tmp"

    # The date has to appear, or two cohorts overwrite each other.
    assert AS_OF in p.factsheets.name
    assert AS_OF in p.anon_dir.name
    assert AS_OF in p.priors_dir.name


def test_two_cohorts_never_share_an_output_path(tmp_path):
    a = run_cascade.cascade_paths("2025-11-03", root=tmp_path)
    b = run_cascade.cascade_paths("2025-12-01", root=tmp_path)

    # `root` is deliberately shared; every artefact under it must not be.
    a_paths = {v for k, v in vars(a).items() if isinstance(v, Path) and k != "root"}
    b_paths = {v for k, v in vars(b).items() if isinstance(v, Path) and k != "root"}

    assert not (a_paths & b_paths), "two cohorts collide on an output path"


def test_no_script_in_the_cascade_hardcodes_a_date_or_tmp():
    """`write_priors.py` hardcoded 2026-08-17; `ruleout_screen.py` hardcoded
    `/tmp/ruleout_all.json`. Either one silently rewrites another cohort's
    artefacts on the second run."""
    import ast

    def code_strings(source: str):
        """String literals the program USES. Docstrings and comments are
        prose: a usage line naming a date is documentation, not a hardcode."""
        tree = ast.parse(source)
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc is not None:
                    docstrings.add(doc)
        return [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and n.value not in docstrings]

    offenders = []
    for name in ("ruleout_screen.py", "compile_factsheets.py",
                 "split_factsheets.py", "anonymize_factsheets.py",
                 "write_priors.py", "run_cascade.py"):
        for literal in code_strings((_SCRIPTS / name).read_text()):
            if "/tmp/" in literal:
                offenders.append(f"{name}: hardcoded /tmp path {literal!r}")
            if "2026-08-17" in literal:
                offenders.append(f"{name}: hardcoded as-of date in {literal!r}")
    assert offenders == [], offenders


def test_the_mechanical_stages_run_in_dependency_order(tmp_path, monkeypatch):
    """Each stage consumes the previous stage's output, so a reordering that
    still 'succeeds' would silently read a stale artefact from a prior run."""
    calls: list[str] = []

    def _stage(name):
        def run(*_a, **_k):
            calls.append(name)
            return {}
        return run

    for stage in ("screen", "compile_factsheets", "split_factsheets",
                  "anonymize_factsheets"):
        monkeypatch.setattr(run_cascade, f"stage_{stage}", _stage(stage))

    run_cascade.run_mechanical(AS_OF, root=tmp_path)

    assert calls == ["screen", "compile_factsheets", "split_factsheets",
                     "anonymize_factsheets"]


def test_the_triage_packet_names_every_anonymized_slug(tmp_path):
    """The workflow fans out over this packet. A slug missing from it is a
    name the panel silently never sees."""
    anon = tmp_path / f"factsheets-anon-{AS_OF}"
    anon.mkdir(parents=True)
    for slug in ("N001", "N002", "N003"):
        (anon / f"{slug}.txt").write_text(f"TICKER {slug}\nrevenue 100\n")

    packet = run_cascade.triage_packet(AS_OF, root=tmp_path)

    assert [row["slug"] for row in packet] == ["N001", "N002", "N003"]
    assert all("TICKER" in row["sheet"] for row in packet)
    assert all("ticker" not in row for row in packet), (
        "the packet must carry the slug only; a real ticker defeats the "
        "anonymization the sheets were built for"
    )


def test_an_empty_anon_dir_raises_rather_than_returning_nothing(tmp_path):
    """A silent empty packet reads downstream as 'the panel rejected all of
    them' rather than 'the cascade never ran'."""
    (tmp_path / f"factsheets-anon-{AS_OF}").mkdir(parents=True)

    with pytest.raises(run_cascade.EmptyCascadeError):
        run_cascade.triage_packet(AS_OF, root=tmp_path)


def test_the_adjudicator_is_pinned_to_the_january_cutoff_model():
    """The adjudicator reads a fact sheet dated to the as-of day. The bare
    `opus` alias follows the session's model and would put a May 2026 cutoff
    on a seat screening a February 2026 cohort."""
    js = (Path(__file__).resolve().parents[2] / "scripts"
          / "cascade_workflow.js").read_text()

    assert "const OPUS = 'claude-opus-4-8'" in js
    assert "model: OPUS," in js


# ---- conviction-buckets unit 2: the adjudicate stage ------------------

def _write_screen_and_map(root: Path, as_of: str, survivors: list[dict],
                          mapping: dict[str, str]) -> None:
    paths = run_cascade.cascade_paths(as_of, root=root)
    root.mkdir(parents=True, exist_ok=True)
    paths.screen.write_text(json.dumps({as_of: {
        "survivors": survivors,
        "stages": {"top_third": 100, "screened": len(survivors),
                   "survivors": len(survivors)},
        "cuts": {},
    }}))
    paths.anon_map.write_text(json.dumps(mapping))


SURVIVORS = [{"ticker": "AAA", "rs": 90.0, "forensics": {}},
             {"ticker": "BBB", "rs": 80.0, "forensics": {}},
             {"ticker": "CCC", "rs": 70.0, "forensics": {}}]
MAP = {"N001": "AAA", "N002": "BBB", "N003": "CCC"}


def test_the_keep_slugs_come_back_as_tickers(tmp_path):
    """The workflow returns slugs, because the seats never saw a ticker.
    Everything downstream fetches closes and filings by ticker."""
    _write_screen_and_map(tmp_path, AS_OF, SURVIVORS, MAP)

    out = run_cascade.record_verdicts(AS_OF, ["N001", "N003"], root=tmp_path)

    assert out["keep"] == ["AAA", "CCC"]
    assert out["cut"] == ["BBB"]


def test_an_unmapped_keep_slug_raises_rather_than_shrinking_the_cohort(tmp_path):
    """A slug with no ticker behind it would be dropped, and the cohort would
    come out one name short with nothing saying why."""
    _write_screen_and_map(tmp_path, AS_OF, SURVIVORS, MAP)

    with pytest.raises(run_cascade.UnmappedSlugError) as e:
        run_cascade.record_verdicts(AS_OF, ["N001", "N999"], root=tmp_path)

    assert "N999" in str(e.value)


def test_an_empty_keep_list_raises(tmp_path):
    """Zero keeps reads downstream as `the seats rejected every name` when it
    is far more often `the workflow result was never wired in`."""
    _write_screen_and_map(tmp_path, AS_OF, SURVIVORS, MAP)

    with pytest.raises(run_cascade.EmptyCascadeError):
        run_cascade.record_verdicts(AS_OF, [], root=tmp_path)


def test_the_cohort_screen_holds_the_keeps_only(tmp_path):
    """`thesis_dossiers.py --rewind` compiles every survivor in the screen it
    is handed. Handing it the pre-cascade screen compiles the names the
    cascade ruled out."""
    _write_screen_and_map(tmp_path, AS_OF, SURVIVORS, MAP)

    run_cascade.record_verdicts(AS_OF, ["N001", "N003"], root=tmp_path)

    screen = json.loads(
        run_cascade.cascade_paths(AS_OF, root=tmp_path).cohort_screen.read_text())
    assert [s["ticker"] for s in screen["survivors"]] == ["AAA", "CCC"]
    assert screen["as_of"] == AS_OF


def test_the_cohort_screen_keeps_rs_so_the_draw_can_stratify(tmp_path):
    """`draw_cohorts.py` strata on rs. A survivor that loses rs still draws,
    silently unstratified."""
    _write_screen_and_map(tmp_path, AS_OF, SURVIVORS, MAP)

    run_cascade.record_verdicts(AS_OF, ["N001", "N002"], root=tmp_path)

    screen = json.loads(
        run_cascade.cascade_paths(AS_OF, root=tmp_path).cohort_screen.read_text())
    assert [s["rs"] for s in screen["survivors"]] == [90.0, 80.0]


def test_the_stage_counts_record_what_the_cascade_removed(tmp_path):
    """The funnel's own record. Without it nothing on disk says how many
    names the agent cascade cut."""
    _write_screen_and_map(tmp_path, AS_OF, SURVIVORS, MAP)

    out = run_cascade.record_verdicts(AS_OF, ["N001"], root=tmp_path)

    assert out["stages"]["screen_survivors"] == 3
    assert out["stages"]["cascade_keeps"] == 1
