import random

from redbot.core import commands


class PP(commands.Cog):
    """Send pp1, zero to seven pp2 emojis, and pp3 without gaps."""

    @commands.command()
    @commands.guild_only()
    @commands.bot_has_permissions(send_messages=True)
    async def pp(self, ctx):
        """Send the server's pp emojis with a random middle length."""
        emojis = {
            name: next(
                (emoji for emoji in ctx.guild.emojis
                 if emoji.name == name and emoji.is_usable()),
                None,
            )
            for name in ("pp1", "pp2", "pp3")
        }
        missing = [name for name, emoji in emojis.items() if emoji is None]
        if missing:
            await ctx.send(
                "Missing or unavailable server emojis: "
                + ", ".join(f":{name}:" for name in missing)
            )
            return

        count = random.randint(0, 7)
        await ctx.send(
            str(emojis["pp1"]) + str(emojis["pp2"]) * count + str(emojis["pp3"])
        )
