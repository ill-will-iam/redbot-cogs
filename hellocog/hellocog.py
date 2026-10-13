from redbot.core import commands


class HelloCog(commands.Cog):
    """Check that your cog repository is installed and loaded."""

    @commands.command()
    async def coghello(self, ctx):
        """Send a confirmation that the starter cog works."""
        await ctx.send("Your Red cog repository is working!")

    async def red_delete_data_for_user(self, *, requester: str, user_id: int) -> None:
        """There is no stored user data to delete."""
        return None
