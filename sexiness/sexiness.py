"""Sexiness: a random, just-for-fun percentage rating."""

from typing import Optional

import discord
from redbot.core import commands

from .scoring import choose_quip, meter, roll_score


class Sexiness(commands.Cog):
    """An entirely unscientific, playful sexiness meter."""

    __author__ = "Will"
    __version__ = "1.0.0"

    @commands.command(name="sexy", aliases=["sexiness"])
    @commands.guild_only()
    async def sexy(
        self,
        ctx: commands.Context,
        member: Optional[discord.Member] = None,
    ):
        """Roll a fresh sexiness percentage for yourself or a mentioned member.

        Examples:
            [p]sexy
            [p]sexy @member
        """
        target = member or ctx.author
        score = roll_score()
        name = discord.utils.escape_markdown(
            discord.utils.escape_mentions(target.display_name)
        )

        await ctx.send(
            f"\U0001f48b **{name}'s Sexiness Rating**\n"
            f"**Sexiness: {score}%**\n"
            f"{meter(score)}\n"
            f"*{choose_quip(score)}*",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """The cog does not collect or persist end-user data."""
        return
