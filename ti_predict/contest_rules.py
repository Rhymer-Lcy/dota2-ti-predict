"""Frozen official TI15 contest constants: the single source of truth.

Every value here is an OFFICIAL rule or a frozen production decision, not a tunable parameter. Sourced
from the in-client TI15 activity and cross-checked against public coverage; see
docs/contest-official-ti15.md and docs/validation-plan-v2.md. Import these instead of hard-coding.
"""

# Group-stage prediction: the six record buckets and how many teams fill each (16 total).
BUCKETS = ("4-0", "4-1", "decider_win", "decider_loss", "1-4", "0-4")
CAPACITY = {"4-0": 1, "4-1": 2, "decider_win": 5, "decider_loss": 5, "1-4": 2, "0-4": 1}

# Group-stage scoring: activity points by number of correct slots. Convex; no wrong-answer penalty,
# no underdog weighting, no crowd/odds weighting (docs/contest-official-ti15.md sec 3).
GROUP_SCORE = {0: 0, 1: 30, 2: 60, 3: 120, 4: 360, 5: 720, 6: 1200, 7: 1800, 8: 2520, 9: 3360,
               10: 4320, 11: 5400, 12: 6600, 13: 7920, 14: 9360, 15: 10920, 16: 12000}

# Main-event prediction scoring: points by number of correct series (14 series to the champion).
# Kept for the deferred main-event track (docs/contest-official-ti15.md sec 7).
MAIN_EVENT_SCORE = {0: 0, 1: 120, 2: 360, 3: 720, 4: 1200, 5: 1800, 6: 2520, 7: 3360, 8: 4320,
                    9: 5400, 10: 6600, 11: 7920, 12: 9360, 13: 10920, 14: 12000}

# Production model freeze: Bradley-Terry time-decay half-life in days. Validated as the frozen choice;
# a longer half-life was not a significant out-of-sample improvement (docs/validation-plan-v2.md).
PRODUCTION_HALF_LIFE_DAYS = 90

# Official-run data-freshness guard: reject an official run whose latest universe map is older than
# this many days before the cutoff (unless explicitly overridden).
STALE_MAX_DAYS = 3

# Group-stage prediction lock: best external estimate; confirm the in-client countdown before use.
GROUP_LOCK_UTC = "2026-08-13T15:00:00Z"

# Total base prize pool (USD).
PRIZE_POOL_USD = 1_600_000
