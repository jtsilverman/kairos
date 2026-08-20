"""thesis-engine unit 5a RED: dossier compiler — one hashed, doc-id-addressed
text bundle per candidate; the single input every thesis agent reads.

Pure render on injected records; fetching is the runner's job. Doc ids are the
citation namespace: a memo claim cites [F1]/[N2]/... and record-memos later
validates citations resolve, so ids must be stable and enumerable.
"""

from __future__ import annotations

from kairos.thesis import dossier


def _inputs(**over):
    base = dict(
        ticker="MU",
        as_of="2026-07-07",
        price=245.10,
        rs=99.4,
        forensics={"ar_growth": 0.322, "revenue_growth": 0.489,
                   "ni_exceeds_ocf_years": 0, "dilution_rate": 0.01},
        filings=[("10-K", "2025-10-03", "Item 7 MD&A: revenue grew..."),
                 ("8-K", "2026-06-25", "Q3 results press release...")],
        news=[("2026-07-01", "Micron guides above consensus", "DRAM pricing...")],
        insiders=[{"date": "2026-06-20", "insider": "SANJAY M", "role": "CEO",
                   "code": "P", "shares": 5000.0, "price": 240.0,
                   "is_10b5_1": False}],
        revisions={"net_up_30d": 12, "trend_delta_90d": 0.42, "positive": True},
    )
    base.update(over)
    return dossier.DossierInputs(**base)


def test_render_assigns_enumerable_doc_ids():
    d = dossier.build(_inputs())
    # every section id present in the text and the registry
    for doc_id in ("[P1]", "[X1]", "[F1]", "[F2]", "[N1]", "[I1]", "[R1]"):
        assert doc_id in d.text
    assert set(d.doc_ids) == {"P1", "X1", "F1", "F2", "N1", "I1", "R1"}


def test_hash_is_deterministic_and_input_sensitive():
    a = dossier.build(_inputs())
    b = dossier.build(_inputs())
    c = dossier.build(_inputs(price=246.00))
    assert a.sha256 == b.sha256
    assert a.sha256 != c.sha256


def test_forensics_and_context_rendered_verbatim():
    d = dossier.build(_inputs())
    assert "ar_growth" in d.text and "0.322" in d.text
    assert "MU" in d.text and "2026-07-07" in d.text and "99.4" in d.text


def test_missing_revisions_renders_section_absent_not_empty():
    # dimension-3 degraded mode: no revisions source -> no [R1] id at all
    # (an empty-but-present section would invite citations to nothing)
    d = dossier.build(_inputs(revisions=None))
    assert "R1" not in d.doc_ids
    assert "[R1]" not in d.text


def test_earnings_section_renders_date_and_bands():
    d = dossier.build(_inputs(earnings={
        "next_earnings_date": "2026-09-23",
        "eps_consensus": {"low": 28.04, "avg": 31.29, "high": 37.44},
        "revenue_consensus": {"low": 46911000000, "avg": 50756885130,
                              "high": 59805000000}}))
    assert "E1" in d.doc_ids
    assert "[E1] EARNINGS CALENDAR" in d.text
    assert "next_earnings_date: 2026-09-23" in d.text
    assert "eps_consensus" in d.text and "31.29" in d.text


def test_missing_earnings_renders_section_absent_not_empty():
    d = dossier.build(_inputs(earnings=None))
    assert "E1" not in d.doc_ids
    assert "EARNINGS CALENDAR" not in d.text


def test_x1_renders_thresholds_and_flagged_list():
    # adversary + judge must see WHICH ratios flag without the analyst-only
    # workflow injection; thresholds mirror memo.py's contract constants
    d = dossier.build(_inputs(forensics={
        "ar_growth": 0.90, "revenue_growth": 0.10,
        "ni_exceeds_ocf_years": 2, "dilution_rate": 0.08}))
    assert "thresholds: ar_growth > 1.5x revenue_growth" in d.text
    assert "dilution_rate > 5%/yr" in d.text
    assert "ni > ocf 2+ consecutive years" in d.text
    assert "flagged: ar_growth, dilution_rate, ni_exceeds_ocf_years" in d.text


def test_x1_renders_flagged_none_when_clean():
    d = dossier.build(_inputs())  # base forensics breach nothing
    assert "flagged: none" in d.text


# --- [I1] four-bucket Form 4 render (dossier-v4 unit 2) ---

def _f4(date, insider, code, shares, price, plan, role="Director"):
    return {"date": date, "insider": insider, "role": role, "code": code,
            "shares": shares, "price": price, "is_10b5_1": plan}


def test_i1_renders_four_buckets():
    d = dossier.build(_inputs(insiders=[
        _f4("2026-06-20", "SANJAY M", "P", 5000.0, 240.0, False, role="CEO"),
        _f4("2026-07-01", "ARNZEN APRIL S", "S", 4279.0, 1077.05, False,
            role="EVP and Chief People Officer"),
        _f4("2026-07-01", "MURPHY MARK", "S", 1000.0, 1080.0, True, role="CFO"),
        _f4("2026-06-15", "MURPHY MARK", "M", 2000.0, 55.0, True, role="CFO"),
        _f4("2026-06-10", "SADANA SUMIT", "F", 300.0, None, False, role="EVP"),
    ]))
    # bucket 1: non-plan buys prominent, human-readable row
    assert "OPEN-MARKET BUYS (code P, non-plan" in d.text
    assert "2026-06-20 SANJAY M (CEO): 5000 sh @ 240.0" in d.text
    # bucket 2: non-plan discretionary sales visible as their own group
    assert "DISCRETIONARY SALES (code S, non-plan" in d.text
    assert ("2026-07-01 ARNZEN APRIL S (EVP and Chief People Officer): "
            "4279 sh @ 1077.05") in d.text
    # bucket 3: plan rows (aff true, ANY code) collapsed to a single count
    assert "10b5-1 plan transactions: 2 (scheduled; no signal)" in d.text
    assert "MURPHY MARK" not in d.text  # both his rows are plan — collapsed
    # bucket 4: other codes per-code counts, no rows
    assert "other codes: F=1" in d.text
    assert "SADANA SUMIT" not in d.text


def test_i1_cluster_line_when_two_insiders_buy_within_60_days():
    d = dossier.build(_inputs(insiders=[
        _f4("2026-05-01", "SMITH JANE", "P", 1000.0, 50.0, False),
        _f4("2026-06-30", "DOE JOHN", "P", 800.0, 52.0, False),
    ]))
    assert "CLUSTER: 2 distinct insiders bought within 60 days" in d.text


def test_i1_no_cluster_line_on_61_day_gap():
    d = dossier.build(_inputs(insiders=[
        _f4("2026-05-01", "SMITH JANE", "P", 1000.0, 50.0, False),
        _f4("2026-07-01", "DOE JOHN", "P", 800.0, 52.0, False),
    ]))
    assert "CLUSTER" not in d.text


def test_i1_no_cluster_line_when_same_insider_buys_twice():
    d = dossier.build(_inputs(insiders=[
        _f4("2026-06-01", "SMITH JANE", "P", 1000.0, 50.0, False),
        _f4("2026-06-10", "SMITH JANE", "P", 800.0, 52.0, False),
    ]))
    assert "CLUSTER" not in d.text


def test_i1_plan_buys_do_not_feed_the_cluster():
    # scheduled plan buys are no-signal: two insiders whose buys are both
    # 10b5-1 must NOT produce the cluster note
    d = dossier.build(_inputs(insiders=[
        _f4("2026-06-01", "SMITH JANE", "P", 1000.0, 50.0, True),
        _f4("2026-06-10", "DOE JOHN", "P", 800.0, 52.0, True),
    ]))
    assert "CLUSTER" not in d.text


def test_i1_empty_rows_render_section_absent():
    d = dossier.build(_inputs(insiders=[]))
    assert "I1" not in d.doc_ids
    assert "[I1]" not in d.text


# --- [S1] short interest (dossier-v4 unit 4) ---

_SI = {
    "rows": [
        {"settlement_date": "2026-05-29", "short_shares": 37549121,
         "days_to_cover": 1.0, "change_pct": 6.57},
        {"settlement_date": "2026-06-15", "short_shares": 41592382,
         "days_to_cover": 1.0, "change_pct": 10.77},
    ],
    "shares_outstanding": 1_120_000_000,
}


def test_s1_renders_level_trend_and_derived_pct():
    d = dossier.build(_inputs(short_interest=_SI))
    assert "S1" in d.doc_ids
    assert "[S1] SHORT INTEREST" in d.text
    assert ("latest: 41592382 shares short (settlement 2026-06-15), "
            "days-to-cover 1.0") in d.text
    assert ("trend: 2026-05-29: 37549121 (+6.57%), "
            "2026-06-15: 41592382 (+10.77%)") in d.text
    # 41592382 / 1.12e9 = 3.71% — hand-computed, labeled derived
    assert ("short as % of shares outstanding (derived from EDGAR shares "
            "series; true float unavailable): 3.71%") in d.text
    # placement: after the [P1]/[X1] block, before [Q1]-and-later sections
    assert d.doc_ids.index("S1") == d.doc_ids.index("X1") + 1


def test_s1_absent_when_fetch_failed():
    d = dossier.build(_inputs(short_interest=None))
    assert "S1" not in d.doc_ids
    assert "[S1]" not in d.text  # exact marker, never rendered empty


def test_s1_derived_pct_line_omitted_without_shares():
    d = dossier.build(_inputs(short_interest={**_SI, "shares_outstanding": None}))
    assert "[S1] SHORT INTEREST" in d.text
    assert "% of shares outstanding" not in d.text  # omit-never-fake


# --- [E1] dispersion line (dossier-v4 unit 5) ---

def test_e1_renders_dispersion_line_when_present():
    d = dossier.build(_inputs(earnings={
        "next_earnings_date": "2026-09-23",
        "eps_consensus": {"low": 8.0, "avg": 10.0, "high": 12.0},
        "dispersion": {"low": 67.39, "high": 80.16, "avg": 73.32485,
                       "spread": 0.1742, "analysts": 33},
    }))
    # debate-v3 U4: the line names its metric — judges were reading a bare
    # "dispersion" with no unit (audit 2026-07-08)
    # v13: the one-directional editorial ("predicts lower returns") is
    # retired; the metric + input-not-gate framing stay
    assert ("dispersion (current FY EPS, 33 analysts): low 67.39 / avg 73.32485 "
            "/ high 80.16 — spread 17.4% of avg (an LLM input, not a gate)"
            ) in d.text
    assert "predicts lower returns" not in d.text


def test_e1_omits_dispersion_line_when_absent():
    d = dossier.build(_inputs(earnings={"next_earnings_date": "2026-09-23"}))
    assert "[E1] EARNINGS CALENDAR" in d.text
    assert "dispersion" not in d.text  # omitted, not zero


# --- [P1] story-age line (dossier-data U1) ---

def test_p1_renders_story_age_line_when_present():
    d = dossier.build(_inputs(story_age={"sessions": 37, "left_censored": False, "window_sessions": 504}))
    assert ("Story age: first RS>=90 attainment 37 sessions ago "
            "(504-session window, from first rankability; "
            "an LLM input, not a gate)") in d.text
    # the line lives in [P1], before the next section header
    assert d.text.index("Story age:") < d.text.index("[X1]")


def test_p1_renders_story_age_left_censored_as_lower_bound():
    d = dossier.build(_inputs(story_age={"sessions": 503, "left_censored": True, "window_sessions": 504}))
    assert "Story age: first RS>=90 attainment >=503 sessions ago" in d.text


def test_p1_omits_story_age_line_when_absent():
    d = dossier.build(_inputs())
    assert "[P1] CONTEXT" in d.text
    assert "Story age:" not in d.text  # omitted, never faked


# --- [Q1] P/S vs own history line (dossier-data U2) ---

_FINANCIALS = dict(
    series={"revenue": [("2025-12-31", 1_000_000.0)]},
    quarterly_revenue=None,
    derived={"ps_ratio": 5.1},
    market_cap=5_100_000.0,
)


def test_q1_renders_ps_history_line_when_present():
    d = dossier.build(_inputs(financials={
        **_FINANCIALS,
        "ps_history": {"percentile": 87.3, "window_sessions": 756,
                       "today_ps": 5.2},
    }))
    assert ("P/S vs own history: percentile 87.3 over the trailing "
            "756-session daily P/S series (annual revenue/shares "
            "vintage-matched, 90d filing lag; an LLM input, not a gate)"
            ) in d.text
    # today_ps stays internal — a second printed P/S beside derived
    # ps_ratio would be a dual-signed datum (AMAT watch)
    assert "5.2" not in d.text


def test_q1_omits_ps_history_line_when_absent():
    d = dossier.build(_inputs(financials=dict(_FINANCIALS)))
    assert "[Q1] FINANCIAL HISTORY" in d.text
    assert "P/S vs own history" not in d.text  # omitted, never faked


# --- [P1] RS decomposition line (dossier-data U3) ---

def test_p1_renders_rs_decomposition_line_when_present():
    d = dossier.build(_inputs(rs_decomposition={
        "63d": 0.2, "126d": 0.5, "252d": 1.0}))
    assert ("RS decomposition: price change 63d +20.0%, 126d +50.0%, "
            "252d +100.0% (the RS score's price legs; estimate-revision "
            "side in [R1]; an LLM input, not a gate)") in d.text
    assert d.text.index("RS decomposition:") < d.text.index("[X1]")
    # no directional editorial, either retired phrasing
    assert "predicts lower returns" not in d.text
    assert "predicts weaker forward returns" not in d.text


def test_p1_omits_rs_decomposition_line_when_absent():
    d = dossier.build(_inputs())
    assert "[P1] CONTEXT" in d.text
    assert "RS decomposition:" not in d.text  # omitted, never faked


# --- thesis-rewind-eval CONTRACT assertion 1: explicit data-gap lines ---

def test_a1_rewind_data_gap_renders_explicit_e1_r1_lines():
    d = dossier.build(_inputs(
        revisions={"data_gap": "no point-in-time revisions vintage exists"},
        earnings={"data_gap": "no point-in-time estimates vintage exists"},
    ))
    # the gap is PRINTED and citable, never a silent omission — agents must
    # see the block is absent by design (rewind dossier, spec A1)
    assert "[R1] ANALYST ESTIMATE REVISIONS: DATA GAP — " \
           "no point-in-time revisions vintage exists" in d.text
    assert "[E1] EARNINGS CALENDAR: DATA GAP — " \
           "no point-in-time estimates vintage exists" in d.text
    assert "R1" in d.doc_ids and "E1" in d.doc_ids
    # no consensus keys leak into a gap rendering
    assert "next_earnings_date" not in d.text
