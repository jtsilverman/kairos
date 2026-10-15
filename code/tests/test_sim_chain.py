"""sim_chain: the split and merge joints an unattended chain relies on."""

import importlib.util
import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("sim_chain", _ROOT / "scripts" / "sim_chain.py")
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)

ARGS = {"asOf": "2026-06-01", "root": "/r", "names": [{"ticker": f"T{i:02d}", "docIds": "P1"} for i in range(11)]}


def _returns(tmp_path, prefix, out_prefix, *, drop=None, wrap=True):
    for b in sorted(tmp_path.glob("a-b*.json")):
        n = int(b.stem.split("-b")[1])
        names = [x["ticker"] for x in json.loads(b.read_text())["names"]]
        summary = [{"slug": t} for t in names if t != drop]
        inner = {"summary": summary, "dropped": [drop] if drop in names else []}
        obj = {"summary": "a description", "result": inner} if wrap and n % 2 else inner
        Path(f"{out_prefix}{n}.json").write_text(json.dumps(obj))


def test_split_makes_batches_of_eight_and_sets_the_layer(tmp_path):
    assert sc.split(ARGS, str(tmp_path / "a-b"), "middle") == 2
    b1 = json.loads((tmp_path / "a-b1.json").read_text())
    assert len(b1["names"]) == 8 and b1["layer"] == "middle" and b1["root"] == "/r"
    assert len(json.loads((tmp_path / "a-b2.json").read_text())["names"]) == 3


def test_merge_reads_both_saved_shapes_into_one_results_file(tmp_path):
    sc.split(ARGS, str(tmp_path / "a-b"))
    _returns(tmp_path, str(tmp_path / "a-b"), str(tmp_path / "o-b"))
    res = sc.merge(ARGS, str(tmp_path / "a-b"), str(tmp_path / "o-b"))
    assert sorted(r["slug"] for r in res["summary"]) == [n["ticker"] for n in ARGS["names"]]


def test_merge_refuses_a_dropped_name(tmp_path):
    sc.split(ARGS, str(tmp_path / "a-b"))
    _returns(tmp_path, str(tmp_path / "a-b"), str(tmp_path / "o-b"), drop="T09")
    with pytest.raises(sc.ChainError, match="dropped"):
        sc.merge(ARGS, str(tmp_path / "a-b"), str(tmp_path / "o-b"))


def test_merge_refuses_a_missing_return(tmp_path):
    sc.split(ARGS, str(tmp_path / "a-b"))
    _returns(tmp_path, str(tmp_path / "a-b"), str(tmp_path / "o-b"))
    (tmp_path / "o-b2.json").unlink()
    with pytest.raises(sc.ChainError, match="no return"):
        sc.merge(ARGS, str(tmp_path / "a-b"), str(tmp_path / "o-b"))


def test_rows_refuses_a_short_sorter_return(tmp_path):
    (tmp_path / "s-b1.json").write_text(json.dumps({"result": {"rows": [{"ticker": "T00"}], "dropped": []}}))
    with pytest.raises(sc.ChainError):
        sc.rows(ARGS, str(tmp_path / "s-b"))
