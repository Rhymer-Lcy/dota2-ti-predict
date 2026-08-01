# TI 2026 Predictions contest — mechanics, scoring, rewards

Research snapshot 2026-08-01, reconciled against the official Dota 2 blog (2026-07-31). Tags
**[C]** confirmed / **[P]** probable / **[TBD]** client-only or unpublished. Sources in
[research-log.md](research-log.md). In-game proper nouns are given English (Chinese) so they can be
matched against a CN client.

Skill-based prediction for **cosmetic rewards — not gambling** (no stake, no money at risk).

## Two separate free activities, both leaderboard-scored
- **[C] Predictions (赛事预测)** — predict tournament outcomes; the friend's target.
- **[C] Fantasy (梦幻挑战)** — draft pro players for fantasy points; a **separate** contest with its
  own scoring. New this year: a **Coach** customization; you pick **1 core + 1 mid + 1 support, each
  from a different team**, with reroll tokens. (Noted for completeness; not the current focus.)

Both feed points → **global-leaderboard rank → tiered rewards**. Free for everyone (no compendium
paywall this year).

## What you predict — [C] scope, [TBD] exact wording/points
- **[C]** Predictions cover the **5-round Swiss group stage** AND the **special elimination + main
  bracket**.
- **[C]** Group-stage picks **lock 2026-08-13 10:00 CST**. Bracket picks lock later **[TBD]** (once
  the 8 main-event teams are set).
- **[C]** Official notes **no one has ever correctly predicted the entire Swiss stage** — the tail
  is brutal (see reality check).
- **[TBD]** The exact question list and **per-question point values** are **only in the in-client
  Predictions/Rewards menu** — the blog does not enumerate them. Likely families: which teams go
  4-win-direct / 4-loss-out / into special elimination; special-elimination winners; bracket
  winners per round; champion. Novelty/stat questions **[TBD]** — confirm in client.

## Rewards — [C] top tier; [TBD] full ladder
- **[C] Top tier = final rank in the top 100:** all **5 Tyrian Regalia Immortals (云紫上品)** +
  **12 months Dota Plus** + **1 Terrain Token** + **100% off the physical Aegis**.
- **[C] Terrain Token** picks 1 of 6 terrains: Sanctums of the Divine (神之圣地), Overgrown Empire
  (蔓生国度), The Emerald Abyss (玉海之渊), Reef's Edge (礁石之界), Desert Terrain (黄沙大漠),
  Immortal Gardens (不朽庭院).
- **[C] Participation:** Aegis chat emoticon, TI wallpapers, team wallpapers; **every 1,000 points
  → 300 Dota Plus Shards**, regardless of rank.
- **[TBD] The full tier ladder** (what ranks/percentiles below top-100 receive) and **per-question
  points** are **in-client only** — need a screenshot of the in-game Rewards section.

## ⚠️ Reality check on "top 5% / get everything" — corrected
- **The official text has NO "top 5%" tier.** The "get everything" threshold is **top 100 of the
  global rank** — an absolute count, not a percentile.
- TI Predictions draws **millions** of players, so **top 100 is a near-lottery at the extreme tail**:
  it effectively needs an almost-perfect Swiss + bracket, and the official itself says nobody has
  ever nailed the full Swiss. **A model can raise expected score and percentile, but it cannot
  realistically deliver a top-100 finish** — variance dominates that far out.
- So "top 5% gets all" is either a misremembering or refers to a **lower reward tier**. What that
  tier actually gives is unknown until we see the in-client ladder.
- **Honest goal-setting:** maximize **expected points / the best *reachable* tier**, and read the
  ladder first to learn which tier is realistic. Do not promise top-100.

## Strategy (once the ladder + points are known)
- If the reachable target is a **hard rank/percentile cutoff**, maximize **P(clearing it)**, not raw
  accuracy — pure chalk lands near the median. Clearing a cutoff usually needs **mostly-favourites
  (chalk) + a few high-conviction contrarian calls** where our probability beats the **crowd's pick
  %**. The edge is against biased human pickers, not against the betting market.
- If it is a **continuous ranking**, lean to per-question EV-max (chalk).
- **Blocking inputs (screenshots):** (1) every question + point value; (2) the full Rewards tier
  ladder; (3) public pick % per option, if shown; (4) the Swiss draw once posted.
