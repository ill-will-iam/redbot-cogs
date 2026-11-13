"""Red-DiscordBot cog that rewards wearing the guild's Server Tag."""

import asyncio
import logging
from typing import Dict, Optional, Tuple

import discord
from redbot.core import Config, commands

from ._logic import wearing_guild_tag

log = logging.getLogger("red.servertag")


class ServerTag(commands.Cog):
    """Give a role while someone displays this server's Discord Server Tag."""

    __author__ = "Will"
    __version__ = "1.0.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=78721092413512, force_registration=True)
        self.config.register_guild(enabled=False, role_id=None)
        self._user_locks: Dict[Tuple[int, int], asyncio.Lock] = {}
        self._sync_locks: Dict[int, asyncio.Lock] = {}

    async def _guild_configuration(self, guild: discord.Guild) -> Optional[discord.Role]:
        settings = await self.config.guild(guild).all()
        if not settings["enabled"] or not settings["role_id"]:
            return None
        return guild.get_role(settings["role_id"])

    @staticmethod
    def _role_manageable(guild: discord.Guild, role: discord.Role) -> bool:
        me = guild.me
        return bool(
            me
            and me.guild_permissions.manage_roles
            and not role.is_default()
            and not role.managed
            and role < me.top_role
        )

    async def _reconcile(
        self,
        guild: discord.Guild,
        user_id: int,
        primary_guild,
        known_role_ids=None,
    ) -> str:
        """Apply one user's tag state. Never remove for absent/unknown data."""
        wearing = wearing_guild_tag(primary_guild, guild.id)
        if wearing is None:
            return "unknown"
        if not await self.config.guild(guild).enabled():
            return "disabled"
        role = await self._guild_configuration(guild)
        if role is None or not self._role_manageable(guild, role):
            return "unavailable"
        if await self.bot.cog_disabled_in_guild(self, guild):
            return "disabled"

        key = (guild.id, user_id)
        lock = self._user_locks.setdefault(key, asyncio.Lock())
        async with lock:
            # Role edits use Discord's atomic per-role endpoint.
            member = guild.get_member(user_id)
            if known_role_ids is not None:
                has_role = role.id in known_role_ids
            elif member is not None:
                has_role = role in member.roles
            else:
                has_role = None

            if has_role is not None and wearing == has_role:
                return "unchanged"

            if member is None:
                try:
                    member = await guild.fetch_member(user_id)
                except discord.NotFound:
                    return "unavailable"
                except (discord.Forbidden, discord.HTTPException):
                    log.exception("Could not fetch member %s in guild %s", user_id, guild.id)
                    return "failed"
                if has_role is None:
                    has_role = role in member.roles
                    if wearing == has_role:
                        return "unchanged"

            try:
                if wearing:
                    await member.add_roles(role, reason="Discord Server Tag equipped")
                    return "added"
                await member.remove_roles(role, reason="Discord Server Tag changed or removed")
                return "removed"
            except (discord.Forbidden, discord.HTTPException):
                log.exception("Could not update Server Tag role for %s in guild %s", user_id, guild.id)
                return "failed"

    @commands.Cog.listener()
    async def on_socket_response(self, payload):
        """Use the raw gateway field even on older discord.py releases."""
        if not isinstance(payload, dict) or payload.get("t") != "GUILD_MEMBER_UPDATE":
            return
        data = payload.get("d")
        if not isinstance(data, dict):
            return
        user = data.get("user")
        if not isinstance(user, dict) or "primary_guild" not in user:
            return  # No server identity data: never guess or strip a role.
        try:
            guild_id = int(data["guild_id"])
            user_id = int(user["id"])
        except (ValueError, TypeError, KeyError):
            return
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        role_ids = data.get("roles")
        known_roles = None
        if isinstance(role_ids, list):
            try:
                known_roles = {int(value) for value in role_ids}
            except (ValueError, TypeError):
                known_roles = None
        await self._reconcile(guild, user_id, user["primary_guild"], known_roles)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Handle newcomers who already display the server's tag."""
        if not await self.config.guild(member.guild).enabled():
            return
        try:
            raw = await self.bot.http.get_member(member.guild.id, member.id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            log.exception("Could not check new member %s", member.id)
            return
        user = raw.get("user", {})
        if "primary_guild" not in user:
            return
        await self._reconcile(
            member.guild,
            member.id,
            user["primary_guild"],
            {int(value) for value in raw.get("roles", [])},
        )

    @commands.group(name="tagrole", aliases=["servertag"], invoke_without_command=True)
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def tagrole(self, ctx: commands.Context):
        """Configure automatic role assignment for this server's Discord tag."""
        await ctx.send_help()

    @tagrole.command(name="setrole")
    async def tagrole_setrole(self, ctx: commands.Context, role: discord.Role):
        """Set the reward role and enable automatic tag-based assignment."""
        if not self._role_manageable(ctx.guild, role):
            return await ctx.send(
                "I need Manage Roles, and the reward role must be an unmanaged "
                "role below my highest role."
            )
        if ctx.author.id != ctx.guild.owner_id and role >= ctx.author.top_role:
            return await ctx.send("You cannot configure a role at or above your highest role.")
        old_id = await self.config.guild(ctx.guild).role_id()
        await self.config.guild(ctx.guild).role_id.set(role.id)
        await self.config.guild(ctx.guild).enabled.set(True)
        message = (
            f"Server Tag rewards enabled: {role.mention}. "
            f"Run {ctx.clean_prefix}tagrole sync to catch up existing members."
        )
        if old_id and old_id != role.id:
            message += " The old reward role was not removed from anyone."
        await ctx.send(message)

    @tagrole.command(name="enable")
    async def tagrole_enable(self, ctx: commands.Context):
        """Enable rewards using the previously selected role."""
        role_id = await self.config.guild(ctx.guild).role_id()
        role = ctx.guild.get_role(role_id) if role_id else None
        if role is None or not self._role_manageable(ctx.guild, role):
            return await ctx.send("Set a manageable role first with tagrole setrole @Role.")
        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.send("Server Tag rewards are enabled. Run tagrole sync if needed.")

    @tagrole.command(name="disable")
    async def tagrole_disable(self, ctx: commands.Context):
        """Pause automatic updates without stripping existing reward roles."""
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.send("Server Tag rewards disabled. Existing assigned roles were left intact.")

    @tagrole.command(name="clear")
    async def tagrole_clear(self, ctx: commands.Context):
        """Forget the configured reward role without changing members' roles."""
        await self.config.guild(ctx.guild).enabled.set(False)
        await self.config.guild(ctx.guild).role_id.set(None)
        await ctx.send("Configuration cleared. Existing assigned roles were left intact.")

    @tagrole.command(name="status")
    async def tagrole_status(self, ctx: commands.Context):
        """Show the current configuration and permissions."""
        enabled = await self.config.guild(ctx.guild).enabled()
        role_id = await self.config.guild(ctx.guild).role_id()
        role = ctx.guild.get_role(role_id) if role_id else None
        valid = role is not None and self._role_manageable(ctx.guild, role)
        await ctx.send(
            f"**Server Tag Role** — {'Enabled' if enabled else 'Disabled'}\n"
            f"Role: {role.mention if role else '(not configured or deleted)'}\n"
            f"Bot can manage role: {'Yes' if valid else 'No'}\n"
            "Checks the server identity's guild ID, not just the 4-character tag text."
        )

    @tagrole.command(name="check")
    async def tagrole_check(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Refresh and correct one member using current Discord API data."""
        member = member or ctx.author
        if not await self.config.guild(ctx.guild).enabled():
            return await ctx.send("Server Tag rewards are disabled. Set a role first.")
        try:
            raw = await self.bot.http.get_member(ctx.guild.id, member.id)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            log.exception("Member check failed")
            return await ctx.send("I couldn't fetch that member from Discord.")
        user = raw.get("user", {})
        if "primary_guild" not in user:
            return await ctx.send("Discord did not provide server identity data. No role was changed.")
        wearing = wearing_guild_tag(user["primary_guild"], ctx.guild.id)
        result = await self._reconcile(
            ctx.guild, member.id, user["primary_guild"], {int(value) for value in raw.get("roles", [])}
        )
        await ctx.send(
            f"{member.mention}: tag {'equipped' if wearing else 'not equipped' if wearing is False else 'unknown'}; "
            f"role action: **{result}**."
        )

    @tagrole.command(name="sync")
    async def tagrole_sync(self, ctx: commands.Context):
        """Audit all members and repair roles using fresh Discord member data."""
        if not await self.config.guild(ctx.guild).enabled():
            return await ctx.send("Server Tag rewards are disabled. Set a role first.")
        role = await self._guild_configuration(ctx.guild)
        if role is None or not self._role_manageable(ctx.guild, role):
            return await ctx.send("The configured role is missing or cannot be managed.")
        lock = self._sync_locks.setdefault(ctx.guild.id, asyncio.Lock())
        if lock.locked():
            return await ctx.send("A Server Tag sync is already running in this server.")
        await ctx.send("Checking current member tags and reconciling reward roles...")
        results = dict(checked=0, added=0, removed=0, unchanged=0, unknown=0, failed=0, unavailable=0)
        try:
            async with lock:
                after = None
                while True:
                    batch = await self.bot.http.get_members(ctx.guild.id, 1000, after)
                    if not batch:
                        break
                    for record in batch:
                        user = record.get("user", {})
                        try:
                            uid = int(user["id"])
                        except (ValueError, KeyError, TypeError):
                            continue
                        if user.get("bot"):
                            continue
                        results["checked"] += 1
                        if "primary_guild" not in user:
                            results["unknown"] += 1
                            continue
                        current_roles = {int(value) for value in record.get("roles", [])}
                        result = await self._reconcile(ctx.guild, uid, user["primary_guild"], current_roles)
                        if result in results:
                            results[result] += 1
                    after = max(int(item["user"]["id"]) for item in batch if "id" in item.get("user", {}))
                    if len(batch) < 1000:
                        break
        except (discord.Forbidden, discord.HTTPException):
            log.exception("Server Tag sync failed for guild %s", ctx.guild.id)
            return await ctx.send("Sync stopped because Discord denied or failed a member-list request.")
        await ctx.send(
            "**Server Tag sync complete** — "
            f"checked {results['checked']}, added {results['added']}, removed {results['removed']}, "
            f"already correct {results['unchanged']}, unknown {results['unknown']}, "
            f"failed {results['failed']}, unavailable {results['unavailable']}."
        )
