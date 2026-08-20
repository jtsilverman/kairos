"""Earnings-call transcripts from the stored Alpha Vantage pulls
(thesis-debate-v2 unit 6b).

Read-only over data/transcripts/<TICKER>/<QUARTER>.json written by
scripts/pull_transcripts.py; no network here. The sha256 is computed over
the canonical transcript-turn JSON so the digest step can journal exactly
which text it summarized (provenance for the [T1] dossier section).
Fail-loud on absence — the dossier runner degrades to [T1]-omitted, this
module never fakes an empty transcript.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_DIR = Path(__file__).resolve().parents[4] / "data" / "transcripts"


class MissingTranscriptError(Exception):
    """No stored transcript for this ticker."""


@dataclass(frozen=True)
class Transcript:
    ticker: str
    quarter: str
    turns: list[dict]      # [{speaker, title, content}, ...] as fetched
    sha256: str            # over canonical turns JSON
    fetched_at: str


def _quarter_end(quarter: str) -> str:
    """'2026Q1' -> '2026-03-31' (calendar-quarter end, ISO)."""
    year, q = quarter.split("Q")
    month = int(q) * 3
    day = {3: 31, 6: 30, 9: 30, 12: 31}[month]
    return f"{year}-{month:02d}-{day:02d}"


def _digest_available_by(meta: dict, quarter: str) -> str:
    """Earliest as_of that may include this digest: the stored call_date, or
    quarter-end + 45 days (standard reporting lag, conservative) when no
    call date is stored — a Q4 call held mid-February must not leak into a
    Feb-02 rewind dossier (thesis-rewind-eval A1)."""
    if meta.get("call_date"):
        return meta["call_date"]
    end = _dt.date.fromisoformat(_quarter_end(quarter))
    return (end + _dt.timedelta(days=45)).isoformat()


def load_digests(ticker: str, *, base_dir: Path | None = None,
                 as_of: str | None = None) -> list[dict]:
    """Stored digest files (<QUARTER>-digest.md, written by the session's
    Sonnet digest step), newest first. `as_of` (ISO date) keeps only digests
    whose call date (stored `call_date:`, else quarter-end + 45 days) is on
    or before as_of. Returns [] when none exist — the dossier runner then
    omits [T1] (omit-never-fake), so absence is a degrade, not an error."""
    d = Path(base_dir or _DEFAULT_DIR) / ticker
    out = []
    for p in sorted(d.glob("*-digest.md"), reverse=True):
        header, _, digest = p.read_text().partition("\n---\n")
        meta = {}
        for line in header.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
        quarter = meta.get("quarter", p.stem.replace("-digest", ""))
        if as_of is not None and _digest_available_by(meta, quarter) > as_of:
            continue
        out.append({"quarter": quarter,
                    "transcript_sha256": meta["transcript_sha256"],
                    "prompt_sha256": meta["prompt_sha256"],
                    "model_alias": meta["model_alias"],
                    "digest": digest.strip()})
    return out


def load_stored(ticker: str, *, base_dir: Path | None = None) -> list[Transcript]:
    """All stored transcripts for a ticker, newest quarter first."""
    d = Path(base_dir or _DEFAULT_DIR) / ticker
    paths = sorted(d.glob("*.json"), reverse=True)  # YYYY'Q'N sorts lexically
    if not paths:
        raise MissingTranscriptError(f"no stored transcript for {ticker} in {d}")
    out = []
    for p in paths:
        body = json.loads(p.read_text())
        turns = body["transcript"]
        out.append(Transcript(
            ticker=ticker,
            quarter=p.stem,
            turns=turns,
            sha256=hashlib.sha256(
                json.dumps(turns, sort_keys=True).encode()).hexdigest(),
            fetched_at=body.get("fetched_at", ""),
        ))
    return out
