"""Timed social line-up cog for Red-DiscordBot."""

from .line import Line


async def setup(bot):
    await bot.add_cog(Line())
