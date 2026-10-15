"""Centralized configuration for kairos.

Single source of truth for the research knobs: Polygon HTTP/rate-limit settings,
the regime snapshot, the forward verdict ledger, and the outbound contact string.
Do not scatter magic numbers into modules; hoist a named knob here.

Trading-side knobs (capital, guardrails, the options research books, the broker
account getter) live in `kairos.trading_config` and are re-exported below when it
is present, so `config.X` reads them unchanged. The public research snapshot does
not ship that module.

Secrets are read lazily at execution time via getters, never at import, so
modules that only import constants do not break when creds are absent. `.env` is
gitignored; never paste a secret here.
"""

from __future__ import annotations

import os

from kairos.data.polygon import RateLimiter


# -- Macro-regime snapshot (thesis-regime-v1; judge weighing context ONLY) ----
# REGIME_VIX_CRASH_PCTILE: the "vol elevated" half of the Daniel-Moskowitz
#   momentum-crash-risk flag — flag fires when SPY trailing-12m return is
#   negative AND VIXCLS sits at/above this trailing-1yr percentile. Never a
#   gate: the flag reaches the judge seat as weighing context, nothing else.
# REGIME_OAS_TREND_LOOKBACK_OBS: observations back (~1 quarter of trading
#   days) the HY OAS trend compares against; falls to the series start when
#   the window is shorter.
REGIME_VIX_CRASH_PCTILE: float = 0.8
REGIME_OAS_TREND_LOOKBACK_OBS: int = 63


# -- Forward verdict ledger (thesis-verdict-ledger) ----------------------------
# REVIEW_MOVE_TRIGGER_PCT: |close/entry - 1| at/above this flags a verdict row
#   for review, at most once per direction (up, down) over the row's lifetime.
#   Advisory only — nothing auto-closes; the ±15% magnitude is the framework's
#   event-driven review line (framework-thesis-engine.md ops cadence).
REVIEW_MOVE_TRIGGER_PCT: float = 0.15


# -- Premove cohort (cohort 2; specs/premove-cohort.md) -------------------------
# PREMOVE_NET_UP_FLOOR: extra net_up_30d floor layered ON TOP of the frozen
#   RevisionSnapshot.positive gate (which already requires net_up >= 0 and
#   delta > 0). 0 = no extra floor. The ONE AC3-adjustable knob: tightened
#   only at Jake's probe review if the cohort overshoots, never silently.
PREMOVE_NET_UP_FLOOR: int = 0


# -- Polygon HTTP timeouts + retry ceiling ------------------------------------
# Applied as connect_timeout/read_timeout/retries on the RESTClient constructor.
# Known SDK limitation (polygon-api-client ~1.16): the Timeout object is stored
# but NOT applied at the HTTP layer; the real guard against a hang is OS TCP
# keepalive + POLYGON_MAX_RETRIES. Passing explicit values is still load-bearing
# (constructor-kwarg tests assert the threading; future SDK versions may fix it).
POLYGON_REQUEST_TIMEOUT: float = 30.0
POLYGON_MAX_RETRIES: int = 3


# -- Rate limiters ------------------------------------------------------------
# STOCK aggregates are fast (Stocks Developer) -> UNDERLYING_LIMITER, ~100/1s.
# The slow options limiter lives with the options books in trading_config.
UNDERLYING_LIMITER: RateLimiter = RateLimiter(max_calls=100, per_seconds=1.0)
# Back-compat alias (older callers): the stock-path limiter.
BACKTEST_LIMITER: RateLimiter = UNDERLYING_LIMITER


# -- Outbound identity --------------------------------------------------------
# SEC EDGAR and FINRA both reject or throttle an anonymous User-Agent and ask for
# a contact address in it. Set KAIROS_CONTACT (e.g. "kairos-research you@example.com")
# in .env before running any fetch against either source.
CONTACT: str = os.environ.get("KAIROS_CONTACT", "kairos-research contact@example.com")


# -- Trading side (private; absent from the public snapshot) ------------------
try:
    from kairos.trading_config import *  # noqa: E402,F401,F403
    from kairos.trading_config import _require_env  # noqa: E402,F401
except ModuleNotFoundError as e:
    # Only the module's own absence is expected. A missing import INSIDE it is a bug.
    if e.name != "kairos.trading_config":
        raise
