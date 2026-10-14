"""Stage 1: event rule-outs read off the EDGAR submissions index.

The confirmation fixtures are verbatim excerpts of the filings that produced
the 2026-08-17 false positives (ETSY, FSLY, AMRX) and true positives (MPWR,
SLAB, ACA, RAMP), so a regression here is a regression against real EDGAR text.
"""

from __future__ import annotations

from kairos import events as ev


def _subs(rows):
    """A submissions index shaped like data.sec.gov/submissions: parallel
    arrays of form, filingDate and items."""
    return {"filings": {"recent": {
        "form": [r[0] for r in rows],
        "filingDate": [r[1] for r in rows],
        "items": [r[2] for r in rows]}}}


AS_OF = "2026-08-17"


# --- the scan ---

def test_a_non_reliance_item_is_flagged():
    hit = ev.scan(_subs([("8-K", "2026-02-27", "4.02,9.01")]), as_of=AS_OF)
    assert hit is not None
    assert hit.form == "8-K" and hit.item == "4.02" and hit.filed == "2026-02-27"


def test_a_bankruptcy_item_is_flagged():
    hit = ev.scan(_subs([("8-K", "2026-01-05", "1.03")]), as_of=AS_OF)
    assert hit is not None and hit.item == "1.03"


def test_an_ordinary_earnings_release_is_not_flagged():
    assert ev.scan(_subs([("8-K", "2026-08-04", "2.02,9.01"),
                          ("8-K", "2026-04-02", "5.02")]), as_of=AS_OF) is None


def test_a_merger_proxy_is_flagged_by_its_form():
    hit = ev.scan(_subs([("DEFM14A", "2026-07-06", "")]), as_of=AS_OF)
    assert hit is not None and hit.form == "DEFM14A" and hit.item is None


def test_a_filing_after_the_as_of_date_is_invisible():
    assert ev.scan(_subs([("8-K", "2026-08-18", "4.02")]), as_of=AS_OF) is None


def test_a_filing_older_than_the_window_is_invisible():
    assert ev.scan(_subs([("8-K", "2025-08-16", "4.02")]),
                   as_of=AS_OF, window_days=365) is None
    assert ev.scan(_subs([("8-K", "2025-08-18", "4.02")]),
                   as_of=AS_OF, window_days=365) is not None


def test_the_newest_event_wins_when_a_filer_has_several():
    hit = ev.scan(_subs([("8-K", "2026-06-01", "3.01"),
                         ("8-K", "2026-01-02", "4.02")]), as_of=AS_OF)
    assert hit.filed == "2026-06-01" and hit.item == "3.01"


def test_every_8k_item_needs_confirmation():
    """A filer types its own item codes and can type them wrong: GVA's
    2026-02-18 index says item 1.03 over a convertible note exchange."""
    for item in ("1.03", "3.01", "4.02"):
        assert ev.scan(_subs([("8-K", "2026-06-01", item)]),
                       as_of=AS_OF).needs_confirmation is True


def test_a_merger_proxy_needs_confirmation_and_a_tender_offer_does_not():
    assert ev.scan(_subs([("DEFM14A", "2026-07-06", "")]),
                   as_of=AS_OF).needs_confirmation is True
    assert ev.scan(_subs([("SC 14D9", "2026-07-06", "")]),
                   as_of=AS_OF).needs_confirmation is False


# --- confirmation: item 3.01 also covers a voluntary exchange transfer ---

_ETSY = ("Item 3.01 Notice of Delisting or Failure to Satisfy a Continued "
         "Listing Rule or Standard; Transfer of Listing. On September 29, "
         "2025 Etsy, Inc., acting pursuant to authorization from its Board of "
         "Directors, determined to voluntarily withdraw the principal listing "
         "of Etsy's common stock from the Nasdaq Global Select Market and "
         "transfer the listing to the New York Stock Exchange.")

_FSLY = ("Item 3.01. Notice of Delisting or Failure to Satisfy a Continued "
         "Listing Rule or Standard; Transfer of Listing. On November 26, "
         "2025, Fastly, Inc. provided notice to the New York Stock Exchange "
         "that it intends to voluntarily withdraw the listing of its Class A "
         "common stock from the NYSE and transfer the listing of its common "
         "stock to the Nasdaq Stock Market LLC.")

_REAL_DELISTING = ("Item 3.01 Notice of Delisting or Failure to Satisfy a "
                   "Continued Listing Rule or Standard. On March 3, 2026, the "
                   "Company received a written notice from the Listing "
                   "Qualifications Department of Nasdaq stating that the "
                   "Company is not in compliance with the minimum bid price "
                   "requirement set forth in Listing Rule 5450(a)(1).")


def test_a_voluntary_exchange_transfer_is_not_a_delisting():
    assert ev.confirms_involuntary_delisting(_ETSY) is False
    assert ev.confirms_involuntary_delisting(_FSLY) is False


def test_a_listing_deficiency_notice_is_a_delisting():
    assert ev.confirms_involuntary_delisting(_REAL_DELISTING) is True


# --- confirmation: an ACQUIRER also files a DEFM14A ---

_SLAB = ("At the Special Meeting you will be asked to consider and vote upon "
         "a proposal to adopt the Agreement and Plan of Merger, dated as of "
         "February 4, 2026, by and among Silicon Labs, Texas Instruments "
         "Incorporated and Caldwell Merger Corp., a wholly owned direct "
         "subsidiary of Texas Instruments. Pursuant to the Merger Agreement, "
         "Merger Sub will merge with and into Silicon Labs, with Silicon Labs "
         "surviving as a wholly owned direct subsidiary of Texas Instruments.")

_ACA = ("On June 21, 2026, the Company entered into an Agreement and Plan of "
        "Merger with CRH Americas, Inc. and Neon Merger Sub, Inc., providing "
        "for the acquisition of the Company by Parent. Subject to the terms "
        "of the merger agreement, merger sub will be merged with and into the "
        "Company, with the Company surviving the merger as a wholly owned "
        "subsidiary of Parent.")

_RAMP = ("On May 16, 2026, LiveRamp Holdings, Inc. entered into an Agreement "
         "and Plan of Merger by and among LiveRamp, MMS USA Holdings, Inc. "
         "and Covey Merger Sub, Inc., pursuant to which LiveRamp will be "
         "acquired by Parent.")

_AMRX = ("On April 21, 2026, Amneal entered into a Membership Interest "
         "Purchase Agreement with Kashiv BioSciences, LLC. Subject to the "
         "terms and conditions of the purchase agreement, Amneal has agreed "
         "to purchase, and the sellers have agreed to sell, 100% of the "
         "issued and outstanding membership interests of Kashiv.")


def test_a_proxy_for_the_registrants_own_sale_is_a_rule_out():
    assert ev.confirms_target_side_merger(_SLAB) is True
    assert ev.confirms_target_side_merger(_ACA) is True
    assert ev.confirms_target_side_merger(_RAMP) is True


def test_a_proxy_for_a_purchase_the_registrant_is_making_is_not_a_rule_out():
    assert ev.confirms_target_side_merger(_AMRX) is False


# --- confirmation: the index's item code must appear in the filing itself ---

_GVA = ("Item 1.01 Entry into a Material Definitive Agreement. Exchange "
        "Agreements On February 18, 2026, Granite Construction Incorporated "
        "entered into separate and privately negotiated agreements with a "
        "limited number of holders of the Company's outstanding 3.75% "
        "Convertible Senior Notes due 2028. Item 1.02 Termination of a "
        "Material Definitive Agreement. Item 3.02 Unregistered Sales of "
        "Equity Securities. Item 9.01 Financial Statements and Exhibits.")

_REAL_BANKRUPTCY = ("Item 1.03 Bankruptcy or Receivership. On March 2, 2026, "
                    "the Company filed a voluntary petition for relief under "
                    "Chapter 11 of the United States Bankruptcy Code in the "
                    "United States Bankruptcy Court for the District of "
                    "Delaware.")

_AXON = ("Item 2.02 Results of Operations and Financial Condition. Item 4.02 "
         "Non-Reliance on Previously Issued Financial Statements. On May 5, "
         "2025, the Audit Committee concluded that the previously issued "
         "financial statements for the Affected Periods should no longer be "
         "relied upon.")


def _hit(item):
    return ev.scan(_subs([("8-K", "2026-06-01", item)]), as_of=AS_OF)


def test_an_item_code_the_filing_does_not_carry_is_a_filer_typo():
    assert ev.confirms(_hit("1.03"), _GVA) is False


def test_a_filing_that_carries_its_item_code_is_confirmed():
    assert ev.confirms(_hit("1.03"), _REAL_BANKRUPTCY) is True
    assert ev.confirms(_hit("4.02"), _AXON) is True


def test_a_listing_item_still_answers_the_voluntary_test():
    assert ev.confirms(_hit("3.01"), _ETSY) is False
    assert ev.confirms(_hit("3.01"), _REAL_DELISTING) is True


def test_a_merger_proxy_confirms_on_the_target_side_test():
    proxy = ev.scan(_subs([("DEFM14A", "2026-07-06", "")]), as_of=AS_OF)
    assert ev.confirms(proxy, _ACA) is True
    assert ev.confirms(proxy, _AMRX) is False
