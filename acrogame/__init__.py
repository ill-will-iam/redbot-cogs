from .acrogame import AcroGame


async def setup(bot):
    await bot.add_cog(AcroGame(bot))
