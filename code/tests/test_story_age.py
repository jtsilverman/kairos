"""dossier-data U1 RED: story age — per-session RS-percentile history
reproducing the live screen field pipeline, and the attainment scan.

The history builder must apply the same field construction as the weekly
screen (screen.rs_field_eligible mask -> rs.rs_raw -> rs_percentile
semantics, screen.py:160-161) or the percentiles fork from the screen's
stored rs — the exact failure the spec's AC4 seam check exists to catch.
Expected values are computed through the LIVE functions (rs.rs_raw +
rs.rs_percentile) as the independent oracle, never through story_age's
own internals.
"""

from __future__ import annotations

from kairos.signals import rs, story_age


def _sessions(n, tickers):
    """Ordered [(date, {ticker: (close, volume)})] fixture. `tickers` maps
    ticker -> (close_fn(i), volume, first_session_index)."""
    out = []
    for i in range(n):
        bars = {}
        for t, (close_fn, volume, start) in tickers.items():
            if i >= start:
                bars[t] = (close_fn(i), volume)
        out.append((f"d{i:03d}", bars))
    return out


def _oracle_pct(closes_by_ticker):
    """Independent expected percentile: the live screen's own pipeline."""
    return rs.rs_percentile(
        {t: rs.rs_raw(c[-253:]) for t, c in closes_by_ticker.items()})


def test_percentile_history_matches_live_screen_pipeline():
    # AAA rising, BBB flat — both eligible; DDD lists too late to rank.
    n = 260
    sess = _sessions(n, {
        "AAA": (lambda i: 10.0 + 0.1 * i, 1_000_000.0, 0),
        "BBB": (lambda i: 50.0, 200_000.0, 0),
        "DDD": (lambda i: 20.0, 1_000_000.0, 160),  # 100 appearances < 253
    })
    hist = story_age.percentile_history(sess, targets={"AAA", "BBB", "DDD"})
    # evaluation sessions: one per session once 253 appearances are possible
    assert len(hist["AAA"]) == n - 252
    expected = _oracle_pct({
        "AAA": [10.0 + 0.1 * i for i in range(n)],
        "BBB": [50.0] * n,
    })
    date, aaa_pct = hist["AAA"][-1]
    assert date == "d259"
    assert aaa_pct == expected["AAA"] == 100.0
    assert hist["BBB"][-1][1] == expected["BBB"] == 0.0
    # never-rankable ticker: present in output, None at every session
    assert all(p is None for _, p in hist["DDD"])


def test_percentile_history_applies_field_eligibility_mask():
    # CCC trades under the $5 field floor with a NEGATIVE score. If the
    # rs_field_eligible mask were skipped, the field would be
    # [CCC(-), BBB(0), AAA(+)] and BBB would rank 50.0; with the mask the
    # field is [BBB, AAA] and BBB ranks 0.0.
    n = 260
    sess = _sessions(n, {
        "AAA": (lambda i: 10.0 + 0.1 * i, 1_000_000.0, 0),
        "BBB": (lambda i: 50.0, 200_000.0, 0),
        "CCC": (lambda i: 4.5 - i * (1.0 / n), 10_000_000.0, 0),
    })
    hist = story_age.percentile_history(sess, targets={"AAA", "BBB", "CCC"})
    assert hist["BBB"][-1][1] == 0.0
    assert hist["AAA"][-1][1] == 100.0
    # the masked ticker itself gets no percentile — omit, never fake
    assert hist["CCC"][-1][1] is None


# --- attainment scan ---

def test_story_age_sessions_since_first_attainment():
    h = ([(f"d{i}", 85.0) for i in range(6)]
         + [("d6", 90.0)]  # >= is attainment (boundary, exact 90.0)
         + [(f"d{i}", 95.0) for i in range(7, 10)])
    assert story_age.scan(h) == {"sessions": 3, "left_censored": False, "window_sessions": 10}


def test_story_age_left_censored_at_window_start():
    h = [(f"d{i}", 95.0) for i in range(10)]
    assert story_age.scan(h) == {"sessions": 9, "left_censored": True, "window_sessions": 10}


def test_story_age_never_rankable_returns_none():
    h = [(f"d{i}", None) for i in range(10)]
    assert story_age.scan(h) is None


def test_story_age_never_attained_returns_none():
    h = [(f"d{i}", 80.0) for i in range(10)]
    assert story_age.scan(h) is None


def test_story_age_counts_from_first_rankability():
    # IPO-shaped: unrankable for 4 sessions, >=90 at its first rankable
    # session — counts from first rankability, NOT left-censored.
    h = ([(f"d{i}", None) for i in range(4)]
         + [(f"d{i}", 92.0) for i in range(4, 10)])
    assert story_age.scan(h) == {"sessions": 5, "left_censored": False, "window_sessions": 10}


def test_percentile_history_evicts_names_no_longer_trading():
    # ZZZ trades sessions 0..299 then dies. build_bars' implicit rule
    # (253 closes within the trailing ~257-session span) keeps a name at
    # most ~4 sessions after its last trade: at t=303 its window-opening
    # appearance (index 47) still fits t-256=47; at t=304 it does not.
    n = 320
    sess = _sessions(n, {
        "AAA": (lambda i: 10.0 + 0.1 * i, 1_000_000.0, 0),
        "BBB": (lambda i: 50.0, 200_000.0, 0),
    })
    for i in range(300):  # ZZZ present only for sessions 0..299
        sess[i][1]["ZZZ"] = (30.0, 1_000_000.0)
    hist = story_age.percentile_history(sess, targets={"ZZZ"})
    by_idx = {252 + j: p for j, (_, p) in enumerate(hist["ZZZ"])}
    assert by_idx[303] is not None
    assert by_idx[304] is None
    assert by_idx[319] is None


def test_percentile_history_excludes_gappy_names_the_screen_never_ranks():
    # GGG trades every other session: 253 appearances need ~506 trailing
    # sessions, far outside the ~257-session span build_bars scans — the
    # live screen would never rank it, so the history must not either.
    n = 600
    sess = _sessions(n, {
        "AAA": (lambda i: 10.0 + 0.1 * i, 1_000_000.0, 0),
        "BBB": (lambda i: 50.0, 200_000.0, 0),
    })
    for i in range(0, n, 2):
        sess[i][1]["GGG"] = (30.0, 1_000_000.0)
    hist = story_age.percentile_history(sess, targets={"GGG"})
    assert all(p is None for _, p in hist["GGG"])
