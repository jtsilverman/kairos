"""thesis-exemplars: the sim's layer-2 scorer.

The tier formula this replaces called a dossier BAD on "two or fewer strong
grades", which labelled 16 clean two-strong/two-adequate May dossiers weak and
produced the false reading that layer 2 lets weak dossiers through. Only 2 of
those 18 names carried any weak-or-absent grade, and the ruler caught both.
So the quality scale is asserted on the worst grade present, and a clean
all-adequate dossier must never grade weak.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "score_sim_layer2",
    Path(__file__).resolve().parents[2] / "scripts" / "score_sim_layer2.py")
ssl = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ssl)

AS_OF = "2026-05-01"
TESTS = ("business_case", "fundamentals", "demand_case", "positioned")


def _grades(*words: str) -> dict[str, str]:
    return dict(zip(TESTS, words))


# --- the quality scale -------------------------------------------------------

def test_an_all_adequate_dossier_is_clean_not_weak():
    """The bug this module exists to prevent: sound but unspectacular is not weak."""
    assert ssl.dossier_quality(_grades("adequate", "adequate", "adequate", "adequate")) == "clean"


def test_two_strong_two_adequate_is_clean():
    assert ssl.dossier_quality(_grades("strong", "strong", "adequate", "adequate")) == "clean"


def test_one_weak_test_is_holed():
    assert ssl.dossier_quality(_grades("strong", "strong", "weak", "adequate")) == "holed"


def test_one_absent_test_is_holed():
    assert ssl.dossier_quality(_grades("strong", "strong", "absent", "adequate")) == "holed"


def test_two_holes_is_weak():
    assert ssl.dossier_quality(_grades("strong", "weak", "weak", "adequate")) == "weak"


def test_a_weak_and_an_absent_is_weak():
    assert ssl.dossier_quality(_grades("strong", "strong", "weak", "absent")) == "weak"


def test_all_strong_is_clean():
    assert ssl.dossier_quality(_grades("strong", "strong", "strong", "strong")) == "clean"


def test_no_grades_fails_loud():
    with pytest.raises(ssl.NoGradesError):
        ssl.dossier_quality({})


def test_an_unknown_grade_fails_loud():
    with pytest.raises(ssl.NoGradesError):
        ssl.dossier_quality(_grades("strong", "strong", "excellent", "adequate"))


# --- bear wins ---------------------------------------------------------------

def test_bear_wins_counts_only_outright_bear_tests():
    assert ssl.bear_wins({"a": "bear", "b": "gap", "c": "bull", "d": "bear"}) == 2


def test_a_gap_is_not_a_bear_win():
    """`gap` is a bull winner whose own evidence is holed, never a bear win."""
    assert ssl.bear_wins({"a": "gap", "b": "gap", "c": "gap", "d": "gap"}) == 0


# --- the scorer over a run ---------------------------------------------------

def _root(tmp_path, names):
    """names: {ticker: (grades, rulings, ruler_pass, alpha, beat)}"""
    (tmp_path / f"exemplars-{AS_OF}.json").write_text(json.dumps(
        {"rows": [{"ticker": t, "as_of": AS_OF, "grades": v[0]} for t, v in names.items()]}))
    (tmp_path / f"outcomes-{AS_OF}.json").write_text(json.dumps(
        {t: {"alpha": v[3], "beat": v[4]} for t, v in names.items()}))
    (tmp_path / f"panel-results-sim-middle-{AS_OF}.json").write_text(json.dumps(
        {"asOf": AS_OF, "summary": [
            {"slug": t, "as_of": AS_OF, "ruler_pass": v[2], "rulings": v[1]}
            for t, v in names.items()]}))
    return tmp_path


def test_the_tier_comes_from_the_dossier_alone():
    """Jake, 2026-09-23: good/mid/bad label the DOSSIER, never the outcome.

    Live the funnel sees only the dossier, so a tier that folded in the realized
    window would grade the funnel against information it will never have.
    """
    assert ssl.dossier_tier(_grades("strong", "strong", "strong", "strong")) == "good"
    assert ssl.dossier_tier(_grades("strong", "strong", "strong", "adequate")) == "mid"
    assert ssl.dossier_tier(_grades("adequate", "adequate", "adequate", "adequate")) == "mid"
    assert ssl.dossier_tier(_grades("strong", "strong", "strong", "weak")) == "bad"
    assert ssl.dossier_tier(_grades("strong", "strong", "strong", "absent")) == "bad"


def test_a_clean_dossier_can_still_be_only_mid():
    """quality and tier split: all-adequate is a whole record but a mid thesis."""
    g = _grades("adequate", "adequate", "adequate", "adequate")
    assert ssl.dossier_quality(g) == "clean" and ssl.dossier_tier(g) == "mid"


def test_the_scorer_groups_by_tier(tmp_path):
    clean = _grades("strong", "strong", "strong", "strong")
    mid = _grades("strong", "strong", "adequate", "adequate")
    holed = _grades("strong", "strong", "weak", "adequate")
    root = _root(tmp_path, {
        "AAA": (clean, dict.fromkeys(TESTS, "bull"), True, 0.25, True),
        "BBB": (mid, dict.fromkeys(TESTS, "gap"), True, -0.25, False),
        "CCC": (holed, {"business_case": "bear", "fundamentals": "bear",
                        "demand_case": "gap", "positioned": "bull"}, False, -0.50, False),
    })
    s = ssl.score(AS_OF, root=root)
    assert s["records"] == 3 and s["graded"] == 3 and s["ungraded"] == []
    assert s["by_tier"]["good"]["n"] == 1 and s["by_tier"]["good"]["keep_rate"] == 1.0
    assert s["by_tier"]["mid"]["n"] == 1
    assert s["by_tier"]["bad"]["keep_rate"] == 0.0
    assert s["by_tier"]["bad"]["cut_names"] == ["CCC"]


def test_the_beat_rate_is_reported_beside_the_tier_not_inside_it(tmp_path):
    """The rubric's own check: good dossiers should beat SPY more often than
    mid ones. A good dossier that LOST still counts as good."""
    clean = _grades("strong", "strong", "strong", "strong")
    root = _root(tmp_path, {
        "AAA": (clean, dict.fromkeys(TESTS, "bull"), True, 0.25, True),
        "BBB": (clean, dict.fromkeys(TESTS, "bull"), True, -0.25, False),
    })
    s = ssl.score(AS_OF, root=root)
    assert s["by_tier"]["good"]["n"] == 2
    assert s["by_tier"]["good"]["tier_beat_rate"] == 0.5


def test_grades_are_read_from_both_files(tmp_path):
    """The sim's own grades cover the names the tuning cohort never drew."""
    clean = _grades("strong", "strong", "strong", "strong")
    root = _root(tmp_path, {"AAA": (clean, dict.fromkeys(TESTS, "bull"), True, 0.25, True)})
    res = json.loads((root / f"panel-results-sim-middle-{AS_OF}.json").read_text())
    res["summary"].append({"slug": "ZZZ", "as_of": AS_OF, "ruler_pass": False,
                           "rulings": dict.fromkeys(TESTS, "bear")})
    (root / f"panel-results-sim-middle-{AS_OF}.json").write_text(json.dumps(res))
    s = ssl.score(AS_OF, root=root)
    assert s["ungraded"] == ["ZZZ"], "with no sim grades ZZZ has no tier"
    (root / f"sim-grades-{AS_OF}.json").write_text(json.dumps(
        {"rows": [{"ticker": "ZZZ", "as_of": AS_OF,
                   "grades": _grades("weak", "weak", "adequate", "strong")}]}))
    s = ssl.score(AS_OF, root=root)
    assert s["ungraded"] == [] and s["by_tier"]["bad"]["n"] == 1


def test_a_sim_graded_name_needs_no_outcome_row(tmp_path):
    """Sim names outside the draw have no realized window; they still tier."""
    clean = _grades("strong", "strong", "strong", "strong")
    root = _root(tmp_path, {"AAA": (clean, dict.fromkeys(TESTS, "bull"), True, 0.25, True)})
    res = json.loads((root / f"panel-results-sim-middle-{AS_OF}.json").read_text())
    res["summary"].append({"slug": "ZZZ", "as_of": AS_OF, "ruler_pass": True,
                           "rulings": dict.fromkeys(TESTS, "bull")})
    (root / f"panel-results-sim-middle-{AS_OF}.json").write_text(json.dumps(res))
    (root / f"sim-grades-{AS_OF}.json").write_text(json.dumps(
        {"rows": [{"ticker": "ZZZ", "as_of": AS_OF, "grades": clean}]}))
    s = ssl.score(AS_OF, root=root)
    good = s["by_tier"]["good"]
    assert good["n"] == 2 and good["with_outcome"] == 1
    assert good["mean_alpha"] == pytest.approx(0.25), "the outcome-less name is not a zero"


def test_bear_wins_split_by_kept_and_cut(tmp_path):
    clean = _grades("strong", "strong", "strong", "strong")
    root = _root(tmp_path, {
        "AAA": (clean, dict.fromkeys(TESTS, "bull"), True, 0.25, True),
        "BBB": (clean, dict.fromkeys(TESTS, "bear"), False, -0.25, False),
    })
    s = ssl.score(AS_OF, root=root)
    assert s["by_tier"]["good"]["mean_bear_wins_kept"] == 0
    assert s["by_tier"]["good"]["mean_bear_wins_cut"] == 4
