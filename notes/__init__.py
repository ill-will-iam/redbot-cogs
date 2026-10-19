"""Staff-only task boards and management memos for Red-DiscordBot."""

from .notes import Notes


async def setup(bot):
    await bot.add_cog(Notes(bot))
