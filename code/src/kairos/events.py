"""Stage 1 of the agent cascade: event rule-outs read off EDGAR.

Between a company's last annual filing and today, an event can break the
picture those numbers paint. Three do it in a way no story rescues: the
company is being bought, its listing is being pulled, or it has told the SEC
its own prior statements are wrong. All three are visible as a form type or
an 8-K item code in the submissions index, so stage 1 is mechanical and
point-in-time rather than an agent read (Jake, 2026-08-18).

Two of the three signals over-fire and need the filing text to confirm:

- A filer types its own item codes into the index and can type them wrong.
  GVA's 2026-02-18 index reports item 1.03, bankruptcy, over a convertible
  note exchange. So every 8-K hit is confirmed against the filing body.
- 8-K item 3.01 covers "Transfer of Listing" as well as delisting, so a
  company voluntarily moving between Nasdaq and the NYSE files the same item
  as one served a deficiency notice. ETSY and FSLY were cut this way.
- A DEFM14A is filed by an ACQUIRER seeking a vote on a purchase as well as
  by a target seeking a vote on its own sale. AMRX was cut this way while
  buying Kashiv BioSciences.

SC 14D9 is filed only by a tender offer's target, so it alone needs no
confirmation.

Measured over four months to 2026-08-17: the scan flagged 19 names and the
confirmation pass rejected 4 of them.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 8-K item codes that break the picture the filed numbers paint.
EVENT_8K_ITEMS: dict[str, str] = {
    "1.03": "bankruptcy or receivership",
    "3.01": "delisting or listing-rule failure",
    "4.02": "prior financial statements not reliable",
}

# Target-side forms. SC 14D9 is filed only by a tender offer's target, so it
# needs no confirmation; DEFM14A does.
EVENT_FORMS: dict[str, str] = {
    "SC 14D9": "tender-offer recommendation",
    "DEFM14A": "definitive merger proxy",
}

# An event older than this no longer describes the company the panel would
# buy: a listing deficiency gets cured, a restatement gets filed.
EVENT_WINDOW_DAYS = 365

# The only signal the index alone can be trusted on.
_TRUSTED_FORMS = {"SC 14D9"}

# How much of the filing after an item heading carries that item's report.
_ITEM_WINDOW = 2500

_INVOLUNTARY = re.compile(
    r"received (?:a |an )?(?:written )?(?:notice|notification|letter)"
    r"|not in compliance|non-?compliance|deficiency"
    r"|fail(?:ure|ed|s) to (?:satisfy|comply)|minimum bid price"
    r"|delisting determination|staff determination",
    re.IGNORECASE)

_VOLUNTARY = re.compile(
    r"voluntarily withdraw|transfer (?:the|its) listing"
    r"|intends to (?:voluntarily )?withdraw",
    re.IGNORECASE)

_TARGET_SIDE = re.compile(
    r"acquisition of (?:the Company|us|[A-Z][\w.,& ]{2,40}?) by"
    r"|will be acquired by"
    r"|(?:merge|merged) with and into (?:the Company|us|[A-Z][\w.,& ]{2,40}?),"
    r"|with (?:the Company|[A-Z][\w.,& ]{2,40}?) surviving"
    r" (?:the merger )?as a wholly[- ]owned",
    re.IGNORECASE)


@dataclass(frozen=True)
class EventHit:
    """One event rule-out candidate. `item` is None for a form-typed hit."""
    form: str
    item: str | None
    filed: str
    reason: str
    needs_confirmation: bool


def scan(submissions: dict, *, as_of: str,
         window_days: int = EVENT_WINDOW_DAYS) -> EventHit | None:
    """The newest event in [as_of - window_days, as_of], or None.

    `submissions` is a data.sec.gov/submissions index. Filings after `as_of`
    are dropped before anything else, so a rewind sees only what existed
    then. The recent block is newest-first, so the first match is the newest.
    """
    recent = submissions["filings"]["recent"]
    floor = (dt.date.fromisoformat(as_of)
             - dt.timedelta(days=window_days)).isoformat()
    for form, filed, items in zip(recent["form"], recent["filingDate"],
                                  recent["items"]):
        if filed > as_of or filed < floor:
            continue
        if form in EVENT_FORMS:
            return EventHit(form=form, item=None, filed=filed,
                            reason=EVENT_FORMS[form],
                            needs_confirmation=form not in _TRUSTED_FORMS)
        if form != "8-K" or not items:
            continue
        for code in (c.strip() for c in items.split(",")):
            if code in EVENT_8K_ITEMS:
                return EventHit(form=form, item=code, filed=filed,
                                reason=EVENT_8K_ITEMS[code],
                                needs_confirmation=True)
    return None


def confirms(hit: EventHit, text: str) -> bool:
    """Whether the flagged filing's own text supports the rule-out. `text` is
    the filing body, tag-stripped and whitespace-collapsed. An unconfirmed
    hit is never a rule-out, because a rule-out fires on a fact and a wrong
    item code is not one."""
    if hit.form != "8-K":
        return confirms_target_side_merger(text)
    start = text.find(f"Item {hit.item}")
    if start < 0:
        logger.info("confirms: %s %s absent from the filing body",
                    hit.form, hit.item)
        return False
    if hit.item == "3.01":
        return confirms_involuntary_delisting(text[start:start + _ITEM_WINDOW])
    return True


def confirms_involuntary_delisting(text: str) -> bool:
    """True when an item 3.01 filing reports a listing the company is losing,
    False when it reports a listing the company is moving. A filing that
    names a voluntary withdrawal is never a rule-out even if it also quotes
    the item's boilerplate title, so the voluntary read wins."""
    if _VOLUNTARY.search(text):
        return False
    return bool(_INVOLUNTARY.search(text))


def confirms_target_side_merger(text: str) -> bool:
    """True when a merger proxy asks the registrant's own holders to approve
    the registrant's sale. False when it asks them to approve a purchase the
    registrant is making, which leaves the company standing and the panel's
    thesis intact."""
    return bool(_TARGET_SIDE.search(text))
