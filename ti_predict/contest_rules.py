"""Frozen TI15 contest constants: the single source of truth.

Every value here is one of: an OFFICIAL contest rule, a frozen production decision, or a verified
operational reference (the graded lock-time estimate GROUP_LOCK_UTC and the official league feed
LEAGUE_FEED_URL) - never a tunable parameter. Sourced from the in-client TI15 activity and
cross-checked against public coverage; each entry's evidence grading is in its own comment; see
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

# Group-stage prediction lock. Evidence (re-verified 2026-08-09, tiered):
# - Tier 1 wording: Valve blog 2026-07-31 (dota2.com/newsentry/678505520073540063): guesses must be
#   in "before the first match starts (10am CST, Thursday 8/13)" - lock == first match by Valve's
#   own construction.
# - Tier 1 timezone convention: Valve's TI2026 ticket post uses CST = China Standard Time
#   ("2pm China Standard Time ... From 2:30pm (CST)"), so 10:00 UTC+8 = 02:00 UTC. The circulating
#   15:00 GMT figure is a US-Central misparse of the same sentence (would be 23:00 in Shanghai).
# - Consistent with the in-client "9 days" countdown observed 2026-08-03 and with TI2025's
#   10:00-local day-1 start.
# Caveats: Valve has not spelled the timezone unambiguously for this specific sentence; the Chinese
# localization omits it; the league feed (league_id 19719) carries no per-match times yet. The
# in-client countdown is the FINAL authority; the official pipeline never defaults to this value -
# it requires an explicit timezone-aware --cutoff.
GROUP_LOCK_UTC = "2026-08-13T02:00:00Z"

# Machine-readable official schedule source (the data behind the game client). Poll for the draw:
# round-1 nodes gain team ids + scheduled_time once published. League window opens 2026-08-12 00:00
# UTC; TI2025's round-1 pairings were published about 47 hours before its first match.
LEAGUE_FEED_URL = ("https://www.dota2.com/webapi/IDOTA2League/GetLeagueData/v001/?league_id=19719")

# Total base prize pool (USD).
PRIZE_POOL_USD = 1_600_000
