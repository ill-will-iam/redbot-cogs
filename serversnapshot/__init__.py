from .serversnapshot import ServerSnapshot


async def setup(bot):
    await bot.add_cog(ServerSnapshot(bot))
