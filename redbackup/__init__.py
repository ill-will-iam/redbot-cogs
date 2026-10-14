from .redbackup import RedBackup


async def setup(bot):
    await bot.add_cog(RedBackup(bot))
