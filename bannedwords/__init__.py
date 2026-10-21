"""Persistent server-wide opt-in Banned Word Game for Red-DiscordBot."""
from .bannedwords import BannedWords

async def setup(bot):
    await bot.add_cog(BannedWords(bot))
