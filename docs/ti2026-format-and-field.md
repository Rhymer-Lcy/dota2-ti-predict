# The International 2026 — format & field

Research snapshot 2026-08-01, **reconciled against the official Dota 2 blog (2026-07-31)** plus
media corroboration. Tags: **[C]** confirmed (official + ≥1 source); **[P]** probable (precedent);
**[TBD]** not yet public. Sources in [research-log.md](research-log.md).

## Event
- **[C]** The International 2026 (TI 2026 / "TI15"), 15th edition, **Shanghai, China**. Main-event
  venue: **SPD Bank Oriental Sports Center (浦发银行东方体育中心)**. Valve + PGL. Base pool ~US$1.6M.
- **[C]** Game patch at launch: **7.41e** (Summer Cleaning / 夏令涤尘 update).

## Schedule (Beijing time, UTC+8)
- **[C]** Group stage: **2026-08-13 → 08-16**.
- **[C]** Main event (playoffs): **2026-08-20 → 08-23**.
- **[C]** Group-stage prediction lock: **2026-08-13 10:00 CST**, before match 1.

## Format — confirmed by official blog
- **[C] Group stage:** 16 teams, **5-round Swiss, all Bo3**.
  - **3 teams that reach 4 wins → advance directly to the main event.**
  - **3 teams that reach 4 losses → eliminated.**
  - the remaining **10 teams → "special elimination"**, seeded by Swiss record: **5 winners advance,
    5 losers eliminated.**
  - ⇒ **8-team main event.** (Corrects an earlier "3 wins / 3 losses" web snippet — the official
    thresholds are **4 wins / 4 losses over 5 rounds**.)
- **[P] Main event:** double elimination, Bo3, **Grand Final Bo5** — TI 2025 precedent; 2026
  per-round Bo is **[TBD]** until Valve posts the bracket.

## The 16-team field — confirmed, with TI gambling-brand renames
Two teams **compete under different names at TI** because Valve bans gambling-related branding —
this is why an earlier list showed apparent "conflicts":
- **BetBoom Team → "BoomBoys"** at TI.
- **PARIVISION → "Team Vision"** at TI.

| # | Team (org) | TI alias | Path | Region |
|---|-----------|----------|------|--------|
| 1 | Aurora Gaming | — | invite | EEU |
| 2 | BetBoom Team | **BoomBoys** | invite | EEU |
| 3 | Team Falcons | — | invite | WEU | 
| 4 | Team Liquid | — | invite | WEU |
| 5 | Tundra Esports | — | invite | WEU |
| 6 | Xtreme Gaming | — | invite | CN |
| 7 | Team Yandex | — | invite | EEU |
| 8 | Team Resilience | — | qualifier | CN |
| 9 | Vici Gaming | — | qualifier | CN |
| 10 | LGD Gaming | — | qualifier | SA |
| 11 | OG | — | qualifier | SEA |
| 12 | GamerLegion | — | qualifier | NA |
| 13 | Team Spirit | — | qualifier | EU |
| 14 | PARIVISION | **Team Vision** | qualifier | EU |
| 15 | HULIGANI | — | qualifier | EU |
| 16 | Nigma Galaxy | — | qualifier | EU |

Direct invites = 7 (WEU: Falcons, Liquid, Tundra; EEU: Aurora, Yandex, BetBoom; CN: Xtreme).
Qualifiers = 9 (EU 4, CN 2, SA 1, SEA 1, NA 1). Machine-readable copy:
`data/ti2026/inputs/teams.csv`.

> Earlier-list errata now fixed: **"1win" was wrong → Tundra Esports**; **"L1GA TEAM" was wrong →
> HULIGANI**; BetBoom/PARIVISION appear under their TI aliases.

## Still to confirm (blocking a full model)
- **[TBD]** Swiss round-1 draw / seeding — needed to simulate the Swiss stage.
- **[TBD]** Main-event exact Bo per round for 2026 (assume TI 2025 until posted).

## Prior-year anchor (calibration)
- **[C]** TI 2025 (Hamburg): champion **Team Falcons** beat **Xtreme Gaming 3–2** (Bo5 GF); Swiss
  Bo3 + 8-team double-elim playoff. Both finalists return as 2026 invites.
