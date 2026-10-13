# The Royal Ribbit Reserve (Ribbit)

One frog-themed economy, currency **Ribbucks**, bank **The Royal Ribbit Reserve**.

This cog uses Red's **native bank for wallet balances**, which allows other cogs to award Ribbucks without importing this cog. Its own Red Config storage tracks inventory, UTC daily streaks, work/catch cooldowns, vault savings, and an admin-only rolling ledger of up to 150 transactions per guild.

## Installation

Keep your Red installation up-to-date (3.5+). Bot prefix in examples is `$`.

```text
$unload economy
$repo update redbot-cogs
$cog install redbot-cogs ribbit
$load ribbit
$bankset showsettings
$ribbit setup
$ribbit
```

**Important:** Setup requires Red's **server-local bank**, not its global bank. The bot owner decides if a mode change is appropriate. Red's global/local switch erases native bank accounts; do not switch after starting gameplay. Setup never resets existing balances. New accounts are set to start at 0 Ribbucks.

## Player commands

| Command | Effect |
| --- | --- |
| `$ribbit catch` | One weighted marsh search every 15 minutes by default; 85% catches, 15% mishaps |
| `$ribbit rates` | Odds and sell values for catches |
| `$ribbit bag [@member]` | Inventory (caught creatures and cosmetic collectibles) |
| `$ribbit sell housefly [qty]` | Sell a specified catch |
| `$ribbit sell all` | Sell all caught edible creatures |
| `$ribbit daily` | Daily UTC allowance and consecutive-day bonus |
| `$ribbit work` | Get a random pond job, hourly by default |
| `$ribbit balance [@member]` | Wallet, Reserve vault, total |
| `$ribbit deposit <amount>` | Store wallet Ribbucks in the vault |
| `$ribbit withdraw <amount>` | Move vault Ribbucks to the wallet |
| `$ribbit pay @member <amount>` | Transfer wallet Ribbucks |
| `$ribbit shop` | Market catalogue |
| `$ribbit buy item_key [qty]` | Buy cosmetic collectible |
| `$ribbit top` | Guild wealth leaderboard |

## Admin commands

| Command | Effect |
| --- | --- |
| `$ribbit setup` | Configure Red's local native bank name/currency and open the Reserve |
| `$ribbit config` | See reward/cooldown settings |
| `$ribbit config catch 15` | Set catch cooldown in minutes |
| `$ribbit config workcooldown 60` | Set work cooldown in minutes |
| `$ribbit config daily 100` | Set daily base reward |
| `$ribbit config workreward 20 60` | Set job min and max |
| `$ribbit grant @member 100` | Give Ribbucks (admin-only, logged) |
| `$ribbit audit 10` | Show recent transactions managed by this cog |

The shop items are collectible only: they do not grant Discord roles, special permissions, or extra earnings. There is no interest or gambling in this first release. Each account starts at zero. Default daily reward is 100 plus up to 70 for consecutive days; work is 20–60 every hour.

### Catch probabilities

**Edible catches (85% total):** Housefly 23% (6), Gnat 15% (3), Mosquito 12% (9), Moth 10% (15), Cricket 8% (25), Grasshopper 7% (40), Butterfly 4% (70), Dragonfly 3% (110), Firefly 2% (175), Royal Moth 1% (350). Figures in parentheses are Ribbucks earned when sold.

**Mishaps (15% total):** Bee 5% (lose 5–12 Ribbucks), Wasp 4% (lose 10–24), Fell in a Hole 4% (lose 7–20), Hit by a Car 2% (lose 25–60). Penalties are capped at the wallet's current balance, so a mishap cannot cause negative funds. Mishaps never produce an inventory item.

Positive catches go into inventory and yield credits **only when sold**. The chance distribution totals exactly 100%.

## Integration with existing cogs

- **AcroGame:** its existing `$acro setcoins <amount>` deposits into Red's native bank, the same Ribbucks wallet.
- **FrogPond / DailyDrawings:** their code currently awards separate points/recognition; no Ribbucks payouts until those cogs are explicitly wired up.
- Other custom cogs may call `await bot.get_cog("Ribbit").award_for_game(member, amount, "game_name")`. This routine enforces the per-server enabled state, shared bank cap, and records the payout. It returns a boolean.
- The Red stock **Economy** cog should stay unloaded to avoid competing `payday`, `slot` and `bank` interfaces.
- The new cog registers the `ribbit` group (alias `rrr`), not generic top-level names such as `catch`, `shop`, or `bank`, to minimize command collisions. Short aliases can be made later via Red's Alias cog.

## Safety / limitations

- Prevents negative balances, over-limit wallet deposits, duplicate cooldown claims within one process, and self-transfers.
- Native bank writes and the custom savings/inventory storage are separate Red transactions; cross-store operations are **not crash-atomic**. A power loss at the exact moment of vault transfer might need manual reconciliation from the ledger. Backups remain wise even for a fresh economy.
- Admin ledger covers this cog's transactions, **not native-bank transactions made by other cogs**.
- Bank credits, unlike this cog's own member data, are managed and erased through Red's core bank controls.
- Persistence is per guild; the Red bank must remain in local mode for payouts and savings.
- This release has not been integration-tested against the live Discord instance.

Source: https://github.com/ill-will-iam/redbot-cogs/tree/main/ribbit
