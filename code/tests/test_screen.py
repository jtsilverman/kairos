"""thesis-engine unit 3b RED: redesigned mechanical screen — all-hard-gate
funnel (2026-07-08). No tracks, no ranking, no mcap band.

Pure logic on injected per-ticker records; fetching is the runner's job.
Expected values hand-set, never recomputed through the screen's own math.
"""

from __future__ import annotations

import pytest

from kairos import screen


def _bars(*, price=50.0, dvol=40_000_000.0, closes=None):
    return screen.BarsSummary(
        price=price,
        dollar_vol_20d_median=dvol,
        closes=closes if closes is not None else [price] * 253,
    )


def _uptrend_closes(n: int = 253, *, start: float = 50.0, end: float = 100.0) -> list[float]:
    """Monotone rise: close > 50d MA > 200d MA, 200d MA rising."""
    step = (end - start) / (n - 1)
    return [start + i * step for i in range(n)]


def _downtrend_closes(n: int = 253, *, start: float = 100.0, end: float = 50.0) -> list[float]:
    step = (end - start) / (n - 1)
    return [start + i * step for i in range(n)]


# --- admission floors ---

def test_admission_floors_reject_each_independently():
    assert screen.admission_eligible(_bars()) is True
    assert screen.admission_eligible(_bars(price=9.99)) is False
    assert screen.admission_eligible(_bars(dvol=24_999_999.0)) is False


def test_rs_field_is_broader_than_admission():
    # $5-$10 price / $5M-$25M dvol names are IN the percentile field but NOT admissible
    b = _bars(price=7.0, dvol=10_000_000.0)
    assert screen.rs_field_eligible(b) is True
    assert screen.admission_eligible(b) is False


# --- trend template ---

def test_trend_template_passes_uptrend_fails_downtrend():
    assert screen.trend_template(_uptrend_closes()) is True
    assert screen.trend_template(_downtrend_closes()) is False


def test_trend_template_fails_flat_below_50d():
    # rose for 200 sessions then broke down 20%: close < 50d MA
    closes = _uptrend_closes(233) + [_uptrend_closes(233)[-1] * 0.8] * 20
    assert screen.trend_template(closes) is False


def test_trend_template_requires_enough_history():
    assert screen.trend_template([50.0] * 100) is False  # < 221 closes: cannot judge


# --- fundamental gates ---

_GROWING = screen.Fundamentals(
    revenue=[("2024-12-31", 100.0), ("2025-12-31", 120.0)],
    receivables=[("2024-12-31", 10.0), ("2025-12-31", 11.0)],
    net_income=[("2024-12-31", 5.0), ("2025-12-31", 7.0)],
    operating_cash_flow=[("2024-12-31", 9.0), ("2025-12-31", 12.0)],
    shares=[("2024-12-31", 100.0), ("2025-12-31", 101.0)],
)


def test_fundamental_gates_require_growth_and_positive_ocf():
    assert screen.fundamentals_pass(_GROWING) is True
    shrinking = screen.Fundamentals(
        revenue=[("2024-12-31", 100.0), ("2025-12-31", 90.0)],
        receivables=_GROWING.receivables,
        net_income=_GROWING.net_income,
        operating_cash_flow=_GROWING.operating_cash_flow,
        shares=_GROWING.shares,
    )
    assert screen.fundamentals_pass(shrinking) is False
    burning = screen.Fundamentals(
        revenue=_GROWING.revenue,
        receivables=_GROWING.receivables,
        net_income=_GROWING.net_income,
        operating_cash_flow=[("2024-12-31", 3.0), ("2025-12-31", -2.0)],
        shares=_GROWING.shares,
    )
    assert screen.fundamentals_pass(burning) is False


# --- forensic ratios: computed outputs, never gates ---

def test_forensics_computes_ratios_without_gating():
    f = screen.Fundamentals(
        revenue=[("2024-12-31", 100.0), ("2025-12-31", 120.0)],   # +20%
        receivables=[("2024-12-31", 10.0), ("2025-12-31", 18.0)],  # +80%
        net_income=[("2024-12-31", 12.0), ("2025-12-31", 14.0)],
        operating_cash_flow=[("2024-12-31", 8.0), ("2025-12-31", 9.0)],
        shares=[("2024-12-31", 100.0), ("2025-12-31", 106.0)],    # +6%
    )
    fx = screen.forensics(f)
    assert fx["ar_growth"] == pytest.approx(0.80)
    assert fx["revenue_growth"] == pytest.approx(0.20)
    assert fx["ni_exceeds_ocf_years"] == 2
    assert fx["dilution_rate"] == pytest.approx(0.06)
    # a forensically ugly but growing+cash-generating name still passes the gates
    assert screen.fundamentals_pass(f) is True


def test_forensics_clean_name_reads_clean():
    fx = screen.forensics(_GROWING)
    assert fx["ni_exceeds_ocf_years"] == 0
    assert fx["dilution_rate"] == pytest.approx(0.01)
    assert fx["ar_growth"] == pytest.approx(0.10)


# --- exclusions ---

def test_biotech_excluded_by_industry_string():
    assert screen.industry_excluded("Biotechnology") is True
    assert screen.industry_excluded("biotechnology & drugs") is True
    assert screen.industry_excluded("Packaged Software") is False


def test_mcap_floor():
    assert screen.mcap_floor_pass(500_000_000) is True
    assert screen.mcap_floor_pass(499_999_999) is False


# --- orchestrator ---

def _mk_field():
    """RS-90 requires top decile: 1 strong name over ~20 weak ones."""
    field = {
        # survivor shape: admissible, uptrend, top RS
        "LEAD": _bars(price=100.0, closes=_uptrend_closes(end=100.0)),
        # in RS field only (price $7): boosts percentile field, never admissible
        "SMALL": _bars(price=7.0, dvol=10_000_000.0,
                       closes=_uptrend_closes(start=3.6, end=7.0)),
        # admissible + strong RS but downtrend: trend gate rejects
        "FALLEN": _bars(price=60.0, closes=_downtrend_closes(start=100.0, end=60.0)),
        # biotech, otherwise survivor-shaped
        "BIO": _bars(price=90.0, closes=_uptrend_closes(start=46.0, end=90.0)),
    }
    # admissible + trend-template-passing but mild RS: pins the RS >= 90 gate.
    # Deleting the RS clause from run_screen must redden this fixture's
    # absence assertion. Gains kept DISTINCT (ties share the lower percentile
    # rank and would drag LEAD below 90).
    field["MILD"] = _bars(price=40.0, closes=_uptrend_closes(start=36.0, end=40.0))
    # field-only names above MILD, below LEAD/BIO (price $7: never admissible):
    # push MILD's percentile below 90
    field["S0"] = _bars(price=6.0, dvol=10_000_000.0,
                        closes=_uptrend_closes(start=3.5, end=6.0))
    field["S1"] = _bars(price=6.5, dvol=10_000_000.0,
                        closes=_uptrend_closes(start=3.5, end=6.5))
    # weak padding so LEAD/BIO sit >= 90th percentile
    field.update({
        f"W{i}": _bars(price=30.0, closes=[30.0] * 253) for i in range(26)
    })
    return field


def test_run_screen_all_gates_and_logged_exclusions():
    def profile(t):
        return screen.Profile(
            market_cap=2_000_000_000,
            industry="Biotechnology" if t == "BIO" else "Packaged Software",
        )

    fundamentals_calls = []

    def fundamentals(t):
        fundamentals_calls.append(t)
        return _GROWING

    result = screen.run_screen(
        _mk_field(), profile_fetch=profile, fundamentals_fetch=fundamentals,
    )
    tickers = {c.ticker for c in result.survivors}
    assert "LEAD" in tickers
    assert "FALLEN" not in tickers and "FALLEN" not in result.exclusions  # bars-stage, not logged
    assert "SMALL" not in tickers
    # RS gate pinned: MILD is admissible and trend-passing, RS ~79 < 90
    assert "MILD" not in tickers and "MILD" not in result.exclusions
    assert result.exclusions["BIO"] == "industry"
    # provider fetches only for bars-stage survivors: FALLEN/SMALL/W* never fetched
    assert "FALLEN" not in fundamentals_calls and "SMALL" not in fundamentals_calls
    # survivor carries rs + forensics for the LLM handoff
    lead = next(c for c in result.survivors if c.ticker == "LEAD")
    assert lead.rs >= 90.0
    assert "ar_growth" in lead.forensics


def test_run_screen_mcap_floor_excludes():
    def profile(t):
        return screen.Profile(
            market_cap=400_000_000 if t == "LEAD" else 2_000_000_000,
            industry="Packaged Software",
        )

    result = screen.run_screen(
        _mk_field(), profile_fetch=profile, fundamentals_fetch=lambda t: _GROWING,
    )
    assert result.exclusions["LEAD"] == "mcap_floor"
    assert "LEAD" not in {c.ticker for c in result.survivors}


def test_run_screen_fundamental_gate_excludes():
    shrinking = screen.Fundamentals(
        revenue=[("2024-12-31", 100.0), ("2025-12-31", 90.0)],
        receivables=_GROWING.receivables,
        net_income=_GROWING.net_income,
        operating_cash_flow=_GROWING.operating_cash_flow,
        shares=_GROWING.shares,
    )

    result = screen.run_screen(
        _mk_field(),
        profile_fetch=lambda t: screen.Profile(
            market_cap=2_000_000_000, industry="Packaged Software"),
        fundamentals_fetch=lambda t: shrinking if t == "LEAD" else _GROWING,
    )
    assert result.exclusions["LEAD"] == "fundamentals"
    assert "LEAD" not in {c.ticker for c in result.survivors}


def test_run_screen_data_error_becomes_logged_exclusion():
    from kairos.data.estimates import MissingEstimatesError

    def profile(t):
        if t == "LEAD":
            raise MissingEstimatesError("no industry (ETF)")
        return screen.Profile(market_cap=2_000_000_000, industry="Packaged Software")

    result = screen.run_screen(
        _mk_field(), profile_fetch=profile, fundamentals_fetch=lambda t: _GROWING,
    )
    assert result.exclusions["LEAD"].startswith("data_error:")
    assert "LEAD" not in {c.ticker for c in result.survivors}
    assert "BIO" in {c.ticker for c in result.survivors}  # sweep survived the error


def test_zero_prior_year_value_never_crashes_the_sweep():
    """RED: a filer with a 0.0 prior-year series value (SPAC/shell revenue,
    zero receivables) raised ZeroDivisionError in _growth and killed the
    WHOLE screen (2025-07-07 as-of run). Growth vs a zero base is
    unjudgeable: fundamentals_pass fails that name; forensics reports None."""
    f = screen.Fundamentals(
        revenue=[("2024-12-31", 0.0), ("2025-12-31", 500.0)],
        receivables=[("2024-12-31", 0.0), ("2025-12-31", 50.0)],
        net_income=[("2025-12-31", 10.0)],
        operating_cash_flow=[("2025-12-31", 20.0)],
        shares=[("2024-12-31", 0.0), ("2025-12-31", 100.0)],
    )
    assert screen.fundamentals_pass(f) is False
    fx = screen.forensics(f)
    assert fx["revenue_growth"] is None
    assert fx["ar_growth"] is None
    assert fx["dilution_rate"] is None


# --- thesis-rewind-eval CONTRACT assertion 2: PIT screen gates ---

def _facts_fy(rows):
    def fy_rows():
        return [{"form": "10-K", "fp": "FY", "start": f"{y}-01-01",
                 "end": f"{y}-12-31", "val": v, "filed": filed}
                for y, v, filed in rows]
    tags = ("Revenues", "AccountsReceivableNetCurrent", "NetIncomeLoss",
            "NetCashProvidedByUsedInOperatingActivities",
            "CommonStockSharesOutstanding")
    return {"facts": {"us-gaap": {
        t: {"units": {"USD": fy_rows()}} for t in tags}}}


def test_a2_fundamentals_from_facts_filed_lte_flips_the_growth_gate():
    # FY2025 (filed 2026-02-25) turns growth positive; the Feb-02 rewind
    # must not see it — the PIT view (FY2023->FY2024 shrinking) fails the gate
    facts = _facts_fy([(2023, 100.0, "2024-02-20"),
                       (2024, 90.0, "2025-02-20"),
                       (2025, 200.0, "2026-02-25")])
    live = screen.fundamentals_from_facts(facts)
    pit = screen.fundamentals_from_facts(facts, filed_lte="2026-02-02")
    assert [e for e, _ in live.revenue][-1] == "2025-12-31"
    assert [e for e, _ in pit.revenue][-1] == "2024-12-31"


def test_a2_pit_market_cap_multiplies_asof_close_by_vintage_shares():
    facts = _facts_fy([(2024, 100_000_000.0, "2025-02-20"),
                       (2025, 120_000_000.0, "2026-02-25")])
    pit = screen.fundamentals_from_facts(facts, filed_lte="2026-02-02")
    # Feb-02 rewind: the FY2025 count (filed 02-25) is invisible; mcap uses
    # the FY2024 count. 4.90 x 100M = 490M < the 500M floor -> gate flips
    # vs the live-vintage 4.90 x 120M = 588M
    assert screen.pit_market_cap(4.90, pit.shares) == pytest.approx(490_000_000.0)
    assert not screen.mcap_floor_pass(screen.pit_market_cap(4.90, pit.shares))
    live = screen.fundamentals_from_facts(facts)
    assert screen.mcap_floor_pass(screen.pit_market_cap(4.90, live.shares))


# --- thesis-rewind-eval CONTRACT assertion 3: stratified cohort draw ---

def _survivors(n=40):
    # RS spread 90.0 .. 99.75, distinct values
    return [{"ticker": f"T{i:02d}", "rs": 90.0 + i * 0.25} for i in range(n)]


def test_a3_stratified_rs_sample_draws_five_per_quartile_deterministically():
    s = _survivors()
    a = screen.stratified_rs_sample(s, per_quartile=5, seed=7)
    b = screen.stratified_rs_sample(s, per_quartile=5, seed=7)
    assert a == b                      # same seed -> identical draw
    assert len(a) == 20
    # exactly 5 from each RS quartile of the survivor list
    ranked = sorted(s, key=lambda x: x["rs"])
    quartiles = [ {d["ticker"] for d in ranked[i*10:(i+1)*10]} for i in range(4) ]
    drawn = [d["ticker"] for d in a]
    assert [sum(t in q for t in drawn) for q in quartiles] == [5, 5, 5, 5]
    # a different seed reshuffles the within-quartile picks
    c = screen.stratified_rs_sample(s, per_quartile=5, seed=8)
    assert c != a


def test_a3_stratified_rs_sample_short_quartile_takes_all():
    s = _survivors(n=14)   # quartiles of 4/4/3/3
    out = screen.stratified_rs_sample(s, per_quartile=5, seed=1)
    assert len(out) == 14  # never invents names; under-full quartiles drain


# --- ruleout-screen fix: split-adjusted market cap ---------------------------
#
# The price feed is split-adjusted; the share count comes from the last annual
# filing and is NOT. A company that split between the filing and the as-of date
# therefore gets a market cap wrong by the split ratio. Caught live 2026-08-18:
# Booking Holdings did a 1-for-25 split on 2026-04-06, and the screen reported a
# $6.9B market cap against a real figure near $163B.


def test_pit_market_cap_applies_a_split_that_happened_after_the_filing():
    """A 25:1 split multiplies the filed share count by 25. Hand arithmetic:
    200.0 x (32,000,000 x 25) = 160,000,000,000."""
    shares = [("2025-12-31", 32_000_000.0)]
    assert screen.pit_market_cap(200.0, shares, split_factor=25.0) == 160_000_000_000.0


def test_pit_market_cap_defaults_to_no_split():
    """No split factor means the old behaviour exactly, so every existing
    caller keeps its number."""
    shares = [("2025-12-31", 100_000_000.0)]
    assert screen.pit_market_cap(25.0, shares) == 2_500_000_000.0


def test_a_reverse_split_shrinks_the_share_count():
    """A 1-for-10 reverse split carries a factor of 0.1: 50.0 x 2,000,000 =
    100,000,000. All three literals are binary-exact."""
    shares = [("2025-12-31", 20_000_000.0)]
    assert screen.pit_market_cap(50.0, shares, split_factor=0.1) == 100_000_000.0
