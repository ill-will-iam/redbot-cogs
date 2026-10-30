"""Dig for treasure, mishaps, and fishing bait; sell valuables for Ribbucks."""

import asyncio
import logging
import time

import discord
from redbot.core import Config, bank, commands
from redbot.core.errors import BalanceTooHigh

from .loot import BAIT_EFFECTS, NAMES, SELL_PRICES, inventory_sale, roll_dig

LOG = logging.getLogger("red.will.dig")
THREE_DIGS = 3
COOLDOWN_SECONDS = 600
DEFAULT_STATE = {
    "inventory": {},
    "uses": 0,
    "cooldown_until": 0.0,
    "total_digs": 0,
    "chests": 0,
    "mishaps": 0,
    "ribbucks_earned": 0,
}
MISHAPS = {"mineshaft", "bullfrog_den", "sewer_pipe", "cursed_idol"}
ITEM_ALIASES = {
    "gold": "gold_ore",
    "ore": "gold_ore",
    "goldore": "gold_ore",
    "diamonds": "diamond",
    "stash": "drug_stash",
    "drugs": "drug_stash",
    "drugstash": "drug_stash",
    "worm": "earthworm",
    "worms": "earthworm",
    "goldenworm": "golden_worm",
}


def duration(seconds: float) -> str:
    remaining = max(0, int(seconds + 0.999))
    mins, secs = divmod(remaining, 60)
    return f"{mins}m {secs}s" if mins else f"{secs}s"


class Dig(commands.Cog):
    """Dig three times, then rest 10 minutes; trade loot at the Reserve."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=202610300452, force_registration=True)
        self.config.register_guild(chest_basis_points=400)
        self.config.register_member(state=DEFAULT_STATE)
        self._member_locks = {}

    def cog_unload(self):
        self._member_locks.clear()

    def _lock_for(self, guild_id: int, user_id: int) -> asyncio.Lock:
        return self._member_locks.setdefault((guild_id, user_id), asyncio.Lock())

    async def red_delete_data_for_user(self, *, requester, user_id):
        """Erase all per-guild digging data for a user, including bait and statistics."""
        for guild_id in (await self.config.all_members()).keys():
            async with self._lock_for(int(guild_id), int(user_id)):
                await self.config.member_from_ids(int(guild_id), int(user_id)).clear()

    @staticmethod
    def _normalize_item(value: str) -> str:
        key = value.strip().lower().replace(" ", "_").replace("-", "_")
        return ITEM_ALIASES.get(key, key)

    async def _reserve(self, ctx):
        """Find the installed Ribbit economy, preventing accidental second currencies."""
        ribbit = self.bot.get_cog("Ribbit")
        if ribbit is None:
            await ctx.send("The Royal Ribbit Reserve isn't loaded. Ask an admin to load `ribbit` before selling.")
            return None
        if await bank.is_global():
            await ctx.send("The Reserve needs Red's per-server bank mode. Ask the bot owner to check bank settings.")
            return None
        if not await ribbit.config.guild(ctx.guild).enabled():
            await ctx.send("The Royal Ribbit Reserve isn't open here. Ask an admin to run `~ribbit setup`.")
            return None
        return ribbit

    async def get_bait_count(self, member: discord.Member, bait: str = "earthworm") -> int:
        """Public API for future fishing cog; returns current bait count."""
        bait = self._normalize_item(bait)
        if bait not in BAIT_EFFECTS:
            raise ValueError("Unknown bait type")
        async with self._lock_for(member.guild.id, member.id):
            state = await self.config.member(member).state()
            return max(0, int(state["inventory"].get(bait, 0)))

    async def consume_bait(self, member: discord.Member, bait: str = "earthworm", quantity: int = 1) -> bool:
        """Public API: atomically remove fishing bait; True iff removal succeeded.

        Fishing should call this only when awarding the fish. If a golden worm
        was consumed, fishing MUST grant a mythic fish to honor its guarantee.
        """
        bait = self._normalize_item(bait)
        if bait not in BAIT_EFFECTS or not (1 <= quantity <= 100):
            raise ValueError("Invalid bait or quantity")
        async with self._lock_for(member.guild.id, member.id):
            conf = self.config.member(member).state
            state = await conf()
            inventory = state["inventory"]
            if inventory.get(bait, 0) < quantity:
                return False
            inventory[bait] -= quantity
            if inventory[bait] == 0:
                del inventory[bait]
            await conf.set(state)
            return True

    @commands.guild_only()
    @commands.group(name="dig", aliases=["d"], invoke_without_command=True)
    async def dig(self, ctx):
        """Dig once! Three consecutive digs, then a ten-minute cooldown.

        Also: ~dig bag, ~dig sell, ~dig odds, ~dig status.
        """
        if ctx.author.bot:
            return
        async with self._lock_for(ctx.guild.id, ctx.author.id):
            conf = self.config.member(ctx.author).state
            state = await conf()
            now = time.time()
            if state["cooldown_until"] > now:
                await ctx.send(
                    f"Your shovel is in timeout. The ground reopens in **{duration(state['cooldown_until'] - now)}**. "
                    "Try `~dig bag` while you're waiting."
                )
                return
            if state["uses"] >= THREE_DIGS:
                state["uses"] = 0
                state["cooldown_until"] = 0.0

            chance = await self.config.guild(ctx.guild).chest_basis_points()
            result = roll_dig(chance)
            for name, count in result.loot.items():
                inventory = state["inventory"]
                inventory[name] = int(inventory.get(name, 0)) + count
            state["total_digs"] += 1
            state["uses"] += 1
            if result.kind == "chest":
                state["chests"] += 1
            if result.kind in MISHAPS:
                state["mishaps"] += 1
            if state["uses"] == THREE_DIGS:
                state["cooldown_until"] = now + COOLDOWN_SECONDS
            await conf.set(state)
            used = state["uses"]
            cool_until = state["cooldown_until"]

        loot = ", ".join(f"**{NAMES[key]} x{quantity}**" for key, quantity in result.loot.items())
        text = f"⛏️ **DIG {used}/{THREE_DIGS}** — {result.text}"
        if loot:
            text += f"\n**Collected:** {loot}"
        if cool_until > 0:
            text += f"\n**All three digs used!** Rest your shovel for **{duration(cool_until - now)}**."
        else:
            text += f"\n**{THREE_DIGS - used} dig(s) left** before your ten-minute cooldown."
        await ctx.send(text, allowed_mentions=discord.AllowedMentions.none())

    @dig.command(name="bag", aliases=["inventory", "inv"])
    async def bag(self, ctx, member: discord.Member = None):
        """View digging valuables and preserved bait."""
        member = member or ctx.author
        state = await self.config.member(member).state()
        inventory = state["inventory"]
        lines = []
        for key in ("gold_ore", "diamond", "drug_stash", "earthworm", "golden_worm"):
            qty = int(inventory.get(key, 0))
            if qty <= 0:
                continue
            item = f"**{NAMES[key]}** x{qty}"
            if key in SELL_PRICES:
                item += f" — sells for {SELL_PRICES[key]:,} each"
            elif key == "golden_worm":
                item += " — **guaranteed mythic fish** (future fishing cog)"
            else:
                item += " — future fishing bait"
            lines.append(item)
        name = discord.utils.escape_markdown(member.display_name)
        await ctx.send(
            f"**{name}'s Digging Bag**\n"
            + ("\n".join(lines) if lines else "Nothing in the bag yet. Try `~d`.")
            + "\nValuables are sold with `~dig sell all`; worms cannot be sold."
        )

    @dig.command(name="status", aliases=["cooldown", "cd", "stats"])
    async def status(self, ctx):
        """See remaining digs, cooldown, and total finds."""
        state = await self.config.member(ctx.author).state()
        remaining = state["cooldown_until"] - time.time()
        if remaining > 0:
            headline = f"On cooldown for **{duration(remaining)}**."
        else:
            remaining_uses = THREE_DIGS if state["uses"] >= THREE_DIGS else THREE_DIGS - state["uses"]
            headline = f"**{remaining_uses}/{THREE_DIGS}** digs available."
        await ctx.send(
            f"**Dig status:** {headline}\n"
            f"Total digs: **{state['total_digs']}** | Treasure chests: **{state['chests']}** | "
            f"Mishaps: **{state['mishaps']}** | Sold for: **{state['ribbucks_earned']:,} Ribbucks**"
        )

    @dig.command(name="odds", aliases=["rates", "prices"])
    async def odds(self, ctx):
        """Show chest odds, sale prices and golden worm rarity."""
        chance = await self.config.guild(ctx.guild).chest_basis_points()
        await ctx.send(
            f"**Digging Field Guide**\n"
            f"Treasure chest: **{chance / 100:g}% of digs**. Each chest contains **2–4 gold ore OR diamonds** "
            f"and **1–2 earthworms**. Every chest has a separate **2.5% chance** of one bonus golden worm.\n"
            "Normal digs may yield gold ore, diamonds, a suspicious drug stash, or an earthworm. "
            "Mineshafts, rabid bullfrogs, broken pipes, and cursed idols award nothing.\n"
            + "\n".join(f"**{NAMES[key]}:** {price} Ribbucks each" for key, price in SELL_PRICES.items())
            + "\n**Worms cannot be sold.** Golden worms guarantee a **mythic fish** once fishing is implemented."
        )

    @dig.command(name="sell")
    async def sell(self, ctx, item: str, quantity: int = 1):
        """Sell valuables for Ribbucks. Example: ~dig sell gold 2 / ~dig sell all."""
        if quantity < 1 or quantity > 100000:
            await ctx.send("Quantity must be between 1 and 100,000.")
            return
        key = self._normalize_item(item)
        if key not in SELL_PRICES and key != "all":
            await ctx.send("You can sell `gold_ore`, `diamond`, or `drug_stash`. Use `~dig sell all` for everything sellable. Worms are protected.")
            return
        ribbit = await self._reserve(ctx)
        if ribbit is None:
            return
        # Ribbit serializes all its guild bank operations through this lock.
        # Sharing it prevents competing sell/transfer/deposit operations in Ribbit.
        async with ribbit._lock(ctx.guild):
            async with self._lock_for(ctx.guild.id, ctx.author.id):
                conf = self.config.member(ctx.author).state
                state = await conf()
                inventory = state["inventory"]
                sold, total = inventory_sale(inventory, key, quantity)
                if not sold:
                    await ctx.send("You don't have enough of that sellable loot. See `~dig bag`.")
                    return
                available = await bank.get_max_balance(ctx.guild) - await bank.get_balance(ctx.author)
                if total > available:
                    await ctx.send(
                        f"The Reserve cannot hold **{total:,} more Ribbucks** in your wallet. "
                        "Use `~ribbit deposit <amount>` to make room, then try again."
                    )
                    return
                # No valuable items are removed unless the deposit succeeds.
                try:
                    await bank.deposit_credits(ctx.author, total)
                except BalanceTooHigh:
                    await ctx.send("Your Ribbucks wallet filled up. Make room at the Reserve and try again.")
                    return
                for sold_key, count in sold.items():
                    inventory[sold_key] -= count
                    if inventory[sold_key] <= 0:
                        del inventory[sold_key]
                state["ribbucks_earned"] += total
                try:
                    await conf.set(state)
                except Exception:
                    # Mirrors the rollback strategy in ribbit's own sell command.
                    await bank.withdraw_credits(ctx.author, total)
                    raise
                try:
                    await ribbit._log(ctx.guild, "dig:sell", ctx.author.id, total)
                except Exception:
                    LOG.exception("Dig sale completed but Reserve ledger logging failed")
        await ctx.send(
            f"**Sold {sum(sold.values())} item(s)** for **{total:,} Ribbucks**! "
            "Your balance is in the **Royal Ribbit Reserve**. Bait stays in your bag."
        )

    @dig.group(name="config", invoke_without_command=True)
    @commands.admin_or_permissions(administrator=True)
    async def configure(self, ctx):
        """Admin configuration for treasure-chest rarity."""
        chance = await self.config.guild(ctx.guild).chest_basis_points()
        await ctx.send(
            f"Treasure-chest odds: **{chance / 100:g}%** per dig. "
            "To adjust between 2% and 5%: `~dig config chest 2.5`"
        )

    @configure.command(name="chest")
    async def configure_chest(self, ctx, percent: float):
        """Set chest percentage from 2 to 5, including decimals."""
        if not 2.0 <= percent <= 5.0:
            await ctx.send("Choose a chest chance between **2% and 5%**.")
            return
        basis_points = round(percent * 100)
        await self.config.guild(ctx.guild).chest_basis_points.set(basis_points)
        await ctx.send(f"Treasure chest chance set to **{basis_points / 100:g}%** per dig.")
