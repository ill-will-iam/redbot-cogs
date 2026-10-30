"""Rated-R, consent-first Truth or Dare for adult Discord channels."""

from collections import defaultdict, deque
from typing import Dict, Optional, Set, Tuple
import secrets

import discord
from redbot.core import Config, commands

from .prompts import DARES, TRUTHS, WILD_DARES, WILD_TRUTHS


class TruthOrDare(commands.Cog):
    """Spicy Truth or Dare with voluntary player pools and no-repeat prompts."""

    __author__ = "Will"
    __version__ = "1.1.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1062026841, force_registration=True)
        self.config.register_guild(enabled=True)
        # Volatile only: (guild_id, channel_id) -> consenting member IDs.
        self._players: Dict[Tuple[int, int], Set[int]] = {}
        self._last_player: Dict[Tuple[int, int], int] = {}
        self._recent = defaultdict(lambda: deque(maxlen=25))
        self._cooldowns = commands.CooldownMapping.from_cooldown(
            1, 5, commands.BucketType.user
        )

    async def cog_check(self, ctx: commands.Context) -> bool:
        """All commands belong in a server, including grouped subcommands."""
        return ctx.guild is not None

    @staticmethod
    def _safe_name(member: discord.Member) -> str:
        return discord.utils.escape_markdown(
            discord.utils.escape_mentions(member.display_name)
        )

    @staticmethod
    def _channel_key(ctx: commands.Context) -> Tuple[int, int]:
        return (ctx.guild.id, ctx.channel.id)

    async def _game_allowed(self, ctx: commands.Context) -> bool:
        if ctx.guild is None:
            await ctx.send("Truth or Dare only works in servers.")
            return False
        if not await self.config.guild(ctx.guild).enabled():
            await ctx.send("Truth or Dare is disabled in this server.")
            return False
        return True

    def _draw(self, key: Tuple[int, int], kind: str) -> str:
        """Favor the bolder Wild pool while avoiding the last 25 prompts."""
        classic, wild = (TRUTHS, WILD_TRUTHS) if kind == "truth" else (DARES, WILD_DARES)
        history = self._recent[(key[0], key[1], kind)]

        # Wild prompts show up three quarters of the time by default.
        chosen_pool = "wild" if secrets.randbelow(4) != 0 else "classic"
        for pool_name in (chosen_pool, "classic" if chosen_pool == "wild" else "wild"):
            prompts = wild if pool_name == "wild" else classic
            choices = [i for i in range(len(prompts)) if (pool_name, i) not in history]
            if choices:
                index = secrets.choice(choices)
                history.append((pool_name, index))
                return prompts[index]

        # Extremely small future prompt pools can exhaust both categories.
        history.clear()
        prompts = wild if chosen_pool == "wild" else classic
        index = secrets.randbelow(len(prompts))
        history.append((chosen_pool, index))
        return prompts[index]

    async def _prompt(
        self,
        ctx: commands.Context,
        kind: str,
        member: Optional[discord.Member] = None,
    ):
        if not await self._game_allowed(ctx):
            return
        target = member or ctx.author
        if target.bot:
            await ctx.send("Even fatboy won't subject another bot to this game.")
            return
        key = self._channel_key(ctx)
        if target.id != ctx.author.id and target.id not in self._players.get(key, set()):
            await ctx.send(
                f"**{self._safe_name(target)}** hasn't joined this channel's game. "
                f"They can opt in with {ctx.clean_prefix}tod join.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        bucket = self._cooldowns.get_bucket(ctx.message)
        retry_after = bucket.update_rate_limit()
        if retry_after:
            await ctx.send(f"Easy, troublemaker. Try again in {retry_after:.0f}s.")
            return

        resolved = secrets.choice(("truth", "dare")) if kind == "random" else kind
        prompt = self._draw(key, resolved)
        header = "🔥 **TRUTH — RATED R**" if resolved == "truth" else "😈 **DARE — RATED R**"
        await ctx.send(
            f"{header}\n\n**{self._safe_name(target)}**, {prompt}\n\n"
            "*18+ • Play voluntarily • You can always pass.*",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return True

    @commands.group(name="tod", invoke_without_command=True)
    @commands.guild_only()
    async def tod(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Get a random R-rated truth or dare, optionally for an opted-in member.

        [p]tod
        [p]tod @member
        [p]tod truth @member
        [p]tod dare
        """
        await self._prompt(ctx, "random", member)

    @tod.command(name="truth")
    async def tod_truth(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Get a truth (for yourself or an opted-in member)."""
        await self._prompt(ctx, "truth", member)

    @tod.command(name="dare")
    async def tod_dare(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Get a dare (for yourself or an opted-in member)."""
        await self._prompt(ctx, "dare", member)

    @commands.command(name="truth")
    @commands.guild_only()
    async def truth(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Shortcut for [p]tod truth."""
        await self._prompt(ctx, "truth", member)

    @commands.command(name="dare")
    @commands.guild_only()
    async def dare(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Shortcut for [p]tod dare."""
        await self._prompt(ctx, "dare", member)

    @tod.command(name="join")
    async def tod_join(self, ctx: commands.Context):
        """Opt into being randomly picked or named by other players in this channel."""
        if not await self._game_allowed(ctx):
            return
        key = self._channel_key(ctx)
        members = self._players.setdefault(key, set())
        if ctx.author.id in members:
            await ctx.send("You're already in this channel's player pool.")
            return
        if len(members) >= 100:
            await ctx.send("This channel's player pool is full (100 members).")
            return
        members.add(ctx.author.id)
        await ctx.send(
            f"✅ **{self._safe_name(ctx.author)}** joined! "
            f"Use {ctx.clean_prefix}tod next to draw a player.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @tod.command(name="leave")
    async def tod_leave(self, ctx: commands.Context):
        """Stop being targeted or randomly picked in this channel."""
        key = self._channel_key(ctx)
        members = self._players.get(key)
        if members:
            members.discard(ctx.author.id)
            if not members:
                self._players.pop(key, None)
            if self._last_player.get(key) == ctx.author.id or not members:
                self._last_player.pop(key, None)
        await ctx.send("✅ You've left this channel's Truth or Dare player pool.")

    @tod.command(name="players")
    async def tod_players(self, ctx: commands.Context):
        """Show the volunteers in this channel's player pool."""
        if not await self._game_allowed(ctx):
            return
        key = self._channel_key(ctx)
        members = [
            member for user_id in self._players.get(key, set())
            if (member := ctx.guild.get_member(user_id)) is not None and not member.bot
        ]
        if not members:
            await ctx.send(
                f"No players have joined yet. Start with {ctx.clean_prefix}tod join."
            )
            return
        names = [self._safe_name(member) for member in sorted(members, key=lambda m: m.id)]
        await ctx.send(
            f"🎲 **Players ({len(names)}):** " + ", ".join(names[:20])
            + (f" and {len(names) - 20} more." if len(names) > 20 else ""),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @tod.command(name="next")
    async def tod_next(self, ctx: commands.Context, kind: str = "random"):
        """Pick a random volunteer: [p]tod next [truth|dare|random]."""
        if not await self._game_allowed(ctx):
            return
        kind = kind.lower()
        if kind not in ("truth", "dare", "random"):
            await ctx.send(f"Use {ctx.clean_prefix}tod next truth, dare, or random.")
            return
        key = self._channel_key(ctx)
        ids = self._players.get(key, set())
        members = [
            member for user_id in ids
            if (member := ctx.guild.get_member(user_id)) is not None and not member.bot
        ]
        if not members:
            await ctx.send(f"Nobody's joined yet. Try {ctx.clean_prefix}tod join.")
            return
        previous = self._last_player.get(key)
        possible = [member for member in members if member.id != previous] or members
        target = secrets.choice(possible)
        # Only advance the turn when a prompt was actually sent.
        if await self._prompt(ctx, kind, target):
            self._last_player[key] = target.id

    @tod.command(name="rules")
    async def tod_rules(self, ctx: commands.Context):
        """Explain the game and its boundaries."""
        prefix = ctx.clean_prefix
        await ctx.send(
            "🎲 **Rated-R Truth or Dare — 18+**\n"
            "• Play only in channels approved by your server's moderators.\n"
            f"• Use {prefix}tod, {prefix}truth, or {prefix}dare for yourself.\n"
            f"• Use {prefix}tod join to volunteer for {prefix}tod next or being targeted.\n"
            f"• Use {prefix}tod leave whenever you want, no explanation needed.\n"
            "• Anyone can pass. No pressure, harassment, unwanted DMs, "
            "nudity, explicit images, or dangerous dares.\n"
            "• Keep things consensual and respect each server's rules."
        )

    @commands.group(name="todset", invoke_without_command=True)
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def todset(self, ctx: commands.Context):
        """Server admin control for the R-rated Truth or Dare game."""
        enabled = await self.config.guild(ctx.guild).enabled()
        await ctx.send(
            f"Rated-R Truth or Dare is **{'on' if enabled else 'off'}**. "
            "No NSFW channel flag is required; follow your server's rules."
        )

    @todset.command(name="on")
    @commands.admin_or_permissions(manage_guild=True)
    async def todset_on(self, ctx: commands.Context):
        """Enable Truth or Dare in this server."""
        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.send("✅ Rated-R Truth or Dare is enabled in this server.")

    @todset.command(name="off")
    @commands.admin_or_permissions(manage_guild=True)
    async def todset_off(self, ctx: commands.Context):
        """Disable the game and clear all temporary player pools in this server."""
        await self.config.guild(ctx.guild).enabled.set(False)
        for storage in (self._players, self._last_player, self._recent):
            for key in tuple(storage):
                if key[0] == ctx.guild.id:
                    storage.pop(key, None)
        await ctx.send("⛔ Truth or Dare disabled. Temporary player pools cleared.")

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """Remove a user from any ephemeral opt-in player pools."""
        for key, members in list(self._players.items()):
            members.discard(user_id)
            if not members:
                self._players.pop(key, None)
                self._last_player.pop(key, None)
        for key, last_user_id in list(self._last_player.items()):
            if last_user_id == user_id:
                self._last_player.pop(key, None)

    def cog_unload(self):
        self._players.clear()
        self._last_player.clear()
        self._recent.clear()
