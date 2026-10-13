from .adminlog import AdminLog


async def setup(bot):
    await bot.add_cog(AdminLog(bot))
