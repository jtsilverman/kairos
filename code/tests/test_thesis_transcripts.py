"""thesis-debate-v2 unit 6b RED: transcripts wrapper + [T1] dossier render.

Wrapper reads the stored Alpha Vantage JSON (data/transcripts/<T>/<Q>.json)
into speaker turns + a sha256 over the raw transcript content; fail-loud on
absence. Dossier [T1] renders digest text + transcript sha + digest-prompt
hash, and is ABSENT (id not in doc_ids) when no digest exists —
omit-never-fake.
"""

import hashlib
import json

import pytest

from kairos.data import transcripts
from kairos.thesis import dossier


def _store(tmp_path, ticker, quarter, turns):
    d = tmp_path / ticker
    d.mkdir(parents=True, exist_ok=True)
    body = {"symbol": ticker, "quarter": quarter, "transcript": turns,
            "fetched_at": "2026-07-09T12:00:00+00:00"}
    (d / f"{quarter}.json").write_text(json.dumps(body))
    return body


def test_load_stored_returns_turns_and_sha(tmp_path):
    turns = [{"speaker": "Operator", "title": "Operator", "content": "Welcome."},
             {"speaker": "Jane CEO", "title": "CEO", "content": "Revenue grew."}]
    _store(tmp_path, "CGNX", "2026Q1", turns)
    (ts,) = transcripts.load_stored("CGNX", base_dir=tmp_path)
    assert ts.quarter == "2026Q1"
    assert ts.turns == turns
    # independent recompute: sha over the canonical transcript-list JSON
    expect = hashlib.sha256(
        json.dumps(turns, sort_keys=True).encode()).hexdigest()
    assert ts.sha256 == expect


def test_load_stored_newest_quarter_first(tmp_path):
    _store(tmp_path, "MU", "2025Q4", [{"speaker": "s", "title": "t",
                                       "content": "old"}])
    _store(tmp_path, "MU", "2026Q3", [{"speaker": "s", "title": "t",
                                       "content": "new"}])
    got = transcripts.load_stored("MU", base_dir=tmp_path)
    assert [t.quarter for t in got] == ["2026Q3", "2025Q4"]


def test_load_stored_missing_ticker_raises(tmp_path):
    with pytest.raises(transcripts.MissingTranscriptError):
        transcripts.load_stored("GHM", base_dir=tmp_path)


def _inputs(**over):
    base = dict(ticker="CGNX", as_of="2026-07-07", price=45.2,
                rs={"score": 0.31, "percentile": 96.0},
                forensics={"ar_growth": 0.1, "revenue_growth": 0.2,
                           "ni_exceeds_ocf_years": 0, "dilution_rate": 0.0},
                filings=[("10-K", "2026-02-12", "MD&A text")],
                news=[], insiders=[], revisions=None,
                financials=None, technicals=None, earnings=None,
                transcript_digests=None)
    base.update(over)
    return dossier.DossierInputs(**base)


def test_t1_renders_digest_with_provenance():
    digests = [{"quarter": "2026Q1", "digest": "Guidance raised; tone steady.",
                "transcript_sha256": "e" * 64, "prompt_sha256": "f" * 64,
                "model_alias": "sonnet"}]
    d = dossier.build(_inputs(transcript_digests=digests))
    assert "T1" in d.doc_ids
    assert "[T1]" in d.text
    assert "Guidance raised; tone steady." in d.text
    assert ("e" * 64) in d.text          # transcript sha journaled in-dossier
    assert ("f" * 64) in d.text          # digest prompt hash journaled
    assert "2026Q1" in d.text


def test_t1_absent_when_no_digests():
    d = dossier.build(_inputs(transcript_digests=None))
    assert "T1" not in d.doc_ids
    assert "[T1]" not in d.text


def test_load_digests_parses_provenance_and_skips_missing(tmp_path):
    d = tmp_path / "CGNX"
    d.mkdir(parents=True)
    (d / "2026Q1-digest.md").write_text(
        "---\n"
        "quarter: 2026Q1\n"
        "transcript_sha256: " + "e" * 64 + "\n"
        "prompt_sha256: " + "f" * 64 + "\n"
        "model_alias: sonnet\n"
        "---\n"
        "Guidance raised; tone steady.\n")
    (got,) = transcripts.load_digests("CGNX", base_dir=tmp_path)
    assert got["quarter"] == "2026Q1"
    assert got["transcript_sha256"] == "e" * 64
    assert got["prompt_sha256"] == "f" * 64
    assert got["model_alias"] == "sonnet"
    assert got["digest"] == "Guidance raised; tone steady."
    assert transcripts.load_digests("NOPE", base_dir=tmp_path) == []


def _digest_file(d, quarter, extra=""):
    (d / f"{quarter}-digest.md").write_text(
        "---\n"
        f"quarter: {quarter}\n"
        "transcript_sha256: " + "e" * 64 + "\n"
        "prompt_sha256: " + "f" * 64 + "\n"
        "model_alias: sonnet\n"
        + extra +
        "---\n"
        "digest body\n")


def test_a1_load_digests_as_of_uses_quarter_end_plus_45d_fallback(tmp_path):
    d = tmp_path / "CGNX"
    d.mkdir(parents=True)
    _digest_file(d, "2025Q3")   # quarter ends 2025-09-30, +45d = 2025-11-14
    _digest_file(d, "2025Q4")   # quarter ends 2025-12-31, +45d = 2026-02-14
    # a 2026-02-02 rewind: the Q4 call (mid-Feb typical) postdates as_of
    got = transcripts.load_digests("CGNX", base_dir=tmp_path,
                                   as_of="2026-02-02")
    assert [g["quarter"] for g in got] == ["2025Q3"]
    # by 2026-02-14 the conservative bound admits Q4
    got = transcripts.load_digests("CGNX", base_dir=tmp_path,
                                   as_of="2026-02-14")
    assert [g["quarter"] for g in got] == ["2025Q4", "2025Q3"]


def test_a1_load_digests_as_of_prefers_stored_call_date(tmp_path):
    d = tmp_path / "MU"
    d.mkdir(parents=True)
    # MU reports off-cycle: fiscal Q2 ended 2026-02-26, call held 03-20 —
    # a stored call_date beats the quarter-end heuristic in BOTH directions
    _digest_file(d, "2026Q1", extra="call_date: 2026-03-20\n")
    assert transcripts.load_digests("MU", base_dir=tmp_path,
                                    as_of="2026-03-19") == []
    (got,) = transcripts.load_digests("MU", base_dir=tmp_path,
                                      as_of="2026-03-20")
    assert got["quarter"] == "2026Q1"
