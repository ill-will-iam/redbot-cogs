# RuneScapeX — OSRS-only cog for Red-DiscordBot

A dedicated **Old School RuneScape** companion cog. Includes detailed player
stats, skill breakdowns, boss and clue hiscores, comparisons, XP/KC gain tracking,
and OSRS Grand Exchange prices. No RuneScape 3 features or game-selection args.

The cog is intentionally named `runescapex` and uses the `$rsx` command group
to coexist with a separately installed `runescape` cog.

## Update Fatboy (already installed)

In Discord (adjust `$` if your bot uses another prefix):

```text
$backup
$repo update redbot-cogs
$cog update runescapex
$reload runescapex
$rsx help
```

For a **first installation** instead of an update, use:

```text
$cog install redbot-cogs runescapex
$load runescapex
```

## Commands — OSRS only

| Command | Description |
| --- | --- |
| `$rsx Zezima` | Player profile (shortcut for `profile`) |
| `$rsx profile Zezima` | Total level, XP, rank, combat, 99s, top skills |
| `$rsx skills Zezima` | All skills, XP, and ranks, paginated |
| `$rsx skill Attack Zezima` | Specific skill level, XP, rank, XP to next, virtual level |
| `$rsx bosses Zezima` | Ranked boss kill counts and ranks |
| `$rsx clues Zezima` | Clue completions and ranks |
| `$rsx compare Zezima | Lynx Titan` | Compare two players (separate with `|`) |
| `$rsx gains Zezima` | XP, level and boss KC gained since previous snapshot |
| `$rsx price Abyssal whip` | GE quotes, spread, 1h volume, limit |
| `$rsx items dragon` | Search the OSRS item catalogue |
| `$rsx help` | Show command list in Discord |

Short aliases: `p`/`stats` for `profile`, `levels` for `skills`, `boss` for
`bosses`, `clue` for `clues`, `vs` for `compare`, `progress` for `gains`,
`ge` for `price`, and `search` for `items`.

`$rsx gains` takes a baseline on first use; subsequent calls report differences
since that baseline and replace it. **Existing OSRS snapshots are preserved** by
keeping the same storage keys (`osrs:<player>`). Up to 200 total historical
snapshot entries are retained.

## Data notes

- Only OSRS public Jagex JSON hiscores are used; named skills include Sailing
  when Jagex supplies it. No third-party account login or API key is required.
- Boss and clue commands show **public ranked records only**: unranked does not
  necessarily mean zero kills or completions. Boss records use a curated list.
- OSRS Wiki price data uses recent player trades; price differences are not
  guaranteed profit, and quotes or hiscores may lag actual game activity.
- No private quests, bank, equipment, or unranked activity data is claimed.
- Errors, HTTP rate limits, and temporary API outages are handled in-chat.
- The original `runescape` cog is not modified or uninstalled by this update.

Data: Jagex Old School RuneScape hiscores and OSRS Wiki real-time prices API.
