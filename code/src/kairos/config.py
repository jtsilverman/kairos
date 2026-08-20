"""Centralized configuration for the kairos research pipeline.

Single source of truth for every knob the screen and the thesis engine read.
Do not scatter magic numbers into modules; hoist a named knob here.

No secret belongs in this file. API keys are read from the environment at call
time, never at import, so a module that only imports constants still loads when
credentials are absent.
"""

from __future__ import annotations

import os

from kairos.data.polygon import RateLimiter


# -- Market regime ------------------------------------------------------------
# REGIME_VIX_CRASH_PCTILE: the VIX percentile above which the regime reads as a
#   crash tape.
# REGIME_OAS_TREND_LOOKBACK_OBS: observations back (~1 quarter of trading days)
#   the high-yield OAS trend compares against; falls to the series start when the
#   window is shorter.
REGIME_VIX_CRASH_PCTILE: float = 0.8
REGIME_OAS_TREND_LOOKBACK_OBS: int = 63


# -- Thesis review cadence ----------------------------------------------------
# REVIEW_MOVE_TRIGGER_PCT: the move that flags an open thesis for review, at most
#   once per direction over the row's lifetime. Advisory only; nothing closes
#   automatically. See docs/framework-thesis-engine.md, ops cadence.
REVIEW_MOVE_TRIGGER_PCT: float = 0.15


# -- Polygon HTTP -------------------------------------------------------------
# The SDK accepts a timeout but does not apply it at the HTTP layer, so the real
# guard against a hang is OS TCP keepalive plus POLYGON_MAX_RETRIES. Passing the
# explicit values is still load-bearing; constructor-kwarg tests assert it.
POLYGON_REQUEST_TIMEOUT: float = 30.0
POLYGON_MAX_RETRIES: int = 3

UNDERLYING_LIMITER: RateLimiter = RateLimiter(max_calls=100, per_seconds=1.0)


# -- Outbound identity --------------------------------------------------------
# SEC EDGAR and FINRA both reject or throttle an anonymous User-Agent and ask for
# a contact address in it. Set KAIROS_CONTACT to your own before running any
# fetch against either source.
CONTACT: str = os.environ.get("KAIROS_CONTACT", "kairos-research contact@example.com")
