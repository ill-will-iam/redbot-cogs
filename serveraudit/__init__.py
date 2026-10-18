"""Read-only Discord guild auditor."""
from .serveraudit import ServerAudit


async def setup(bot):
    await bot.add_cog(ServerAudit(bot))
