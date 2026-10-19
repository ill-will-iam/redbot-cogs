"""Selective message cleanup for Red-DiscordBot."""

from .purge import Purge


async def setup(bot):
    await bot.add_cog(Purge(bot))
