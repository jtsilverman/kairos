#!/usr/bin/env python3
"""Score a rewind cohort's verdicts against realized one-quarter alpha vs SPY
(thesis-rewind-eval CONTRACT A4).

Mirrors the live ledger's outcome definition exactly (one alpha definition
in the project): entry = first close STRICTLY after as_of; exit = first
available close on/after as_of + one quarter (91 calendar days); alpha =
ticker_return - spy_return; hit sign by derived direction. Prints, per
cohort: the per-name table, Spearman rank correlation (p_outperform vs
realized alpha), Brier score by conviction band, and the challenger-p
distribution (the advocacy-lock diagnostic). Two invocations on identical
inputs produce identical output: pure functions, sorted iteration, no
clock reads.

Usage:
    .venv/bin/python scripts/score_rewind.py --records records.json \
        --as-of 2026-02-02 [--verbose]

records.json: records_from_journal.py output (per name: judge p_outperform,
per-seat p including the challenger seat).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code" / "src"))

logger = logging.getLogger("score_rewind")

HORIZON_DAYS = 91  # one quarter, frozen (specs/vision.md, Jake 2026-08-18).
# One full earnings cycle. The evidence the panel reads re-rates on the
# earnings print, and a 56-day window often closed before the next one.


class IncompleteWindowError(RuntimeError):
    """The close series ends before the horizon — the cohort is not yet
    scoreable; never fake an exit price."""


def outcome(series: list[tuple[str, float]], spy: list[tuple[str, float]],
            *, as_of: str, horizon_days: int = HORIZON_DAYS) -> dict:
    """Realized outcome for one name. `series`/`spy` are (iso_date, close)
    ascending. Entry: first close strictly after as_of (both legs on the
    ENTRY date). Exit: first available close on/after as_of + horizon_days
    (missing bars roll forward, mirroring ledger.close_out). The default is
    the frozen quarter; a longer read passes its horizon explicitly."""
    horizon = (dt.date.fromisoformat(as_of)
               + dt.timedelta(days=horizon_days)).isoformat()
    t_by_date = dict(series)
    s_by_date = dict(spy)
    shared = sorted(set(t_by_date) & set(s_by_date))
    entry_date = next((d for d in shared if d > as_of), None)
    exit_date = next((d for d in shared if d >= horizon), None)
    if entry_date is None or exit_date is None:
        raise IncompleteWindowError(
            f"series ends before {'entry' if entry_date is None else 'horizon'}"
            f" (as_of {as_of}, horizon {horizon})")
    t_ret = t_by_date[exit_date] / t_by_date[entry_date] - 1.0
    s_ret = s_by_date[exit_date] / s_by_date[entry_date] - 1.0
    alpha = t_ret - s_ret
    return {"entry_date": entry_date, "exit_date": exit_date,
            "ticker_return": t_ret, "spy_return": s_ret,
            "alpha": alpha, "beat": alpha > 0}


def _ranks(xs: list[float]) -> list[float]:
    """Average ranks (ties share the mean rank), 1-based."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        mean_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = mean_rank
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float:
    """Spearman rank correlation = Pearson correlation of the ranks
    (tie-safe; the d^2 shortcut assumes no ties)."""
    rx, ry = _ranks(list(xs)), _ranks(list(ys))
    n = len(rx)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    if vx == 0 or vy == 0:
        raise ValueError("degenerate ranks (all-equal input)")
    return cov / (vx * vy) ** 0.5


def brier_by_band(rows: list[dict]) -> dict[str, float]:
    """Mean (p - beat)^2 grouped by the code-derived conviction band."""
    from kairos.thesis.memo import band_from_p

    sums: dict[str, list[float]] = {}
    for r in rows:
        band = band_from_p(r["p"])
        sums.setdefault(band, []).append((r["p"] - (1.0 if r["beat"] else 0.0)) ** 2)
    return {band: sum(v) / len(v) for band, v in sorted(sums.items())}


def challenger_distribution(ps: list[float]) -> dict:
    """The advocacy-lock diagnostic: an honest directed searcher sometimes
    reports a dead short case (p > 0.5); a near-zero fraction over a train
    set is the lock signature (spec anti-skew layer 3)."""
    n = len(ps)
    return {"n": n,
            "frac_above_half": (sum(1 for p in ps if p > 0.5) / n) if n else None,
            "min": min(ps) if ps else None,
            "max": max(ps) if ps else None}


def _closes(ticker: str, start: str, end: str) -> list[tuple[str, float]]:
    from kairos.data.polygon import fetch_grouped_daily

    out = []
    d = dt.date.fromisoformat(start)
    stop = dt.date.fromisoformat(end)
    while d <= stop:
        if d.weekday() < 5:
            m = {b.ticker: b.close for b in fetch_grouped_daily(d.isoformat())}
            if ticker in m:
                out.append((d.isoformat(), m[ticker]))
        d += dt.timedelta(days=1)
    return out


def score_cohort(records: list[dict], *, as_of: str,
                 closes_fn=None) -> dict:
    """Deterministic cohort scoreboard. `closes_fn(ticker, start, end)` is
    injectable for tests; default reads the grouped-daily cache."""
    closes_fn = closes_fn or _closes
    end = (dt.date.fromisoformat(as_of)
           + dt.timedelta(days=HORIZON_DAYS + 21)).isoformat()
    spy = closes_fn("SPY", as_of, end)
    rows = []
    for r in sorted(records, key=lambda r: r["ticker"]):
        o = outcome(closes_fn(r["ticker"], as_of, end), spy, as_of=as_of)
        rows.append({"ticker": r["ticker"], "p": r["judge"]["p_outperform"],
                     "challenger_p": r.get("challenger", {}).get("p_outperform"),
                     **o})
    ps = [row["p"] for row in rows]
    alphas = [row["alpha"] for row in rows]
    ch = [row["challenger_p"] for row in rows
          if row["challenger_p"] is not None]
    return {"as_of": as_of, "n": len(rows), "rows": rows,
            "spearman": spearman(ps, alphas),
            "brier_by_band": brier_by_band(
                [{"p": row["p"], "beat": row["beat"]} for row in rows]),
            "challenger": challenger_distribution(ch)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True)
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        stream=sys.stderr, format="%(name)s %(levelname)s %(message)s")

    records = json.loads(Path(args.records).read_text())
    s = score_cohort(records, as_of=args.as_of)
    print(f"cohort {s['as_of']}: n={s['n']}  spearman {s['spearman']:+.3f}")
    print(f"brier by band: " + json.dumps(s["brier_by_band"], sort_keys=True))
    print(f"challenger p: " + json.dumps(s["challenger"], sort_keys=True))
    fmt = "{:<6} {:>5} {:>6} {:>11} {:>11} {:>8} {:>5}"
    print(fmt.format("name", "p", "chal_p", "entry", "exit", "alpha", "beat"))
    for row in s["rows"]:
        print(fmt.format(
            row["ticker"], f"{row['p']:.2f}",
            "-" if row["challenger_p"] is None else f"{row['challenger_p']:.2f}",
            row["entry_date"], row["exit_date"],
            f"{row['alpha']:+.3f}", "Y" if row["beat"] else "N"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
