from .truthordare import TruthOrDare


async def setup(bot):
    await bot.add_cog(TruthOrDare(bot))
