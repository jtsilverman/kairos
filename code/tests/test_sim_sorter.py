"""thesis-exemplars: the sim's blind sorter for names outside the tuning cohort.

Roughly a third of each sim date's layer-1 survivors were never graded, so
keep rates computed over the graded subset describe two thirds of the run
while reading as if they described all of it. This module grades the rest.

What the tests pin down:

- it never writes `exemplars-<as_of>.json`, the reference set of record;
- it records no class and no outcome, because these names have no realized
  window and a class is quality crossed with what the price did;
- `record` MERGES, because the fan-out arrives in batches;
- a name already graded in either file is not re-read.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
_SPEC = importlib.util.spec_from_file_location("sim_sorter", _SCRIPTS / "sim_sorter.py")
ss = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ss)

AS_OF = "2026-05-01"
TESTS = ("business_case", "fundamentals", "demand_case", "positioned")


def _sorter_row(ticker: str, *grades: str) -> dict:
    words = grades or ("strong",) * 4
    return {"ticker": ticker, "as_of": AS_OF,
            "tests": {k: {"grade": g, "evidence": "e", "cite": "Q1"}
                      for k, g in zip(TESTS, words)},
            "driver": "the driver", "summary": "the summary"}


def _root(tmp_path, sim=("AAA", "BBB", "CCC"), cohort=("AAA",)):
    d = tmp_path / "dossiers" / f"rewind-{AS_OF}"
    d.mkdir(parents=True)
    rows = []
    for t in sim:
        (d / f"{t}.md").write_text(f"# {t}")
        rows.append({"ticker": t, "as_of": AS_OF, "doc_ids": ["P1", "Q1"],
                     "sha256": "0" * 64, "dossierPath": str(d / f"{t}.md")})
    (d / "manifest.json").write_text(json.dumps(rows))
    (tmp_path / f"panel-args-real-sim-{AS_OF}.json").write_text(json.dumps(
        {"asOf": AS_OF, "root": str(tmp_path),
         "names": [{"ticker": t, "docIds": "P1 Q1"} for t in sim]}))
    # the tuning cohort: graded already, with a realized window
    (tmp_path / f"exemplars-{AS_OF}.json").write_text(json.dumps(
        {"as_of": AS_OF, "rows": [
            {"ticker": t, "as_of": AS_OF, "class": "EXEMPLAR", "beat": True,
             "alpha": 0.25, "grades": dict.fromkeys(TESTS, "strong")} for t in cohort]}))
    return tmp_path


def test_only_the_ungraded_names_are_prepared(tmp_path):
    root = _root(tmp_path)
    assert ss.ungraded(AS_OF, root=root) == ["BBB", "CCC"]
    args = ss.sorter_args(AS_OF, root=root)
    assert [n["ticker"] for n in args["names"]] == ["BBB", "CCC"]


def test_the_args_carry_no_outcome_field(tmp_path):
    """The sorter is blind; an alpha or beat field in its args would leak.

    Asserted over the args' own keys, not a substring of the JSON: `root` is an
    absolute path, and a tmp dir named after the test made a substring scan for
    "outcome" match the path rather than any field.
    """
    root = _root(tmp_path)
    args = ss.sorter_args(AS_OF, root=root)
    assert set(args) == {"asOf", "root", "names"}
    for n in args["names"]:
        assert set(n) == {"ticker", "docIds"}


def test_a_sim_name_with_no_dossier_fails_loud(tmp_path):
    root = _root(tmp_path)
    (root / "dossiers" / f"rewind-{AS_OF}" / "BBB.md").unlink()
    with pytest.raises(ss.sort_exemplars.MissingDossierError):
        ss.sorter_args(AS_OF, root=root)


def test_nothing_to_grade_fails_loud_rather_than_writing_an_empty_fan_out(tmp_path):
    root = _root(tmp_path, sim=("AAA",), cohort=("AAA",))
    with pytest.raises(ss.NothingUngradedError):
        ss.sorter_args(AS_OF, root=root)


def test_record_writes_grades_with_no_class_and_no_outcome(tmp_path):
    root = _root(tmp_path)
    out = ss.record(AS_OF, [_sorter_row("BBB", "strong", "adequate", "weak", "adequate")],
                    root=root)
    assert out["n"] == 1
    row = out["rows"][0]
    assert row["grades"] == {"business_case": "strong", "fundamentals": "adequate",
                             "demand_case": "weak", "positioned": "adequate"}
    assert "class" not in row and "beat" not in row and "alpha" not in row


def test_record_merges_across_batches(tmp_path):
    root = _root(tmp_path)
    ss.record(AS_OF, [_sorter_row("BBB")], root=root)
    out = ss.record(AS_OF, [_sorter_row("CCC")], root=root)
    assert [r["ticker"] for r in out["rows"]] == ["BBB", "CCC"]


def test_record_never_touches_the_reference_set(tmp_path):
    root = _root(tmp_path)
    ref = root / f"exemplars-{AS_OF}.json"
    before = ref.read_text()
    ss.record(AS_OF, [_sorter_row("BBB")], root=root)
    assert ref.read_text() == before


def test_a_grade_for_a_name_outside_the_sim_fails_loud(tmp_path):
    root = _root(tmp_path)
    with pytest.raises(ss.sort_exemplars.UnknownTickerError):
        ss.record(AS_OF, [_sorter_row("ZZZ")], root=root)


def test_a_name_graded_in_the_sim_file_is_not_prepared_again(tmp_path):
    root = _root(tmp_path)
    ss.record(AS_OF, [_sorter_row("BBB")], root=root)
    assert ss.ungraded(AS_OF, root=root) == ["CCC"]


def test_the_two_files_together_cover_every_sim_name(tmp_path):
    root = _root(tmp_path)
    ss.record(AS_OF, [_sorter_row("BBB"), _sorter_row("CCC")], root=root)
    assert ss.ungraded(AS_OF, root=root) == []
