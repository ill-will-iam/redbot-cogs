# Dig — Fatboy Redbot V3 Cog

Use `~d` or `~dig` to dig for valuables and fishing bait. Each guild member gets **three immediate digs**, followed by a **10-minute cooldown beginning with dig #3**. Partial batches don't expire; the timer starts only after the third dig. Cooldowns and inventories persist across restarts. No outside packages are needed.

## Install

After this folder is committed under `dig/` in `ill-will-iam/redbot-cogs`:

```
~repo update redbot-cogs
~cog install redbot-cogs dig
~load dig
```

If `ribbit` isn't running, players can collect items, but **cannot sell** until the Royal Ribbit Reserve is set up for this server using `~ribbit setup`. Dig uses the **same Red guild bank**, not a separate wallet. Dug items have a separate `~dig bag` inventory rather than appearing in `~ribbit bag`.

## Commands

| Command | Function |
|---|---|
| `~d` or `~dig` | Attempt a dig; 3 digs per 10-minute cycle. |
| `~dig bag` | View gold ore, diamonds, contraband, worms, golden worms. |
| `~dig status` | Digs remaining, cooldown, chests, mishaps, sales total. |
| `~dig odds` | Chest odds and sale prices. |
| `~dig sell all` | Sell all saleable dug loot for Ribbucks; never sells worms. |
| `~dig sell gold 2` | Sell 2 gold ores; also `diamond`, `stash`. |
| `~dig config` | Admin-only, see chest odds. |
| `~dig config chest 2.5` | Admin-only, change chest odds to any value between 2% and 5%. |

### Sale values

- Gold ore — 55 Ribbucks.
- Diamond — 160 Ribbucks.
- Suspicious drug stash (fictional collectible) — 95 Ribbucks.
- Earthworm / Golden worm — never sellable.

### Odds

Default chest chance is **4% per dig** (admin adjustable **2%-5%**). Every chest contains:

- **2 to 4** gold ores **or** diamonds, randomly chosen (75% gold ore, 25% diamonds).
- **1 or 2** ordinary earthworms.
- Independently, a **2.5% chance per chest** to include **one additional golden worm**. At the default 4% chest chance, each dig has a 0.1% overall chance for a golden worm (about 1 in 1000 digs); at 2%-5% chest odds, this ranges from 0.05%-0.125% per dig.

If no chest appeared, weighted outcomes are: gold ore 34%, diamond 10%, drug stash 20%, earthworm 18%, broken leg in an abandoned mineshaft 7%, rabid bullfrog den 6%, sewer pipe 3%, and cursed idol 2%. The remaining percentage of the total dig probability after the chest roll is allocated among these outcomes. Mishaps give no loot or deductions, but still consume one dig.

## Future fishing cog API

```python
dig = bot.get_cog("Dig")
count = await dig.get_bait_count(member, "earthworm")
used = await dig.consume_bait(member, "golden_worm", quantity=1)
if used:
    # IMPORTANT: grant a MYTHIC fish on this successful catch.
    rarity = "mythic"
```

`Dig` exposes `BAIT_EFFECTS` in `dig.loot`:

```
{"golden_worm": {"guaranteed_rarity": "mythic"}}
```

**The mythic guarantee is a contract for the future fishing cog**, not an implemented fishing feature in this release. Future fishing must consume a golden worm only when it awards the mythic fish (not upon failed casting). Dig's `consume_bait` atomically decrements bait, even under concurrent fishing commands.

## Engineering notes

- Locks serialize every dig, bait consumption, and sale per user/server. Sales also share the existing Ribbit cog's guild lock so Ribbit wallet operations cannot race the new seller.
- The bank credit is deposited first, and digging inventory is decremented only after a successful deposit; if the subsequent inventory write fails, the credit is rolled back.
- A full wallet leaves loot untouched. Players can create room with `~ribbit deposit <amount>`.
- All loot, stats, and cooldowns are stored in Red Config and can be erased using Red's user-data deletion mechanism. No chat message logs are stored.
- No additional gameplay penalty is applied to a broken leg. It is a narrative setback, not a persistent injury state.
- Separate guilds have separate bags and cooldowns.
