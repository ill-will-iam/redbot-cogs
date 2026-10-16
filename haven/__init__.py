from .haven import Haven


async def setup(bot):
    await bot.add_cog(Haven(bot))
