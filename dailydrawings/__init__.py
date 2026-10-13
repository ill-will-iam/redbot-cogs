from .dailydrawings import DailyDrawings

__red_end_user_data_statement__ = (
    "Stores per-server channel and schedule settings, daily topic rotation, and "
    "the current drawing round for restart recovery. Active rounds contain "
    "entrant/voter Discord IDs, submission and ballot message IDs, attachment "
    "IDs/URLs and vote choices. These records clear when a round ends or is "
    "cancelled. No image files, leaderboard or win history are stored locally. "
    "User-data deletion cancels affected rounds and clears their stored state. "
    "Already posted Discord photos, gallery posts and announcements remain."
)


async def setup(bot):
    await bot.add_cog(DailyDrawings(bot))
