"""Local image editing for Red-DiscordBot."""

from .imageedit import ImageEdit


async def setup(bot):
    await bot.add_cog(ImageEdit(bot))
