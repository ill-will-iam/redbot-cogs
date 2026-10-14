"""A silly, random sanity check for Red-DiscordBot."""

from .sanity import Sanity


async def setup(bot):
    await bot.add_cog(Sanity())
