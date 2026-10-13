from .ribbit import Ribbit


async def setup(bot):
    await bot.add_cog(Ribbit(bot))
