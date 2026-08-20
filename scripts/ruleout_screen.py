"""The rule-out screen and stage 1, across several months, filings cached.

The screen of record is docs/ruleout-screen-2026-08.md. Rules 1-4 and the
trimming floors run inline here; rules 5rev/6/7/8 live in kairos.ruleout and
stage 1's event rule-outs in kairos.events.

Funnel: whole market -> trimming floors -> rule-outs -> stage 1 events.
Measured 2026-08-17: 768 top-third -> 342 screened -> 336 survivors.

Filings are fetched once per ticker for the whole run. The same companies
recur every month, so the second month onward is nearly free.

Usage: code/.venv/bin/python scripts/ruleout_screen.py <date> [more dates] [--out PATH]
"""
import datetime as dt, json, re, sys, time
sys.path.insert(0, "code/src"); sys.path.insert(0, "scripts")
from collections import Counter
from kairos import events, ruleout, screen
from kairos.data import edgar
import weekly_screen as ws

RS_FLOOR, DILUTION_MAX = 67.0, 0.20
# `--out` so a ten-cohort rewind writes ten files. The old fixed path meant
# every cohort after the first silently overwrote the one before it.
_argv = sys.argv[1:]
if "--out" in _argv:
    _i = _argv.index("--out")
    OUT_PATH = _argv[_i + 1]
    _argv = _argv[:_i] + _argv[_i + 2:]
    DATES = _argv
else:
    DATES = _argv
    OUT_PATH = f"data/ruleout-{DATES[0]}.json" if DATES else None

_facts, _subs = {}, {}
def facts_for(t):
    if t not in _facts:
        try: _facts[t] = edgar.fetch_companyfacts(t)
        except Exception: _facts[t] = None
    return _facts[t]

def subs_for(t):
    if t not in _subs:
        try: _subs[t] = edgar.fetch_submissions(t)
        except Exception: _subs[t] = None
    return _subs[t]

def series(f, tags, lte):
    if f is None: return None
    try: return edgar.annual_series(f, tags, filed_lte=lte)
    except Exception: return None

def g(s):
    if not s or len(s) < 2: return None
    p, l = s[-2][1], s[-1][1]
    return None if not p else (l - p) / abs(p)

def confirm(t, hit, as_of):
    """Pull the flagged filing's own text and hand it to events.confirms."""
    for f in edgar.recent_filings(subs_for(t), forms=(hit.form,), limit=80,
                                  filed_lte=as_of):
        if f.filed != hit.filed: continue
        text = re.sub(r"\s+", " ", edgar.strip_filing_html(
            edgar.fetch_filing_text(f.url)))
        return events.confirms(hit, text)
    return False

out = {}
for d in DATES:
    AS_OF = dt.date.fromisoformat(d); lte = d
    t0 = time.time()
    bars = ws.build_bars(AS_OF)
    field, pct = screen._ranked_field(bars)
    floors = {t: b for t, b in field.items() if screen.admission_eligible(b)}
    short = sorted(((t, pct[t]) for t in floors if pct.get(t) is not None
                    and pct[t] >= RS_FLOOR), key=lambda x: -x[1])
    rows, cuts = [], {}
    for t, rs_pct in short:
        f = facts_for(t)
        if f is None: cuts[t] = "no filings"; continue
        rev = series(f, edgar.REVENUE_TAGS, lte)
        shares = series(f, edgar.SHARES_TAGS, lte)
        if not rev or rev[-1][1] <= 0: cuts[t] = "no revenue"; continue
        if not shares: cuts[t] = "no share count"; continue
        mcap = screen.pit_market_cap(bars[t].price, shares)
        if mcap is None or mcap < screen._MCAP_FLOOR:
            cuts[t] = "too small"; continue
        rg = g(rev)
        if rg is None or rg <= 0: cuts[t] = "revenue not growing"; continue
        ocf = series(f, edgar.OPERATING_CASH_FLOW_TAGS, lte)
        if not ocf or ocf[-1][1] <= 0: cuts[t] = "does not fund itself"; continue
        dil = g(shares)
        if dil is not None and dil > DILUTION_MAX:
            cuts[t] = "share count exploding"; continue
        if not ruleout.revenue_base_ok(rev):
            cuts[t] = "revenue base too small"; continue

        sb = subs_for(t)
        sic = int(sb.get("sic") or 0) if sb else 0
        cik = int(sb["cik"]) if sb else None
        if ruleout.is_exogenous_sector(sic):
            cuts[t] = "exogenous sector"; continue

        ni_g = g(series(f, edgar.NET_INCOME_TAGS, lte))
        if ruleout.is_financial(sic):
            bvps = ruleout.book_value_per_share(
                series(f, edgar.EQUITY_TAGS, lte) or [],
                series(f, edgar.SHARES_TAGS, lte) or [])
            if not ruleout.financial_compounding(ni_g, g(bvps)):
                cuts[t] = "financial not compounding"; continue
        elif ruleout.nonfinancial_collapsing(
                ni_g, g(series(f, edgar.CAPEX_TAGS, lte)),
                g(series(f, edgar.RESEARCH_TAGS, lte))):
            cuts[t] = "deteriorating, not investing"; continue

        # The dossier compiler reads price, technicals and forensics too.
        # Emitting only the gate's own fields failed 25 of 25 compiles on
        # KeyError 'price'. screen.dossier_row owns the shape.
        rows.append(screen.dossier_row(
            ticker=t, cik=cik, sic=sic, rs=round(rs_pct, 1),
            rev_growth=round(rg, 3), market_cap=mcap, bars=field[t],
            series={"revenue": series(f, edgar.REVENUE_TAGS, lte),
                    "receivables": series(f, edgar.RECEIVABLES_TAGS, lte),
                    "net_income": series(f, edgar.NET_INCOME_TAGS, lte),
                    "operating_cash_flow": series(
                        f, edgar.OPERATING_CASH_FLOW_TAGS, lte),
                    "shares": series(f, edgar.SHARES_TAGS, lte)}))

    by_ticker = {r["ticker"]: r for r in rows}
    kept = ruleout.first_per_filer([(r["ticker"], r["cik"]) for r in rows])
    for t in by_ticker.keys() - set(kept):
        cuts[t] = "duplicate filer"
    screened = len(kept)

    survivors, stage1 = [], {}
    for t in kept:
        hit = events.scan(subs_for(t), as_of=d)
        if hit and (not hit.needs_confirmation or confirm(t, hit, d)):
            stage1[t] = f"{hit.reason} ({hit.form} {hit.item or ''} {hit.filed})"
            continue
        survivors.append(by_ticker[t])

    out[d] = {"stages": {"history": len(bars), "field": len(field),
                         "floors": len(floors), "top_third": len(short),
                         "screened": screened, "survivors": len(survivors)},
              "cuts": dict(Counter(cuts.values())), "stage1_cuts": stage1,
              "survivors": survivors}
    print(f"{d}: top-third {len(short):4d} -> screened {screened:4d} "
          f"-> survivors {len(survivors):4d} ({time.time()-t0:.0f}s, "
          f"{len(_facts)} filings cached)", flush=True)

json.dump(out, open(OUT_PATH, "w"), indent=1)
