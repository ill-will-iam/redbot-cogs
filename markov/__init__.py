from .markov import Markov

async def setup(bot):
    cog = Markov(bot)
    await bot.add_cog(cog)
