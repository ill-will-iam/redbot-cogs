from .dig import Dig


async def setup(bot):
    await bot.add_cog(Dig(bot))
