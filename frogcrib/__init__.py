from .frogcrib import FrogCrib


async def setup(bot):
    await bot.add_cog(FrogCrib(bot))
