"""thesis-exemplars unit 2: the blind sorter and the exemplar files.

One opus seat reads each REAL dossier with no outcome and grades the four
tests (docs/four-tests.md) plus the driver. Code then joins the blind grade
to the realized window and sorts the name into one of four classes. The
"thesis visible" rule is mechanical and lives here, never in a prompt, so a
model cannot lower the bar by being generous.

Fail-loud: a cohort name with no grade, a grade with no outcome, or a grade
for a ticker outside the cohort each raise. A silently shrunk cohort would
read as a cleaner panel than the one that ran.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import sort_exemplars as se  # noqa: E402

AS_OF = "2026-02-02"


def _tests(*grades):
    keys = ("business_case", "fundamentals", "demand_case", "positioned")
    return {k: {"grade": g, "evidence": "e " * 20, "cite": "Q1"} for k, g in zip(keys, grades)}


@pytest.mark.parametrize("grades,visible", [
    (("strong", "strong", "strong", "strong"), True),
    (("strong", "strong", "strong", "adequate"), False),  # one adequate is not strong
    (("adequate", "adequate", "adequate", "weak"), False),
    (("strong", "strong", "strong", "absent"), False),
])
def test_thesis_visible_is_strong_on_all_four(grades, visible):
    """Amended 2026-09-11: three-of-four-adequate passed 98 of 100 names."""
    assert se.visible(_tests(*grades)) is visible


def test_visible_rejects_an_unknown_grade():
    with pytest.raises(se.BadGradeError):
        se.visible(_tests("strong", "strong", "strong", "great"))


@pytest.mark.parametrize("vis,beat,cls", [
    (True, True, "EXEMPLAR"),
    (True, False, "THESIS_NOT_FOLLOWED"),
    (False, True, "LUCK"),
    (False, False, "NOTHING"),
])
def test_the_class_table(vis, beat, cls):
    assert se.classify(vis, beat) == cls


def _root(tmp_path, tickers=("AAA", "BBB"), dossiers=None):
    root = tmp_path
    d = root / "dossiers" / f"rewind-{AS_OF}"
    d.mkdir(parents=True)
    rows = []
    for t in (dossiers or tickers):
        (d / f"{t}.md").write_text("# x\n" + "[P1] price\n" * 300)
        rows.append({"ticker": t, "as_of": AS_OF, "dossierPath": str(d / f"{t}.md"),
                     "doc_ids": ["P1", "Q1"], "sha256": "0"})
    (d / "manifest.json").write_text(json.dumps(rows))
    outcomes = {t: {"alpha": 0.1 if t == "AAA" else -0.1, "beat": t == "AAA",
                    "ticker_return": 0.1, "spy_return": 0.0,
                    "entry_date": "2026-02-03", "exit_date": "2026-05-04"} for t in tickers}
    (root / f"outcomes-{AS_OF}.json").write_text(json.dumps(outcomes))
    return root


def test_prepare_marshals_the_cohort_by_path_with_no_outcome(tmp_path):
    root = _root(tmp_path, dossiers=("AAA", "BBB", "CCC"))  # CCC compiled, not drawn
    args = se.sorter_args(AS_OF, root=root)
    assert [n["ticker"] for n in args["names"]] == ["AAA", "BBB"]
    assert args["root"] == str(root.resolve()) and args["asOf"] == AS_OF
    for n in args["names"]:
        assert n["docIds"] == "P1 Q1"
        assert "alpha" not in n and "beat" not in n and "dossierPath" not in n


def test_prepare_fails_loud_on_a_drawn_name_with_no_dossier(tmp_path):
    root = _root(tmp_path, tickers=("AAA", "BBB", "ZZZ"), dossiers=("AAA", "BBB"))
    with pytest.raises(se.MissingDossierError):
        se.sorter_args(AS_OF, root=root)


def _grade(t, *grades):
    return {"ticker": t, "as_of": AS_OF, "tests": _tests(*grades),
            "driver": "d " * 25, "summary": "s " * 25}


def test_record_joins_blind_grades_to_outcomes(tmp_path):
    root = _root(tmp_path)
    rows = [_grade("AAA", "strong", "strong", "strong", "strong"),
            _grade("BBB", "weak", "absent", "weak", "weak")]
    out = se.record(AS_OF, rows, root=root)
    by = {r["ticker"]: r for r in out["rows"]}
    assert by["AAA"]["class"] == "EXEMPLAR" and by["AAA"]["visible"] is True
    assert by["BBB"]["class"] == "NOTHING" and by["BBB"]["visible"] is False
    assert by["AAA"]["signed"] is False
    assert out["counts"] == {"EXEMPLAR": 1, "THESIS_NOT_FOLLOWED": 0, "LUCK": 0, "NOTHING": 1}
    on_disk = json.loads((root / f"exemplars-{AS_OF}.json").read_text())
    assert on_disk["counts"] == out["counts"]


def test_record_fails_loud_on_a_missing_grade(tmp_path):
    root = _root(tmp_path)
    with pytest.raises(se.MissingGradeError):
        se.record(AS_OF, [_grade("AAA", "strong", "strong", "strong", "strong")], root=root)


def test_record_fails_loud_on_a_grade_outside_the_cohort(tmp_path):
    root = _root(tmp_path)
    rows = [_grade("AAA", "strong", "strong", "strong", "strong"),
            _grade("BBB", "weak", "weak", "weak", "weak"),
            _grade("QQQ", "weak", "weak", "weak", "weak")]
    with pytest.raises(se.UnknownTickerError):
        se.record(AS_OF, rows, root=root)


def test_record_keeps_a_signature_already_given(tmp_path):
    root = _root(tmp_path)
    rows = [_grade("AAA", "strong", "strong", "strong", "strong"),
            _grade("BBB", "weak", "weak", "weak", "weak")]
    se.record(AS_OF, rows, root=root)
    p = root / f"exemplars-{AS_OF}.json"
    d = json.loads(p.read_text())
    d["rows"][0]["signed"] = True
    p.write_text(json.dumps(d))
    out = se.record(AS_OF, rows, root=root)
    assert {r["ticker"]: r["signed"] for r in out["rows"]}["AAA"] is True
