"""Owner-only, self-service role controls for Red-DiscordBot 3.5+."""

import discord
from redbot.core import commands


class RoleControl(commands.Cog):
    """Let FATBOY's owner add or remove roles on their own account."""

    def __init__(self, bot):
        self.bot = bot

    async def _validate_role(self, ctx, role: discord.Role) -> bool:
        """Check that the requested role can actually be managed by this bot."""
        if role.is_default():
            await ctx.send("The @everyone role cannot be assigned or removed.")
            return False

        if role.managed:
            await ctx.send("That role is managed by a Discord integration and cannot be changed manually.")
            return False

        bot_member = ctx.guild.me
        if bot_member is None:
            try:
                bot_member = await ctx.guild.fetch_member(self.bot.user.id)
            except (discord.Forbidden, discord.HTTPException, AttributeError):
                await ctx.send("I couldn't check my role hierarchy in this server.")
                return False

        if role >= bot_member.top_role:
            await ctx.send(
                "I can't manage that role. Move FATBOY's highest role above "
                "the requested role in **Server Settings → Roles**."
            )
            return False

        return True

    @commands.command(name="roleme", aliases=["giverole"])
    @commands.guild_only()
    @commands.is_owner()
    @commands.bot_has_guild_permissions(manage_roles=True)
    async def roleme(self, ctx, *, role: discord.Role):
        """Give yourself a role: [p]roleme <role name, ID, or mention>."""
        member = ctx.author
        if role in member.roles:
            await ctx.send(f"You already have **{discord.utils.escape_markdown(role.name)}**.")
            return

        if not await self._validate_role(ctx, role):
            return

        try:
            await member.add_roles(role, reason=f"Self-assigned by bot owner ({member.id})")
        except discord.Forbidden:
            await ctx.send("Discord denied that role change. Check my Manage Roles permission and role position.")
        except discord.HTTPException:
            await ctx.send("Discord couldn't assign that role. Try again shortly.")
        else:
            await ctx.send(f"Added **{discord.utils.escape_markdown(role.name)}** to your roles.")

    @commands.command(name="unroleme", aliases=["removemyrole"])
    @commands.guild_only()
    @commands.is_owner()
    @commands.bot_has_guild_permissions(manage_roles=True)
    async def unroleme(self, ctx, *, role: discord.Role):
        """Remove one of your roles: [p]unroleme <role name, ID, or mention>."""
        member = ctx.author
        if role not in member.roles:
            await ctx.send(f"You don't have **{discord.utils.escape_markdown(role.name)}**.")
            return

        if not await self._validate_role(ctx, role):
            return

        try:
            await member.remove_roles(role, reason=f"Self-removed by bot owner ({member.id})")
        except discord.Forbidden:
            await ctx.send("Discord denied that role change. Check my Manage Roles permission and role position.")
        except discord.HTTPException:
            await ctx.send("Discord couldn't remove that role. Try again shortly.")
        else:
            await ctx.send(f"Removed **{discord.utils.escape_markdown(role.name)}** from your roles.")

    @commands.command(name="myroles")
    @commands.guild_only()
    @commands.is_owner()
    async def myroles(self, ctx):
        """Show your server roles, highest first."""
        roles = sorted(
            (r for r in ctx.author.roles if not r.is_default()),
            reverse=True,
        )
        if not roles:
            await ctx.send("You have no roles besides @everyone in this server.")
            return

        lines = [f"• {discord.utils.escape_markdown(r.name)} (`{r.id}`)" for r in roles]
        # Split into several messages so a user with many roles stays under Discord's limit.
        current = "**Your server roles:**"
        for line in lines:
            if len(current) + len(line) + 1 > 1900:
                await ctx.send(current, allowed_mentions=discord.AllowedMentions.none())
                current = "**Your server roles (continued):**"
            current += "\n" + line
        await ctx.send(current, allowed_mentions=discord.AllowedMentions.none())
