"""thesis-exemplars unit 8, vision milestone 3: real-name funnel args.

`run_panel.py` scrubs every dossier and hands the panel a `CO-nnn` slug;
this spec reads real names, as production will. `panel_prepare.py` writes
the compact args `{asOf, root, names: [{ticker, docIds}]}` from the cohort
draw and the rewind manifest. Every seat reads the full dossier by path, so
no view file is written; the v18 views went with the v18 seats.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import panel_prepare as pp  # noqa: E402

AS_OF = "2026-02-02"
DOSSIER = """\
# AAA as of 2026-02-02

[P1] price frame
close 10
[Q1] financial history
rev 1 2 3
[X1] forensic ratios
ar 0.1
[F1] filing one
text
[E1] earnings timing
next print
[N1] news one
headline
[S1] short interest
3%
[I1] insiders
buy
[R1] revisions
up
"""


def _root(tmp_path, tickers=("AAA", "BBB")):
    d = tmp_path / "dossiers" / f"rewind-{AS_OF}"
    d.mkdir(parents=True)
    rows = []
    for t in tickers:
        (d / f"{t}.md").write_text(DOSSIER.replace("AAA", t))
        rows.append({"ticker": t, "as_of": AS_OF, "dossierPath": str(d / f"{t}.md"),
                     "doc_ids": ["P1", "Q1", "X1", "F1", "E1", "N1", "S1", "I1", "R1"],
                     "sha256": "0"})
    (d / "manifest.json").write_text(json.dumps(rows))
    (tmp_path / f"outcomes-{AS_OF}.json").write_text(json.dumps(
        {t: {"alpha": 0.0, "beat": False} for t in tickers}))
    return tmp_path


def test_args_carry_every_drawn_name_with_its_doc_ids_and_no_views(tmp_path):
    root = _root(tmp_path)
    args = pp.prepare(AS_OF, root=root)
    assert args["asOf"] == AS_OF and args["root"] == str(root.resolve())
    assert [n["ticker"] for n in args["names"]] == ["AAA", "BBB"]
    assert args["names"][0]["docIds"] == "P1 Q1 X1 F1 E1 N1 S1 I1 R1"
    assert "CO-" not in json.dumps(args) and "anon" not in json.dumps(args)
    assert not (root / "dossiers" / f"views-{AS_OF}").exists(), "no view files"
    assert not (_SCRIPTS / "dossier_views.py").exists(), "the view writer is gone"


def test_a_drawn_name_with_no_dossier_fails_loud(tmp_path):
    root = _root(tmp_path)
    o = root / f"outcomes-{AS_OF}.json"
    d = json.loads(o.read_text()); d["ZZZ"] = {"alpha": 0.0, "beat": False}
    o.write_text(json.dumps(d))
    with pytest.raises(pp.MissingDossierError):
        pp.prepare(AS_OF, root=root)


def test_a_sample_restricts_the_args_to_the_named_lists_at_that_date(tmp_path):
    """vision milestone 3: layer 1 runs on GOOD plus EDGE, layer 2 on GOOD plus BAD."""
    root = _root(tmp_path, tickers=("AAA", "BBB", "CCC"))
    sample = tmp_path / "contrast-sample.json"
    row = lambda t, d: {"ticker": t, "as_of": d, "cls": "EXEMPLAR", "alpha": 0.5, "grades": "3333"}
    sample.write_text(json.dumps({
        "good": [row("AAA", AS_OF), row("ZZZ", "2026-03-16")],
        "edge": [row("BBB", AS_OF)],
        "bad": [row("CCC", AS_OF)],
    }))
    args = pp.prepare(AS_OF, root=root, sample=sample, lists=("good", "edge"))
    assert [n["ticker"] for n in args["names"]] == ["AAA", "BBB"]
    for leak in ("cls", "alpha", "grades", "EXEMPLAR"):
        assert leak not in json.dumps(args)
    args = pp.prepare(AS_OF, root=root, sample=sample, lists=("good", "bad"))
    assert [n["ticker"] for n in args["names"]] == ["AAA", "CCC"]


def test_a_sample_name_outside_the_cohort_fails_loud(tmp_path):
    root = _root(tmp_path)
    sample = tmp_path / "contrast-sample.json"
    sample.write_text(json.dumps({"good": [{"ticker": "QQQ", "as_of": AS_OF}]}))
    with pytest.raises(pp.UnknownSampleNameError):
        pp.prepare(AS_OF, root=root, sample=sample, lists=("good",))


def test_the_sim_runs_every_layer_1_survivor_not_just_the_graded_cohort(tmp_path):
    """The full sim's names come from layer 1, not from `outcomes-<as_of>.json`.

    Outcomes hold only the ~100 names that were drawn and graded per date, so
    gating the sim on them would silently drop 176 of 458 survivors — the
    funnel would look like it ran while most of the field never entered.
    """
    root = _root(tmp_path, tickers=("AAA", "BBB", "CCC"))
    # the graded cohort is a strict subset: only AAA was ever drawn
    (root / f"outcomes-{AS_OF}.json").write_text(json.dumps({"AAA": {"alpha": 0.0, "beat": False}}))
    names_from = tmp_path / "survivors.json"
    names_from.write_text(json.dumps(["AAA", "BBB", "CCC"]))
    args = pp.prepare(AS_OF, root=root, names_from=names_from)
    assert [n["ticker"] for n in args["names"]] == ["AAA", "BBB", "CCC"]


def test_a_survivor_with_no_dossier_still_fails_loud(tmp_path):
    root = _root(tmp_path)
    names_from = tmp_path / "survivors.json"
    names_from.write_text(json.dumps(["AAA", "ZZZ"]))
    with pytest.raises(pp.MissingDossierError):
        pp.prepare(AS_OF, root=root, names_from=names_from)


def test_the_sim_needs_no_outcomes_file_at_all(tmp_path):
    root = _root(tmp_path)
    (root / f"outcomes-{AS_OF}.json").unlink()
    names_from = tmp_path / "survivors.json"
    names_from.write_text(json.dumps(["AAA", "BBB"]))
    args = pp.prepare(AS_OF, root=root, names_from=names_from)
    assert len(args["names"]) == 2


def test_a_live_date_reads_the_live_compile_and_names_it_in_the_args(tmp_path):
    # live dossiers compile to dossiers/<as_of>/; the workflow derives its path from dossierDir
    d = "2026-10-07"
    ddir = tmp_path / "dossiers" / d
    ddir.mkdir(parents=True)
    (ddir / "AAA.md").write_text("x")
    (ddir / "manifest.json").write_text(json.dumps([{"ticker": "AAA", "doc_ids": ["P1", "Q1"]}]))
    names = tmp_path / "n.json"
    names.write_text(json.dumps(["AAA"]))
    args = pp.prepare(d, root=tmp_path, names_from=names, live=True)
    assert args["dossierDir"] == d and args["names"] == [{"ticker": "AAA", "docIds": "P1 Q1"}]
    with pytest.raises(FileNotFoundError):
        pp.prepare(d, root=tmp_path, names_from=names)   # the rewind default does not see it
