"""Per-guild automatic roles for new human members of Red-DiscordBot."""

from __future__ import annotations

import logging

import discord
from redbot.core import Config, commands

log = logging.getLogger("red.autorole")

MAX_ROLES = 10


class AutoRole(commands.Cog):
    """Give configured roles to joining members automatically and silently."""

    __author__ = "Will"
    __version__ = "1.0.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=7610192026, force_registration=True)
        self.config.register_guild(role_ids=[], enabled=True)

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No individual user data is stored."""
        return

    @staticmethod
    def _can_assign(guild: discord.Guild, role: discord.Role) -> bool:
        me = guild.me
        return bool(
            me
            and me.guild_permissions.manage_roles
            and not role.is_default()
            and not role.managed
            and role < me.top_role
        )

    @staticmethod
    def _safe_role(role: discord.Role) -> bool:
        """Never auto-grant staff privileges to everybody who joins."""
        perms = role.permissions
        return not any((
            perms.administrator,
            perms.manage_guild,
            perms.manage_roles,
            perms.manage_channels,
            perms.manage_webhooks,
            perms.kick_members,
            perms.ban_members,
            perms.moderate_members,
        ))

    async def _grant(self, member: discord.Member) -> None:
        if member.bot or member.pending:
            return  # Leave bots alone; respect Discord's rules-screening gate.
        guild = member.guild
        if not await self.config.guild(guild).enabled():
            return
        ids = await self.config.guild(guild).role_ids()
        if not ids:
            return

        roles = []
        for role_id in ids:
            role = guild.get_role(int(role_id))
            if (
                role is not None
                and role not in member.roles
                and self._can_assign(guild, role)
                and self._safe_role(role)
            ):
                roles.append(role)

        if not roles:
            return

        try:
            await member.add_roles(
                *roles,
                reason="AutoRole: automatic member join assignment",
                atomic=True,
            )
        except (discord.Forbidden, discord.HTTPException):
            log.exception(
                "Could not apply join roles in guild %s to member %s",
                guild.id,
                member.id,
            )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        await self._grant(member)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        # Grant only after Membership Screening is completed, if enabled.
        if before.pending and not after.pending:
            await self._grant(after)

    async def _show(self, ctx: commands.Context) -> None:
        data = await self.config.guild(ctx.guild).all()
        names = []
        for role_id in data["role_ids"]:
            role = ctx.guild.get_role(int(role_id))
            names.append(role.mention if role else f"(deleted role ID {role_id})")
        lines = "\n".join(f"- {name}" for name in names) if names else "No roles configured."
        state = "ON" if data["enabled"] else "OFF"
        await ctx.send(
            f"**Automatic join roles: {state}**\n{lines}\n"
            f"Configure with `{ctx.clean_prefix}autorole add @Role` or "
            f"`{ctx.clean_prefix}autorole remove @Role`.\n"
            "New human members only; rules-screening completion is respected.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.group(name="autorole", invoke_without_command=True)
    @commands.guild_only()
    @commands.admin_or_permissions(manage_roles=True)
    async def autorole(self, ctx: commands.Context) -> None:
        """Configure roles assigned to each new human member."""
        await self._show(ctx)

    @autorole.command(name="add")
    async def autorole_add(self, ctx: commands.Context, role: discord.Role) -> None:
        """Automatically grant this role to new members. Example: [p]autorole add @Member"""
        if not self._safe_role(role):
            await ctx.send("That role has staff powers and cannot be assigned automatically.")
            return
        if not self._can_assign(ctx.guild, role):
            await ctx.send(
                "I cannot assign that role. Grant me **Manage Roles** and move my "
                "highest role above it in Server Settings → Roles."
            )
            return

        async with self.config.guild(ctx.guild).role_ids() as ids:
            if role.id in ids:
                outcome = f"{role.mention} is already configured."
            elif len(ids) >= MAX_ROLES:
                outcome = f"Maximum of {MAX_ROLES} automatic roles per server."
            else:
                ids.append(role.id)
                outcome = f"New members will automatically receive {role.mention}."
        await ctx.send(outcome, allowed_mentions=discord.AllowedMentions.none())

    @autorole.command(name="remove")
    async def autorole_remove(self, ctx: commands.Context, role: discord.Role) -> None:
        """Stop assigning this role to future joiners."""
        async with self.config.guild(ctx.guild).role_ids() as ids:
            if role.id in ids:
                ids.remove(role.id)
                found = True
            else:
                found = False
        if found:
            await ctx.send(f"Stopped assigning {role.mention} to new members.", allowed_mentions=discord.AllowedMentions.none())
        else:
            await ctx.send("That role is not configured.")

    @autorole.command(name="list", aliases=["status"])
    async def autorole_list(self, ctx: commands.Context) -> None:
        """Show configured roles and whether assignment is enabled."""
        await self._show(ctx)

    @autorole.command(name="on", aliases=["enable"])
    async def autorole_on(self, ctx: commands.Context) -> None:
        """Enable join assignments."""
        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.send("Automatic join roles enabled.")

    @autorole.command(name="off", aliases=["disable"])
    async def autorole_off(self, ctx: commands.Context) -> None:
        """Disable join assignments without forgetting selected roles."""
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.send("Automatic join roles disabled. Saved roles are unchanged.")

    @autorole.command(name="clear")
    async def autorole_clear(self, ctx: commands.Context) -> None:
        """Remove all configured join roles for this server."""
        await self.config.guild(ctx.guild).role_ids.set([])
        await ctx.send("Cleared all automatic join roles for this server.")
