from .frogpond import FrogPond

__red_end_user_data_statement__ = (
    "Stores Discord user IDs with per-server points and solved-puzzle counts. "
    "Active games keep the starter ID and player scores in memory, cleared on "
    "stop, reload or restart. Guess text is neither archived nor deleted. "
    "Data deletion cancels affected games and removes the user's stored scores. "
    "Already posted Discord game messages are not removed."
)


async def setup(bot):
    await bot.add_cog(FrogPond(bot))
