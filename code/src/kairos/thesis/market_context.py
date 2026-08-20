"""Render the regime snapshot into the hashed judge-only text block.

The block is compiled once per run (scripts/thesis_market.py), handed to the
JUDGE seat only, and journaled on the memo (market_context_text +
market_context_sha256). The header marker is the exact string the workflow
transcript greps and the citation contract key off: the block is weighing
context, never citable evidence. None in -> None out (omit-never-fake).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from kairos.thesis.regime import RegimeSnapshot

HEADER_MARKER = "context for verdict weighing, NOT citable evidence"


@dataclass(frozen=True)
class MarketContext:
    text: str
    sha256: str


def render(snapshot: RegimeSnapshot | None, *,
           extra_lines: list[str] | None = None) -> MarketContext | None:
    """`extra_lines` (e.g. the rewind base-rate anchor) join the text BEFORE
    hashing — the sha must cover everything the judges read (write and read
    through one seam, the hash-verified-artifact rule)."""
    if snapshot is None:
        return None
    flag = "ON" if snapshot.momentum_crash_risk else "OFF"
    text = (
        f"MARKET CONTEXT (macro regime) — {HEADER_MARKER}\n"
        f"- 10yr-3mo Treasury slope (T10Y3M): {snapshot.t10y3m:.2f}\n"
        f"- HY credit spread (BAMLH0A0HYM2 OAS): {snapshot.hy_oas_level:.2f}"
        f" (1yr percentile {snapshot.hy_oas_pctile_1yr:.0%}, {snapshot.hy_oas_trend})\n"
        f"- VIX: {snapshot.vix_level:.2f} (1yr percentile {snapshot.vix_pctile_1yr:.0%})\n"
        f"- SPY trailing-12m return: {snapshot.spy_12m_return:+.1%}\n"
        f"- momentum-crash-risk: {flag}"
        f" (12m market return negative AND VIX >= 1yr crash percentile)"
    )
    if extra_lines:
        text += "\n" + "\n".join(extra_lines)
    return MarketContext(
        text=text, sha256=hashlib.sha256(text.encode("utf-8")).hexdigest()
    )


# The file on disk carries block.text VERBATIM — no trailing newline, no
# framing. Writer (scripts/thesis_market.py) and reader
# (scripts/record_memos.py --market-context) both route through here so the
# journaled sha is byte-for-byte the sha of the block the judges saw
# (reviewer finding 2026-07-10: a cosmetic trailing newline on the write
# side silently broke that equality forever).
def write_block(block: MarketContext, path) -> None:
    from pathlib import Path

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(block.text)


def load_block(path) -> MarketContext:
    from pathlib import Path

    text = Path(path).read_text()
    return MarketContext(
        text=text, sha256=hashlib.sha256(text.encode("utf-8")).hexdigest()
    )
