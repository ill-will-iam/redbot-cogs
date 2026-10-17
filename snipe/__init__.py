"""Recent deleted message viewer for Red-DiscordBot."""

from .snipe import Snipe


async def setup(bot):
    await bot.add_cog(Snipe(bot))
