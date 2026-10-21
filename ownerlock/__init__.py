"""Owner-only command-access management for selected Red cogs."""

from .ownerlock import OwnerLock


async def setup(bot):
    await bot.add_cog(OwnerLock(bot))
