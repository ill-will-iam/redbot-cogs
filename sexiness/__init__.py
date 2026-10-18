"""Red-DiscordBot Sexiness cog."""

from .sexiness import Sexiness


async def setup(bot):
    await bot.add_cog(Sexiness())
