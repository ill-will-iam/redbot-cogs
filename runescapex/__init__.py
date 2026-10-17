from .runescapex import RuneScapeX


async def setup(bot):
    await bot.add_cog(RuneScapeX(bot))
