import random

import discord
from redbot.core import commands


EMOJI_NAMES = ("pp1", "pp2", "pp3")


def find_pp_emojis(server_emojis):
    """Resolve shortcode names without depending on member/role caches."""
    found = {}
    for emoji in server_emojis:
        name = emoji.name.strip(":").casefold()
        if name in EMOJI_NAMES and name not in found:
            found[name] = emoji
    return found


class PP(commands.Cog):
    """Send :pp1:, zero to seven :pp2: emojis, and :pp3: without gaps."""

    @commands.command()
    @commands.guild_only()
    @commands.bot_has_permissions(send_messages=True)
    async def pp(self, ctx):
        """Send the server's pp emojis with a random middle length."""
        emojis = find_pp_emojis(ctx.guild.emojis)
        if any(name not in emojis for name in EMOJI_NAMES):
            # Query Discord itself if the gateway emoji cache is incomplete.
            try:
                emojis = find_pp_emojis(await ctx.guild.fetch_emojis())
            except discord.HTTPException:
                await ctx.send(
                    "I couldn't retrieve this server's emojis from Discord. "
                    "Please try $pp again."
                )
                return

        missing = [name for name in EMOJI_NAMES if name not in emojis]
        if missing:
            await ctx.send(
                "Discord's emoji list for this server is missing: "
                + ", ".join(f":{name}:" for name in missing)
                + ". Check that these are uploaded to this server, "
                "rather than available through another server's Nitro emojis."
            )
            return

        count = random.randint(0, 7)
        # str(Emoji) includes the colons AND the ID required by Discord:
        # <:pp1:123...> for static emojis or <a:pp1:123...> for animated ones.
        await ctx.send(
            str(emojis["pp1"]) + str(emojis["pp2"]) * count + str(emojis["pp3"])
        )
