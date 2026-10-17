# RuneScapeX — detailed OSRS / RS3 cog for Red-DiscordBot

A **separate**, safe-to-install companion to a pre-existing `runescape` cog. It is
named `runescapex` to avoid overwriting an unknown third-party cog or conflicting
with its existing commands. Uses public Jagex hiscores and OSRS Wiki GE prices;
**no API token or pip requirement** beyond Red's existing aiohttp/discord.py.

## Installation / testing on Fatboy

In Discord (with Downloader loaded):

```text
$backup
$repo update redbot-cogs
$cog install redbot-cogs runescapex
$load runescapex
$rsx help
$rsx osrs Zezima
$rsx rs3 Zezima
$rsx skills osrs Zezima
$rsx skill osrs Attack Zezima
$rsx bosses Zezima
$rsx clues Zezima
$rsx compare osrs Zezima | Lynx Titan
$rsx gains osrs Zezima
$rsx price Abyssal whip
$rsx items dragon
```

`$rsx gains` takes a first baseline; subsequent calls report differences since
that baseline, then update it. At most 200 player snapshots are retained.

## Boundaries

- OSRS hiscores are read through Jagex's **named JSON** endpoint, so new skills
  (including Sailing) and activities remain aligned when Jagex changes the roster.
- Boss and clue pages display **ranked public records only**; unranked records
  are not evidence of zero kills. The boss roster is deliberately curated so
  arbitrary minigame scores are not incorrectly labelled kills.
- RS3 uses its public lite hiscores CSV. RS3 boss kill counts, quests,
  equipment, account bank, and unranked activity data are **not** exposed here.
- `skill` XP-to-next uses the standard XP curve, not RS3 Invention's special curve.
- GE high/low values are last-trade quotes; apparent spread isn't profit.
  Market samples can be stale. Queries are cached to protect upstream services.
- API outages, rate limiting and deleted/unranked players are handled as
  readable Discord errors. Public hiscores may lag in-game progression.
- To replace your original cog later, first identify its source and commands.
  This separate cog can coexist without disrupting it.

Data attribution: Jagex RuneScape hiscores; OSRS Wiki real-time prices.
