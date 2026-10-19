"""Timed, channel-local social line-up command for Red-DiscordBot."""

import asyncio
from dataclasses import dataclass, field
from typing import Dict, Optional, Set, Tuple

import discord
from redbot.core import commands

JOIN_WINDOW_SECONDS = 45
COUNTDOWN_TICK_SECONDS = 1


@dataclass
class LineRound:
    channel: discord.abc.Messageable
    participants: Set[int] = field(default_factory=set)
    accepting: bool = True
    task: Optional[asyncio.Task] = None


def display_name(member: discord.Member) -> str:
    """Render a visible, bold @name without triggering a Discord mention."""
    safe_name = discord.utils.escape_mentions(
        discord.utils.escape_markdown(member.display_name)
    )
    return f"**@{safe_name}**"


class Line(commands.Cog):
    """Line up together for 45 seconds, then raise a toast."""

    __author__ = "Will"
    __version__ = "1.0.0"

    def __init__(self):
        self._rounds: Dict[Tuple[int, int], LineRound] = {}
        self._lock = asyncio.Lock()

    def cog_unload(self):
        """Stop outstanding countdowns when the cog is unloaded/reloaded."""
        for round_ in self._rounds.values():
            if round_.task is not None:
                round_.task.cancel()
        self._rounds.clear()

    @commands.command(name="line")
    @commands.guild_only()
    @commands.bot_has_permissions(send_messages=True)
    async def line(self, ctx: commands.Context):
        """Start a 45-second line, or join the one in this channel."""
        key = (ctx.guild.id, ctx.channel.id)
        name = display_name(ctx.author)
        no_pings = discord.AllowedMentions.none()

        async with self._lock:
            round_ = self._rounds.get(key)
            if round_ is None:
                await ctx.send(
                    f"{name} is lining up! "
                    f"Join them with `{ctx.clean_prefix}line` and get lifted.",
                    allowed_mentions=no_pings,
                )
                round_ = LineRound(channel=ctx.channel)
                round_.participants.add(ctx.author.id)
                self._rounds[key] = round_
                round_.task = asyncio.create_task(self._finish_round(key, round_))
                return

            if not round_.accepting:
                await ctx.send(
                    "The countdown has started! A new line can begin shortly.",
                    allowed_mentions=no_pings,
                )
                return

            if ctx.author.id in round_.participants:
                await ctx.send(f"{name} is already in line!", allowed_mentions=no_pings)
                return

            await ctx.send(f"{name} is lining up a fatty!", allowed_mentions=no_pings)
            round_.participants.add(ctx.author.id)

    async def _finish_round(self, key: Tuple[int, int], round_: LineRound):
        """Close signups after 45 seconds, count down 3 seconds, and finish."""
        try:
            await asyncio.sleep(JOIN_WINDOW_SECONDS)
            async with self._lock:
                if self._rounds.get(key) is not round_:
                    return
                round_.accepting = False

            for remaining in (3, 2, 1):
                await round_.channel.send(
                    f"**{remaining}...**", allowed_mentions=discord.AllowedMentions.none()
                )
                await asyncio.sleep(COUNTDOWN_TICK_SECONDS)

            await round_.channel.send(
                "🥂 **Cheers, enjoy!** 🥂",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.HTTPException, discord.Forbidden):
            # Missing channel/permissions: end this round without a stuck session.
            pass
        finally:
            async with self._lock:
                if self._rounds.get(key) is round_:
                    del self._rounds[key]

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """Remove a user from temporary active line rosters, if present."""
        async with self._lock:
            for round_ in self._rounds.values():
                round_.participants.discard(user_id)
