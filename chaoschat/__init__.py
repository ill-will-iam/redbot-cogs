"""ChaosChat: spontaneous, absurd conversation for Red-DiscordBot."""

from .chaoschat import ChaosChat


async def setup(bot):
    await bot.add_cog(ChaosChat(bot))
