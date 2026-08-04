# Data sources for TI 2026 modeling

> Note: the TI15 contest exposes no odds and no crowd percentages, so the odds/screenshot workflow
> below does not apply to it (`devig.py` / `series.py` remain generic reusable utilities). OpenDota
> is the data source used by the production pipeline.

Research snapshot 2026-08-01. Sources in [research-log.md](research-log.md).

Two things we need very different sources for: **team-strength data** (to build our own win
probabilities) and **market odds** (the calibrated benchmark, as in the football project). The
first is free and easy; the second is the hard part.

## Team / match data — for our own rating model (FREE, usable)
| Source | Access | Notes |
|--------|--------|-------|
| **OpenDota** `api.opendota.com` | **[C] Free, no key needed.** 50,000 calls/month, 60 req/min. | Best default. Endpoints: `/proMatches` (recent pro games: teams, winner, score, duration, league), `/teams`, `/teams/{id}/matches`, `/matches/{id}`. Enough to build an Elo/Glicko or logistic rating from recent pro results. Optional free API key raises limits. |
| **STRATZ** `stratz.com/api` | **[C] Free, but needs an account token** (GraphQL). | Richer parsed data + its own AI win-probabilities. Good cross-check. Respect its terms; token required. |
| **Valve Web API** | Official, needs a free WebAPI key. | Canonical match/league data; lower-level than OpenDota. |
| **Liquipedia** | Web/wiki, **blocks scrapers (403)**; has an API with strict rate limits + required User-Agent. | Great for the human-readable field/format/seeding; not for bulk pulls. |

**Plan:** pull recent pro matches from OpenDota → build a team rating → convert to single-map win
prob `p` → series/Swiss/bracket probabilities. Fetcher goes in `ti_predict/` and writes to
`data/ti2026/raw/` (see `data/README.md`). **Do not hallucinate team strength** — it must come from
a fresh OpenDota pull; the assistant's training data does not know current rosters/patch form.

## Market odds — the calibrated benchmark (HARD; no clean free source)
| Source | Cost | Usable here? |
|--------|------|--------------|
| **PandaScore**, **Abios**, Sportradar | **[C] Paid** (PandaScore ~€1,600+/mo; Abios ~$2k–10k/mo). Also **prohibit betting-related use** on stats plans. | No. |
| **OddsPapi** (claims free tier, 350+ books) | Free tier claimed | **[P] unverified** — treat with caution; validate before relying. |
| **Manual screenshots** of a bookmaker's TI match-winner / series-score lines | Free | **Recommended, mirrors the football workflow.** Transcribe into `data/ti2026/inputs/`, Shin-de-vig with `ti_predict/devig.py`. |
| **In-client win %** (if the Predictions UI shows crowd/implied probabilities) | Free | Use as the **crowd** signal for differentiation (see predictions-contest.md). |

**Bottom line:** there is **no reliable free odds API**. Realistic inputs are (1) OpenDota →
our own model, and (2) hand-entered odds/percentages from screenshots. Both feed the same
de-vig + series math.

## Licensing / hygiene
- OpenDota/STRATZ data: fine for personal analysis; don't redistribute bulk dumps.
- Never commit any paid-odds data or API tokens. Tokens go in `.env.local` (gitignored); template
  in `.env.template`.
- Raw API pulls are large/regenerable → gitignored (`data/*/raw/`, `data/*/processed/`). The small
  hand-entered inputs and our predictions are tracked (see `.gitignore`).
