"""Frog-themed economy built on Red's native, guild-specific bank."""
import asyncio
import random
import time
from datetime import datetime, timezone

import discord
from redbot.core import Config, bank, commands

from .items import CATCHES, SHOP, WORK, catch_random


BANK_NAME = "The Royal Ribbit Reserve"
CURRENCY = "Ribbucks"


def fmt(seconds):
    seconds = max(0, int(seconds))
    if seconds >= 3600:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
    if seconds >= 60:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds}s"


class Ribbit(commands.Cog):
    """The Royal Ribbit Reserve. Catch critters, earn and spend Ribbucks."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=202610131418, force_registration=True)
        self.config.register_guild(
            enabled=False, catch_seconds=900, daily_base=100,
            work_min=20, work_max=60, work_seconds=3600, ledger=[]
        )
        self.config.register_member(
            inventory={}, savings=0, last_catch=0.0, last_daily="",
            daily_streak=0, last_work=0.0
        )
        self._locks = {}

    def cog_unload(self):
        self._locks.clear()

    def _lock(self, guild):
        return self._locks.setdefault(guild.id, asyncio.Lock())

    async def _ready(self, ctx):
        if await bank.is_global():
            await ctx.send("The Reserve needs a **per-server** Red bank. Ask the bot owner to review `$bankset showsettings` before setup.")
            return False
        if not await self.config.guild(ctx.guild).enabled():
            await ctx.send("The Royal Ribbit Reserve has not opened yet. An admin can run `$ribbit setup`.")
            return False
        return True

    async def _log(self, guild, action, user_id, amount=0, other_id=None):
        async with self.config.guild(guild).ledger() as rows:
            rows.append({
                "at": int(time.time()), "event": str(action)[:48],
                "user": int(user_id), "other": int(other_id) if other_id else None,
                "amount": int(amount)
            })
            del rows[:-150]

    async def _room(self, member):
        cap = await bank.get_max_balance(member.guild)
        return max(0, cap - await bank.get_balance(member))

    async def _add(self, member, amount):
        if amount <= 0:
            return False
        if amount > await self._room(member):
            return False
        await bank.deposit_credits(member, amount)
        return True

    @commands.guild_only()
    @commands.group(name="ribbit", aliases=["rrr"], invoke_without_command=True)
    async def ribbit(self, ctx):
        """Frog economy commands."""
        await ctx.send(
            "**The Royal Ribbit Reserve** | Currency: **Ribbucks**\n"
            "`$ribbit catch` - search the marsh (15m by default)\n"
            "`$ribbit bag` / `$ribbit sell <catch|all> [count]`\n"
            "`$ribbit daily` / `$ribbit work`\n"
            "`$ribbit balance [@member]` / `$ribbit pay @member <amount>`\n"
            "`$ribbit deposit <amount>` / `$ribbit withdraw <amount>`\n"
            "`$ribbit shop` / `$ribbit buy <item> [count]`\n"
            "`$ribbit top` / `$ribbit rates`\n"
            "Admin: `$ribbit setup`, `$ribbit config`, `$ribbit grant`, `$ribbit audit`."
        )

    @ribbit.command(name="setup")
    @commands.admin_or_permissions(administrator=True)
    async def setup_reserve(self, ctx):
        """Initialize a fresh, guild-specific economy without resetting accounts."""
        if await bank.is_global():
            await ctx.send("Setup stopped: Red's bank is in global mode. The bot owner must decide whether to change that setting first (switching resets bank accounts).")
            return
        async with self._lock(ctx.guild):
            await bank.set_bank_name(BANK_NAME, ctx.guild)
            await bank.set_currency_name(CURRENCY, ctx.guild)
            await bank.set_default_balance(0, ctx.guild)
            await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.send(f"**{BANK_NAME} is OPEN!** All newly created accounts start with **0 {CURRENCY}**. Try `$ribbit catch`.")

    @ribbit.command(name="rates", aliases=["critters", "catches"])
    async def rates(self, ctx):
        """Show catch probabilities, sale values, and sting hazards."""
        lines = []
        for key, item in CATCHES.items():
            if "sting" in item:
                lo, hi = item["sting"]
                lines.append(f"{item['name']}: {item['weight']}% chance | sting: -{lo} to -{hi} Ribbucks")
            else:
                lines.append(f"{item['name']}: {item['weight']}% chance | sells for {item['value']}")
        await ctx.send("**Marsh field guide**\n" + "\n".join(lines))

    @ribbit.command(name="catch", aliases=["flies", "hunt"])
    async def catch(self, ctx):
        """Catch a random marsh critter; bad luck can sting."""
        if not await self._ready(ctx):
            return
        async with self._lock(ctx.guild):
            conf = self.config.member(ctx.author)
            now = time.time()
            seconds = await self.config.guild(ctx.guild).catch_seconds()
            remaining = seconds - (now - await conf.last_catch())
            if remaining > 0:
                await ctx.send(f"The flies aren't back yet! Try again in **{fmt(remaining)}**.")
                return
            item_id = catch_random()
            item = CATCHES[item_id]
            if "sting" in item:
                lo, hi = item["sting"]
                injury = random.randint(lo, hi)
                balance = await bank.get_balance(ctx.author)
                injury = min(injury, balance)
                if injury:
                    await bank.withdraw_credits(ctx.author, injury)
                    await self._log(ctx.guild, f"stung:{item_id}", ctx.author.id, -injury)
                msg = (f"A wild **{item['name']}** stung you! You lost **{injury} Ribbucks**."
                       if injury else f"A wild **{item['name']}** chased you off! No catch, but you had no Ribbucks to lose.")
            else:
                async with conf.inventory() as inventory:
                    inventory[item_id] = int(inventory.get(item_id, 0)) + 1
                msg = (f"You caught a **{item['name']}**! Added to your bag. "
                       f"It sells for **{item['value']} Ribbucks**. Use `$ribbit sell {item_id}`.")
            await conf.last_catch.set(now)
        await ctx.send(msg)

    @ribbit.command(name="bag", aliases=["inventory", "inv"])
    async def bag(self, ctx, member: discord.Member = None):
        """View catches and purchased collectibles."""
        if not await self._ready(ctx):
            return
        member = member or ctx.author
        inventory = await self.config.member(member).inventory()
        lines = []
        for key, quantity in sorted(inventory.items()):
            if quantity < 1:
                continue
            if key in CATCHES:
                item = CATCHES[key]
                lines.append(f"{item['name']} x{quantity} (sell: {item['value']} each)")
            elif key in SHOP:
                lines.append(f"{SHOP[key]['name']} x{quantity} (collectible)")
        await ctx.send(f"**{discord.utils.escape_markdown(member.display_name)}'s frog bag**\n" + ("\n".join(lines) if lines else "Your bag is empty. Try `$ribbit catch`."))

    @ribbit.command(name="sell")
    async def sell(self, ctx, item: str, quantity: int = 1):
        """Sell caught insects by key, or use 'all' to sell every catch."""
        if not await self._ready(ctx):
            return
        if quantity <= 0 or quantity > 100000:
            await ctx.send("Quantity must be between 1 and 100,000.")
            return
        item = item.lower().replace("-", "_")
        async with self._lock(ctx.guild):
            conf = self.config.member(ctx.author)
            inv = await conf.inventory()
            if item == "all":
                sold = {k: v for k, v in inv.items() if k in CATCHES and CATCHES[k]["value"] and v > 0}
            elif item in CATCHES and CATCHES[item]["value"] and inv.get(item, 0) >= quantity:
                sold = {item: quantity}
            else:
                await ctx.send("You don't have enough of that catch to sell. See `$ribbit bag` and `$ribbit rates`.")
                return
            total = sum(CATCHES[k]["value"] * v for k, v in sold.items())
            if not total:
                await ctx.send("No tasty catches to sell!")
                return
            if not await self._add(ctx.author, total):
                await ctx.send("Your wallet is at its bank limit. Store some Ribbucks first with `$ribbit deposit`.")
                return
            for k, v in sold.items():
                inv[k] -= v
                if inv[k] <= 0:
                    del inv[k]
            await conf.inventory.set(inv)
            await self._log(ctx.guild, "sell", ctx.author.id, total)
        await ctx.send(f"Sold **{sum(sold.values())} catches** for **{total} Ribbucks**. Ribbit!")

    @ribbit.command(name="daily")
    async def daily(self, ctx):
        """Collect a daily allowance with a consecutive-day bonus."""
        if not await self._ready(ctx):
            return
        async with self._lock(ctx.guild):
            conf = self.config.member(ctx.author)
            today = datetime.now(timezone.utc).date()
            previous = await conf.last_daily()
            if previous == today.isoformat():
                await ctx.send("Your daily lily-pad allowance has already been collected (resets at 00:00 UTC).")
                return
            from datetime import timedelta
            streak = (await conf.daily_streak() + 1) if previous == (today - timedelta(days=1)).isoformat() else 1
            base = await self.config.guild(ctx.guild).daily_base()
            reward = base + min(streak - 1, 7) * 10
            if not await self._add(ctx.author, reward):
                await ctx.send("Your wallet cannot hold the daily reward; make room and try again.")
                return
            await conf.last_daily.set(today.isoformat())
            await conf.daily_streak.set(streak)
            await self._log(ctx.guild, "daily", ctx.author.id, reward)
        await ctx.send(f"Daily allowance: **+{reward} Ribbucks**! Your pond streak is **{streak} day(s)**.")

    @ribbit.command(name="work")
    async def work(self, ctx):
        """Earn Ribbucks for helping out around the marsh."""
        if not await self._ready(ctx):
            return
        async with self._lock(ctx.guild):
            conf = self.config.member(ctx.author)
            now = time.time()
            delay = await self.config.guild(ctx.guild).work_seconds()
            remaining = delay - (now - await conf.last_work())
            if remaining > 0:
                await ctx.send(f"You're on a break. Your next pond job is in **{fmt(remaining)}**.")
                return
            settings = await self.config.guild(ctx.guild).all()
            reward = random.randint(settings["work_min"], settings["work_max"])
            task = random.choice(WORK)
            if not await self._add(ctx.author, reward):
                await ctx.send("Your wallet has insufficient room for a work reward. Store some Ribbucks first.")
                return
            await conf.last_work.set(now)
            await self._log(ctx.guild, "work", ctx.author.id, reward)
        await ctx.send(f"You {task} and earned **{reward} Ribbucks**!")

    @ribbit.command(name="balance", aliases=["bal", "bank"])
    async def balance(self, ctx, member: discord.Member = None):
        """Wallet balance and savings held at the Reserve."""
        if not await self._ready(ctx):
            return
        member = member or ctx.author
        wallet = await bank.get_balance(member)
        saved = await self.config.member(member).savings()
        await ctx.send(
            f"**{BANK_NAME} — {discord.utils.escape_markdown(member.display_name)}**\n"
            f"Wallet: **{wallet:,} Ribbucks** | Vault: **{saved:,} Ribbucks**\n"
            f"Total: **{wallet + saved:,} Ribbucks**"
        )

    @ribbit.command(name="deposit", aliases=["save"])
    async def deposit(self, ctx, amount: int):
        """Move Ribbucks from your wallet into the Reserve vault."""
        if not await self._ready(ctx):
            return
        if amount <= 0:
            await ctx.send("Deposit must be a positive number.")
            return
        async with self._lock(ctx.guild):
            if not await bank.can_spend(ctx.author, amount):
                await ctx.send("Your wallet doesn't have that many Ribbucks.")
                return
            conf = self.config.member(ctx.author)
            saved = await conf.savings()
            await bank.withdraw_credits(ctx.author, amount)
            try:
                await conf.savings.set(saved + amount)
            except Exception:
                await bank.deposit_credits(ctx.author, amount)
                raise
            await self._log(ctx.guild, "vault_deposit", ctx.author.id, amount)
        await ctx.send(f"Stored **{amount:,} Ribbucks** in your Reserve vault. No interest is applied.")

    @ribbit.command(name="withdraw", aliases=["unsave"])
    async def withdraw(self, ctx, amount: int):
        """Move Ribbucks from your Reserve vault to your wallet."""
        if not await self._ready(ctx):
            return
        if amount <= 0:
            await ctx.send("Withdrawal must be a positive number.")
            return
        async with self._lock(ctx.guild):
            conf = self.config.member(ctx.author)
            saved = await conf.savings()
            if saved < amount:
                await ctx.send("Not enough Ribbucks in the vault.")
                return
            if not await self._add(ctx.author, amount):
                await ctx.send("Your wallet cannot hold that many Ribbucks. Try a smaller withdrawal.")
                return
            try:
                await conf.savings.set(saved - amount)
            except Exception:
                await bank.withdraw_credits(ctx.author, amount)
                raise
            await self._log(ctx.guild, "vault_withdraw", ctx.author.id, -amount)
        await ctx.send(f"Withdrew **{amount:,} Ribbucks** from your Reserve vault.")

    @ribbit.command(name="pay", aliases=["transfer", "give"])
    async def pay(self, ctx, member: discord.Member, amount: int):
        """Transfer Ribbucks to another member."""
        if not await self._ready(ctx):
            return
        if amount <= 0 or member.bot or member.id == ctx.author.id:
            await ctx.send("Choose another real member and a positive amount.")
            return
        async with self._lock(ctx.guild):
            if not await bank.can_spend(ctx.author, amount) or amount > await self._room(member):
                await ctx.send("Insufficient funds or the recipient's wallet is full.")
                return
            await bank.transfer_credits(ctx.author, member, amount)
            await self._log(ctx.guild, "pay", ctx.author.id, -amount, member.id)
        await ctx.send(f"Paid **{amount:,} Ribbucks** to {member.mention}.")

    @ribbit.command(name="shop")
    async def shop(self, ctx):
        """See collectibles for sale in the frog shop."""
        if not await self._ready(ctx):
            return
        lines = [f"**{v['name']}** (`{k}`) — {v['price']:,} Ribbucks" for k, v in SHOP.items()]
        await ctx.send("**The Lily Pad Market**\n" + "\n".join(lines) + "\nUse `$ribbit buy item_key`. These items are cosmetic collectibles, not powers.")

    @ribbit.command(name="buy")
    async def buy(self, ctx, item: str, quantity: int = 1):
        """Buy a cosmetic collectible from the Lily Pad Market."""
        if not await self._ready(ctx):
            return
        item = item.lower().replace("-", "_")
        if item not in SHOP or quantity < 1 or quantity > 100:
            await ctx.send("Unknown collectible or invalid quantity. Check `$ribbit shop`.")
            return
        total = SHOP[item]["price"] * quantity
        async with self._lock(ctx.guild):
            if not await bank.can_spend(ctx.author, total):
                await ctx.send(f"You need **{total:,} Ribbucks** for this purchase.")
                return
            conf = self.config.member(ctx.author)
            inventory = await conf.inventory()
            await bank.withdraw_credits(ctx.author, total)
            inventory[item] = inventory.get(item, 0) + quantity
            try:
                await conf.inventory.set(inventory)
            except Exception:
                await bank.deposit_credits(ctx.author, total)
                raise
            await self._log(ctx.guild, f"buy:{item}", ctx.author.id, -total)
        await ctx.send(f"Purchased **{quantity} x {SHOP[item]['name']}** for **{total:,} Ribbucks**.")

    @ribbit.command(name="top", aliases=["richest", "leaderboard"])
    async def top(self, ctx):
        """Top ten members by wallet plus vault savings."""
        if not await self._ready(ctx):
            return
        wallets = await bank.get_leaderboard(guild=ctx.guild)
        accounts = {int(uid): int(raw.get("balance", 0)) for uid, raw in wallets}
        stored = await self.config.all_members(ctx.guild)
        for uid, data in stored.items():
            accounts[int(uid)] = accounts.get(int(uid), 0) + int(data.get("savings", 0))
        leaders = sorted(
            ((uid, amount) for uid, amount in accounts.items() if ctx.guild.get_member(uid) and not ctx.guild.get_member(uid).bot),
            key=lambda entry: (-entry[1], entry[0])
        )[:10]
        if not leaders:
            await ctx.send("The Reserve has no wealthy frogs yet.")
            return
        lines = [
            f"**{i}.** {discord.utils.escape_markdown(ctx.guild.get_member(uid).display_name)} — {amount:,} Ribbucks"
            for i, (uid, amount) in enumerate(leaders, 1)
        ]
        await ctx.send("**Royal Ribbit Rich List (wallet + vault)**\n" + "\n".join(lines))

    @ribbit.group(name="config", invoke_without_command=True)
    @commands.admin_or_permissions(administrator=True)
    async def configure(self, ctx):
        """View/configure the Reserve's earning rates and cooldowns."""
        settings = await self.config.guild(ctx.guild).all()
        await ctx.send(
            f"**Reserve controls**\n"
            f"Catch cooldown: {fmt(settings['catch_seconds'])}\n"
            f"Work cooldown: {fmt(settings['work_seconds'])}\n"
            f"Daily base: {settings['daily_base']} Ribbucks\n"
            f"Work reward: {settings['work_min']}–{settings['work_max']} Ribbucks\n"
            "Change with `$ribbit config catch <minutes>`, `workcooldown <minutes>`, "
            "`daily <amount>`, or `workreward <minimum> <maximum>`."
        )

    @configure.command(name="catch")
    async def config_catch(self, ctx, minutes: int):
        if not 1 <= minutes <= 1440:
            await ctx.send("Set the catch cooldown between 1 and 1,440 minutes.")
            return
        await self.config.guild(ctx.guild).catch_seconds.set(minutes * 60)
        await ctx.send(f"Catch cooldown set to **{minutes} minutes**.")

    @configure.command(name="workcooldown")
    async def config_workcooldown(self, ctx, minutes: int):
        if not 1 <= minutes <= 1440:
            await ctx.send("Set the work cooldown between 1 and 1,440 minutes.")
            return
        await self.config.guild(ctx.guild).work_seconds.set(minutes * 60)
        await ctx.send(f"Work cooldown set to **{minutes} minutes**.")

    @configure.command(name="daily")
    async def config_daily(self, ctx, amount: int):
        if not 1 <= amount <= 100000:
            await ctx.send("Set the base daily allowance between 1 and 100,000 Ribbucks.")
            return
        await self.config.guild(ctx.guild).daily_base.set(amount)
        await ctx.send(f"Daily base set to **{amount} Ribbucks**.")

    @configure.command(name="workreward")
    async def config_workreward(self, ctx, minimum: int, maximum: int):
        if not 1 <= minimum <= maximum <= 100000:
            await ctx.send("Use a minimum >= 1, a maximum >= minimum, and a maximum <= 100,000.")
            return
        conf = self.config.guild(ctx.guild)
        await conf.work_min.set(minimum)
        await conf.work_max.set(maximum)
        await ctx.send(f"Work rewards set to **{minimum}–{maximum} Ribbucks**.")

    @ribbit.command(name="grant")
    @commands.admin_or_permissions(administrator=True)
    async def grant(self, ctx, member: discord.Member, amount: int):
        """Admin-only grant of wallet credits."""
        if not await self._ready(ctx):
            return
        if amount <= 0 or amount > 1000000 or member.bot:
            await ctx.send("Grant 1–1,000,000 Ribbucks to a real member.")
            return
        async with self._lock(ctx.guild):
            if not await self._add(member, amount):
                await ctx.send("That grant would exceed the recipient's bank limit.")
                return
            await self._log(ctx.guild, "admin_grant", member.id, amount, ctx.author.id)
        await ctx.send(f"Granted **{amount:,} Ribbucks** to {member.mention}.")

    @ribbit.command(name="audit")
    @commands.admin_or_permissions(administrator=True)
    async def audit(self, ctx, limit: int = 10):
        """Show recent transactions from this cog; native bank changes are separate."""
        limit = max(1, min(15, limit))
        rows = (await self.config.guild(ctx.guild).ledger())[-limit:]
        if not rows:
            await ctx.send("No Reserve activity logged yet.")
            return
        lines = [
            f"<t:{r['at']}:f> | {r['event']} | {r['user']} | {r['amount']:+,}"
            for r in reversed(rows)
        ]
        await ctx.send("**Recent Reserve transactions**\n" + "\n".join(lines))

    async def award_for_game(self, member, amount, source):
        """Optional shared payout API for other cogs; returns True on success."""
        if member.bot or amount <= 0 or amount > 1000000:
            return False
        if await bank.is_global() or not await self.config.guild(member.guild).enabled():
            return False
        async with self._lock(member.guild):
            if not await self._add(member, amount):
                return False
            await self._log(member.guild, f"game:{source}", member.id, amount)
        return True

    async def red_delete_data_for_user(self, *, requester, user_id):
        """Delete this cog's member state and anonymize its event rows."""
        guild_data = await self.config.all_guilds()
        for guild_id in guild_data:
            await self.config.member_from_ids(int(guild_id), int(user_id)).clear()
            async with self.config.guild_from_id(int(guild_id)).ledger() as rows:
                rows[:] = [r for r in rows if r.get("user") != user_id and r.get("other") != user_id]
