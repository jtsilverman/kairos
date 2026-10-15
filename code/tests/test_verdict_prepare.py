"""thesis-exemplars unit 11, vision milestone 3: layer-2 args from middle-layer results.

The verdict layer reads each name's bull case, bear case and rulings. Those
run to 10 KB or more per name, so `scripts/verdict_prepare.py` writes them
to `data/cases-<as_of>/<ticker>.json` and the args carry the path plus the
small parts the workflow needs in code (the four ruling words, the overall
word). Every name given runs editor and verdict, pass or not.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import verdict_prepare as vp  # noqa: E402

D = "2026-02-02"


def _rec(t, overall):
    return {"slug": t, "as_of": D, "ruler_pass": overall == "bull", "overall": overall,
            "rulings": {"business_case": "bull", "fundamentals": "gap", "demand_case": "bull", "positioned": "bull"},
            "cases": {"bull": {"tests": {"business_case": {"case": "x" * 300}}},
                      "bear": {"tests": {"business_case": {"case": "y" * 300}}},
                      "ruler": {"tests": {}, "overall": {"ruling": overall, "why": "w" * 40}, "struck": []}},
            "shortlist": False, "p_judge": None, "thesis": None}


def test_args_carry_a_cases_path_and_the_small_parts_only(tmp_path):
    results = tmp_path / "r.json"
    results.write_text(json.dumps({"summary": [_rec("AAA", "bull"), _rec("BBB", "bear")], "dropped": []}))
    args = vp.prepare(D, [results], root=tmp_path, doc_ids={"AAA": "P1 Q1", "BBB": "P1 Q1"})
    assert args["layer"] == "verdict" and args["asOf"] == D
    names = {n["ticker"]: n for n in args["names"]}
    assert set(names) == {"AAA", "BBB"}
    assert names["AAA"]["casesPath"] == str(tmp_path / f"cases-{D}" / "AAA.json")
    assert names["AAA"]["rulings"]["fundamentals"] == "gap" and names["AAA"]["overall"] == "bull"
    assert names["BBB"]["overall"] == "bear", "a ruler-cut name is still given: layer 2 force-passes"
    assert "cases" not in names["AAA"] and len(json.dumps(args)) < 2000
    on_disk = json.loads((tmp_path / f"cases-{D}" / "AAA.json").read_text())
    assert on_disk["bull"]["tests"]["business_case"]["case"].startswith("xxx")
    assert "overall" in on_disk["ruler"]


def test_a_sample_list_restricts_the_names(tmp_path):
    results = tmp_path / "r.json"
    results.write_text(json.dumps({"summary": [_rec("AAA", "bull"), _rec("BBB", "bear")], "dropped": []}))
    args = vp.prepare(D, [results], root=tmp_path, doc_ids={"AAA": "P1", "BBB": "P1"}, only={"BBB"})
    assert [n["ticker"] for n in args["names"]] == ["BBB"]


def test_a_name_with_no_doc_ids_fails_loud(tmp_path):
    results = tmp_path / "r.json"
    results.write_text(json.dumps({"summary": [_rec("AAA", "bull")], "dropped": []}))
    with pytest.raises(KeyError):
        vp.prepare(D, [results], root=tmp_path, doc_ids={})
