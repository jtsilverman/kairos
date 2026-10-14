"""cascade_parts: a packet split under the size cap merges back to one result."""

import importlib.util
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "scripts"))
_spec = importlib.util.spec_from_file_location("cascade_parts", _ROOT / "scripts" / "cascade_parts.py")
cp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cp)

SRC = (_ROOT / "scripts" / "cascade_workflow.js").read_text()


def _packet(n, size=3000):
    return [{"slug": f"N{i:03d}", "sheet": "x" * size} for i in range(n)]


def test_a_packet_over_the_cap_is_split_into_parts_each_under_it(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "CAP", 200_000)
    paths = cp.split("2026-10-06", _packet(120), SRC, str(tmp_path / "c-p"))
    assert len(paths) >= 2
    assert all(len(Path(p).read_bytes()) <= 200_000 * cp.HEADROOM for p in paths)
    assert all("model: SONNET" in Path(p).read_text() for p in paths)


def test_a_packet_under_the_cap_stays_one_part(tmp_path):
    assert len(cp.split("2026-10-06", _packet(10), SRC, str(tmp_path / "c-p"))) == 1


def _ret(slugs, keep):
    return {"rule": "TWO_NO", "counts": {"sheets": len(slugs), "kept": len(keep), "reads": len(slugs)},
            "keeps": keep, "rows": [{"slug": s} for s in slugs]}


def test_merge_sums_counts_and_joins_keeps():
    pk = _packet(4, 1)
    res = cp.merge("d", [_ret(["N000", "N001"], ["N000"]), _ret(["N002", "N003"], ["N003"])], pk)
    assert res["keeps"] == ["N000", "N003"] and res["counts"] == {"sheets": 4, "kept": 2, "reads": 4}


def test_merge_refuses_a_missing_or_duplicated_row():
    pk = _packet(4, 1)
    with pytest.raises(cp.PartsError):
        cp.merge("d", [_ret(["N000", "N001"], [])], pk)
    with pytest.raises(cp.PartsError):
        cp.merge("d", [_ret(["N000", "N001"], []), _ret(["N001", "N002", "N003"], [])], pk)
