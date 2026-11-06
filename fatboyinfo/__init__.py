from .fatboyinfo import FatboyInfo

__red_end_user_data_statement__ = "This cog stores only bot-owner-configured public profile text, color, and an alias setting. It does not store Discord user data."


async def setup(bot):
    cog = FatboyInfo(bot)
    await bot.add_cog(cog)
    await cog.activate_info_alias()
