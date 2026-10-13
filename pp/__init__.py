from .pp import PP


async def setup(bot):
    await bot.add_cog(PP())
