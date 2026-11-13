"""ServerTag: assign and revoke roles based on Discord Server Tags."""
from .servertag import ServerTag


async def setup(bot):
    await bot.add_cog(ServerTag(bot))
