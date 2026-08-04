# Research log — TI 2026 prediction project

> Dated research log. For the current authoritative state see `README.md`,
> `docs/contest-official-ti15.md` and `docs/validation-plan-v2.md`.

Provenance for the synthesized docs. Each entry: date, what was checked, source URLs. Synthesis
lives in the topic docs; this file is the citation trail.

## 2026-08-01 — initial scoping (web research)

**Event, schedule, format, field** (→ [ti2026-format-and-field.md](ti2026-format-and-field.md))
- Shanghai / Oriental Sports Center; group stage 08-13→16 (Swiss, Bo3), main event 08-20→23:
  - https://www.gosugamers.net/dota2/tournaments/62969-the-international-2026
  - https://boostmatch.gg/blog/esports/articles/ti-2026-dota-international-shanghai-guide
  - https://liquipedia.net/dota2/The_International/2026 (403 to fetch; via search snippet)
  - https://www.dota2protips.com/tournaments/the-international-2026  (16-team list + advancement)
  - https://www.hotspawn.com/dota2/news/the-international-2026-group-stage-predictions-heres-what-we-picked
- 16 teams (7 invite / 9 qualifier) enumerated from dota2protips.
- Advancement (top-3 direct / 4–13 elimination / 14–16 out; 8-team main event) — dota2protips,
  hotspawn, gosugamers.
- Prior-year anchor TI 2025 (Falcons 3–2 Xtreme Gaming, Hamburg, double-elim Bo3 + Bo5 GF):
  - https://en.wikipedia.org/wiki/The_International_2025
  - https://liquipedia.net/dota2/The_International/2025/Main_Event (via search snippet)

**Predictions contest** (→ [predictions-contest.md](predictions-contest.md))
- Free (no compendium wall), covers Swiss + bracket, global leaderboard, tiered rewards, lock
  08-13 10:00 CST; Tyrian Regalia / Terrain Token / Dota Plus; 1000 pts → 300 shards:
  - https://patchbot.io/games/dota-2/articles/993-the-international-predictions-fantasy-and-supporter-bundles (Valve blog mirror)
  - https://changelog.gg/games/dota-2/updates/2026-07-30-the-international-predictions-fantasy-and-supporter-bundles-c14429b06a7c2422
  - https://www.hotspawn.com/dota2/news/the-international-2026-compendium
  - https://vgtimes.com/gaming-news/162669-valve-releases-the-international-2026-compendium-for-dota-2-completely-revamps-fantasy-league.html
  - https://teamplay.gg/blog/dota-2-international-compendium-rewards
- **Not found on web:** exact per-question points; exact reward percentile thresholds (the literal
  "top 5%"). These are in-client only → need the client's screenshots. Liquipedia Rewards page
  (https://liquipedia.net/dota2/The_International_2026_Rewards) 403s to automated fetch.

**Data sources** (→ [data-sources.md](data-sources.md))
- OpenDota free, no key, 50k/mo + 60/min:
  - https://www.opendota.com/api-keys ; https://docs.opendota.com/ ; https://blog.opendota.com/2018/04/17/changes-to-the-api/
- STRATZ free w/ token (GraphQL): https://stratz.com/api ; https://stratz.com/knowledge-base/API
- Odds APIs paid + betting-use restrictions (PandaScore/Abios); OddsPapi free-tier claim unverified:
  - https://www.pandascore.co/pricing ; https://www.pandascore.co/odds
  - https://oddspapi.io/blog/pandascore-api-alternative-free-esports-odds/

## 2026-08-01 — reconciliation against the official blog (corrections)

Trigger: a relayed transcription of the official CN post surfaced apparent conflicts with the
first-pass field list. Verified against the official article + media; the "conflicts" were TI
gambling-brand renames, and the first-pass list (from a fan aggregator) had two real errors.

- **Official source (primary):**
  https://www.dota2.com.cn/article/details/20260731/220508.html — "欢迎来到上海！2026年国际邀请赛
  捆绑包与赛事预测上线" (2026-07-31). Fetched: 16-team list, 5-round Swiss (4W direct / 4L out /
  10 → special elim 5-5), top-100 reward = all 5 Immortals + 12mo Dota Plus + Terrain Token + 100%
  physical Aegis; per-question points and full tier ladder = not stated in the blog (in-client only).
- **Corroboration (team list + renames):**
  - https://egamersworld.com/dota2/news/35790/the-international-2026-all-participating-teams-p3Fem02Xs
  - https://dotesports.com/dota-2/news/dota-2-ti-2026-teams
  - https://www.gosugamers.net/dota2/news/78704-here-are-all-the-international-2026-qualifier-winners
  - https://escharts.com/news/team-falcons-xtreme-gaming-and-team-liquid-headline-international-2026-direct-invites
- **Corrections applied** to ti2026-format-and-field.md + teams.csv:
  - Swiss threshold **3W/3L → 4W/4L over 5 rounds** (was a wrong web snippet).
  - Direct invite **"1win" → Tundra Esports** (fan-site error).
  - EU qualifier **"L1GA TEAM" → HULIGANI**.
  - **BetBoom → "BoomBoys"** and **PARIVISION → "Team Vision"** are TI aliases (same orgs), not
    different teams — this explained the apparent conflict in the relayed list.
- **Correction to the reward premise:** the official has **no "top 5%" tier**; the full-set
  threshold is **top 100 (absolute rank)**. predictions-contest.md updated with a reality-check.

## Reliability notes
- Liquipedia + escorenews block automated fetch (403); facts above are cross-checked across ≥2
  independent renderable sources where possible.
- Some result-tracker domains (ti2026-ph.*) are SEO/affiliate sites — **not** used as primary
  sources; ignore unless corroborated.
- Re-verify all **[TBD]** items against the official Dota 2 client / Valve blog and the Liquipedia
  bracket once the draw and main-event format are posted.
