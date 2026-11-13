"""ServerTag v2: tiered Discord tag and boost rewards with role-permission auditing."""

import asyncio
import io
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

import discord
from redbot.core import Config, commands

from ._logic import booster_state, changed_roles, wanted_roles, wearing_guild_tag

log = logging.getLogger("red.servertag")

RESTRICTED_PERMISSIONS = (
    "administrator",
    "manage_roles",
    "manage_guild",
    "manage_channels",
    "ban_members",
    "kick_members",
    "moderate_members",
    "manage_webhooks",
)


class ServerTag(commands.Cog):
    """Safely manage different tag rewards for basic members and boosters."""

    __author__ = "Will"
    __version__ = "2.0.0"

    def __init__(self, bot):
        self.bot = bot
        # Reuse v1's identifier and role_id key so existing tag roles survive upgrades.
        self.config = Config.get_conf(self, identifier=78721092413512, force_registration=True)
        self.config.register_guild(
            enabled=False,
            role_id=None,
            basic_role_id=None,
            boost_role_id=None,
            boost_tag_role_id=None,
            role_snapshot={},
        )
        self._member_locks: Dict[Tuple[int, int], asyncio.Lock] = {}
        self._sync_locks: Dict[int, asyncio.Lock] = {}

    async def red_delete_data_for_user(self, *, requester, user_id):
        """No per-user data is stored by this cog."""
        return

    @staticmethod
    def _manageable(guild: discord.Guild, role: discord.Role) -> bool:
        me = guild.me
        return bool(
            me
            and me.guild_permissions.manage_roles
            and not role.is_default()
            and not role.managed
            and role < me.top_role
        )

    @staticmethod
    def _dangerous(role: discord.Role) -> bool:
        return any(bool(getattr(role.permissions, key, False)) for key in RESTRICTED_PERMISSIONS)

    def _role_issue(self, guild: discord.Guild, role: discord.Role) -> Optional[str]:
        if not self._manageable(guild, role):
            return "I need Manage Roles; the reward role must be unmanaged and below my top role."
        if self._dangerous(role):
            return "That reward role grants moderation or administration privileges. Use a safe reward role."
        return None

    @staticmethod
    def _reward_ids(settings):
        return {
            key: settings.get(key)
            for key in ("role_id", "boost_role_id", "boost_tag_role_id")
            if settings.get(key) is not None
        }

    async def _set_reward(self, ctx, key: str, role: discord.Role, label: str):
        issue = self._role_issue(ctx.guild, role)
        if issue:
            return await ctx.send(issue)
        if ctx.author.id != ctx.guild.owner_id and role >= ctx.author.top_role:
            return await ctx.send("You cannot configure a role at or above your highest role.")
        settings = await self.config.guild(ctx.guild).all()
        used = self._reward_ids(settings)
        if any(existing_key != key and role.id == rid for existing_key, rid in used.items()):
            return await ctx.send("Each reward must use a different role to avoid conflicting assignments.")
        if role.id == settings.get("basic_role_id"):
            return await ctx.send("The reward cannot also be the basic eligibility role.")
        old = settings.get(key)
        await self.config.guild(ctx.guild).set_raw(key, value=role.id)
        await self.config.guild(ctx.guild).enabled.set(True)
        message = (
            f"{label} reward set to {role.mention}. Automation enabled. "
            f"Run {ctx.clean_prefix}tagrole sync to update everyone."
        )
        if old and old != role.id:
            message += " The previously configured role is not automatically stripped."
        await ctx.send(message)

    @staticmethod
    def _capture_roles(guild: discord.Guild):
        """Record guild-role permissions and explicit channel overwrites by role ID."""
        roles = {}
        for role in guild.roles:
            overwrites = {}
            for channel in guild.channels:
                override = channel.overwrites.get(role)
                if override is not None:
                    allow, deny = override.pair()
                    overwrites[str(channel.id)] = {"allow": allow.value, "deny": deny.value}
            roles[str(role.id)] = {
                "name": role.name,
                "position": role.position,
                "permissions": role.permissions.value,
                "managed": role.managed,
                "hoist": role.hoist,
                "mentionable": role.mentionable,
                "overwrites": overwrites,
            }
        return {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "guild_id": guild.id,
            "roles": roles,
        }

    async def _reconcile_record(self, guild: discord.Guild, raw: dict):
        """Reconcile only configured custom rewards using the latest observed state."""
        if not await self.config.guild(guild).enabled():
            return "disabled"
        if await self.bot.cog_disabled_in_guild(self, guild):
            return "disabled"

        user = raw.get("user") or {}
        if user.get("bot"):
            return "skipped"
        try:
            user_id = int(user["id"])
            current_ids = {int(role_id) for role_id in raw["roles"]}
        except (TypeError, ValueError, KeyError):
            return "unknown"

        settings = await self.config.guild(guild).all()
        configured = self._reward_ids(settings)
        if not configured:
            return "unavailable"

        primary = user.get("primary_guild", ...)
        tag_state = (
            wearing_guild_tag(primary, guild.id) if primary is not ... else None
        )
        premium_role = guild.premium_subscriber_role
        boosting = booster_state(raw, premium_role.id if premium_role else None)
        basic_id = settings.get("basic_role_id")
        has_basic = basic_id is None or basic_id == guild.id or basic_id in current_ids

        wanted = wanted_roles(
            tag_state,
            boosting,
            has_basic,
            settings.get("role_id"),
            settings.get("boost_tag_role_id"),
            settings.get("boost_role_id"),
        )
        if not wanted:
            return "unknown"

        lock = self._member_locks.setdefault((guild.id, user_id), asyncio.Lock())
        async with lock:
            # Fetch a fresh role list only if an update is needed. Avoid stale
            # member caches, especially for members fetched during bulk sync.
            changes = []
            failures = 0
            for role_id, desired in wanted.items():
                role = guild.get_role(role_id)
                if role is None or self._role_issue(guild, role):
                    failures += 1
                    continue
                if (role_id in current_ids) != desired:
                    changes.append((role, desired))

            if not changes:
                return "unavailable" if failures else "unchanged"

            try:
                member = await guild.fetch_member(user_id)
            except discord.NotFound:
                return "unavailable"
            except (discord.Forbidden, discord.HTTPException):
                log.exception("Could not fetch member %s in guild %s", user_id, guild.id)
                return "failed"

            applied = []
            for role, desired in changes:
                # Re-evaluate actual role possession after fetching the member.
                has = role in member.roles
                if has == desired:
                    continue
                try:
                    if desired:
                        await member.add_roles(role, reason="ServerTag: tag/boost reward granted")
                        applied.append("added")
                    else:
                        await member.remove_roles(role, reason="ServerTag: tag/boost reward revoked")
                        applied.append("removed")
                except (discord.Forbidden, discord.HTTPException):
                    log.exception("Failed to manage role %s for user %s", role.id, user_id)
                    failures += 1
            if failures:
                return "failed"
            if not applied:
                return "unchanged"
            return "updated" if len(applied) > 1 or len(set(applied)) > 1 else applied[0]

    async def _refresh(self, guild, user_id):
        try:
            payload = await self.bot.http.get_member(guild.id, user_id)
        except discord.NotFound:
            return "unavailable"
        except (discord.Forbidden, discord.HTTPException):
            log.exception("Could not retrieve member %s for tag/boost check", user_id)
            return "failed"
        return await self._reconcile_record(guild, payload)

    @commands.Cog.listener()
    async def on_socket_response(self, event):
        if not isinstance(event, dict) or event.get("t") != "GUILD_MEMBER_UPDATE":
            return
        payload = event.get("d")
        if not isinstance(payload, dict):
            return
        try:
            guild_id = int(payload["guild_id"])
        except (ValueError, TypeError, KeyError):
            return
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        # The Gateway event carries user.primary_guild and premium_since.
        # Missing tag data is never treated as tag removal.
        await self._reconcile_record(guild, payload)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self._refresh(member.guild, member.id)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """A second route for booster / basic eligibility changes."""
        settings = await self.config.guild(after.guild).all()
        if not settings.get("enabled"):
            return
        premium_role = after.guild.premium_subscriber_role
        boost_role_changed = (
            premium_role is not None
            and ((premium_role in before.roles) != (premium_role in after.roles))
        )
        basic_id = settings.get("basic_role_id")
        basic_changed = (
            basic_id is not None
            and ((basic_id in {r.id for r in before.roles}) != (basic_id in {r.id for r in after.roles}))
        )
        if before.premium_since != after.premium_since or boost_role_changed or basic_changed:
            await self._refresh(after.guild, after.id)

    @commands.group(name="tagrole", aliases=["servertag"], invoke_without_command=True)
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def tagrole(self, ctx: commands.Context):
        """Configure tag and boost rewards and audit existing role permissions."""
        await ctx.send_help()

    @tagrole.command(name="setrole")
    async def tagrole_setrole(self, ctx: commands.Context, role: discord.Role):
        """Set the normal server-tag reward (also used by v1)."""
        await self._set_reward(ctx, "role_id", role, "Basic tag")

    @tagrole.command(name="setboostrole")
    async def tagrole_setboostrole(self, ctx: commands.Context, role: discord.Role):
        """Set a custom role awarded while boosting, whether tagged or not."""
        await self._set_reward(ctx, "boost_role_id", role, "Booster")

    @tagrole.command(name="setboosttagrole")
    async def tagrole_setboosttagrole(self, ctx: commands.Context, role: discord.Role):
        """Set upgraded tag reward while boosting; replaces basic tag reward."""
        await self._set_reward(ctx, "boost_tag_role_id", role, "Booster tag")

    @tagrole.command(name="setbaserole")
    async def tagrole_setbaserole(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        """Require a basic membership role for non-boosters to earn the tag reward.

        Run without a role to allow all basic members.
        """
        settings = await self.config.guild(ctx.guild).all()
        if role and role.id in self._reward_ids(settings).values():
            return await ctx.send("The basic eligibility role cannot also be a reward role.")
        await self.config.guild(ctx.guild).basic_role_id.set(role.id if role else None)
        await ctx.send(
            f"Basic membership requirement: {role.mention if role else 'any member'}. "
            f"Run {ctx.clean_prefix}tagrole sync."
        )

    @tagrole.command(name="unsetboostrole")
    async def tagrole_unsetboostrole(self, ctx: commands.Context):
        """Disable booster-only reward without removing already-assigned old roles."""
        await self.config.guild(ctx.guild).boost_role_id.set(None)
        await ctx.send("Booster-only reward unset. Existing assignments remain until manually cleaned.")

    @tagrole.command(name="unsetboosttagrole")
    async def tagrole_unsetboosttagrole(self, ctx: commands.Context):
        """Disable upgraded booster-tag reward; use standard tag reward for boosters."""
        await self.config.guild(ctx.guild).boost_tag_role_id.set(None)
        await ctx.send("Booster tag upgrade unset. Old upgraded roles must be cleaned manually.")

    @tagrole.command(name="status")
    async def tagrole_status(self, ctx: commands.Context):
        """Show configured roles and the last permission snapshot."""
        settings = await self.config.guild(ctx.guild).all()
        def fmt(key):
            role_id = settings.get(key)
            if not role_id:
                return "Not set"
            role = ctx.guild.get_role(role_id)
            if not role:
                return f"Deleted role ({role_id})"
            return f"{role.mention} ({'safe' if not self._role_issue(ctx.guild, role) else 'NOT SAFE/UNMANAGEABLE'})"
        audit = settings.get("role_snapshot") or {}
        await ctx.send(
            f"**ServerTag v2** — {'Enabled' if settings['enabled'] else 'Disabled'}\n"
            f"Basic eligibility: {fmt('basic_role_id') if settings.get('basic_role_id') else 'All members'}\n"
            f"Basic tag reward: {fmt('role_id')}\n"
            f"Booster reward (tag not required): {fmt('boost_role_id')}\n"
            f"Booster + tag upgrade: {fmt('boost_tag_role_id')}\n"
            f"Role snapshot: {audit.get('captured_at', 'Not taken')}\n"
            "Built-in Discord boost role is never modified."
        )

    @tagrole.command(name="enable")
    async def tagrole_enable(self, ctx: commands.Context):
        """Start using all configured reward rules."""
        settings = await self.config.guild(ctx.guild).all()
        rewards = self._reward_ids(settings)
        if not rewards:
            return await ctx.send("Configure at least one reward first.")
        for role_id in rewards.values():
            role = ctx.guild.get_role(role_id)
            if role is None or self._role_issue(ctx.guild, role):
                return await ctx.send("A configured reward role is missing or unsafe. Check tagrole status.")
        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.send("Tag and booster reward automation enabled.")

    @tagrole.command(name="disable")
    async def tagrole_disable(self, ctx: commands.Context):
        """Pause automated role changes without stripping existing roles."""
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.send("Tag and booster rewards disabled; current member roles were kept.")

    @tagrole.command(name="clear")
    async def tagrole_clear(self, ctx: commands.Context):
        """Clear automation rules but retain saved permissions snapshot."""
        g = self.config.guild(ctx.guild)
        await g.enabled.set(False)
        for key in ("role_id", "boost_role_id", "boost_tag_role_id", "basic_role_id"):
            await g.set_raw(key, value=None)
        await ctx.send("Reward configuration cleared. Current roles and permission snapshot remain intact.")

    @tagrole.command(name="roles")
    async def tagrole_roles(self, ctx: commands.Context):
        """List every server role, permission flags, and potential privileges."""
        lines = [f"Guild: {ctx.guild.name} ({ctx.guild.id})", f"Roles: {len(ctx.guild.roles)}", ""]
        for role in reversed(ctx.guild.roles):
            active = [name for name, value in role.permissions if value]
            danger = [name for name in active if name in RESTRICTED_PERMISSIONS]
            lines.append(
                f"{role.position:>3} | {role.name} | ID={role.id} | "
                f"managed={role.managed} | bot_manageable={self._manageable(ctx.guild, role)}\n"
                f"    enabled permissions: {', '.join(active) or '(none)'}\n"
                f"    sensitive permissions: {', '.join(danger) or '(none)'}"
            )
        content = "\n".join(lines).encode("utf-8")
        await ctx.send(
            f"Audited {len(ctx.guild.roles)} roles. Nothing was modified.",
            file=discord.File(io.BytesIO(content), filename="servertag_roles.txt"),
        )

    @tagrole.command(name="snapshot")
    async def tagrole_snapshot(self, ctx: commands.Context):
        """Save the current role permissions and channel-level role overwrites."""
        data = self._capture_roles(ctx.guild)
        await self.config.guild(ctx.guild).role_snapshot.set(data)
        await ctx.send(
            f"Saved a read-only snapshot of {len(data['roles'])} roles, "
            "including guild permissions and explicit channel overwrites."
        )

    @tagrole.command(name="diff")
    async def tagrole_diff(self, ctx: commands.Context):
        """Compare current role permissions with the stored snapshot."""
        old = await self.config.guild(ctx.guild).role_snapshot()
        if not old:
            return await ctx.send("No snapshot stored. Run tagrole snapshot first.")
        new = self._capture_roles(ctx.guild)
        diff = changed_roles(old, new)
        if not diff:
            return await ctx.send("No role, role-permission, or channel-overwrite changes since snapshot.")
        await ctx.send(
            f"Found {len(diff)} changes since {old.get('captured_at', 'the snapshot')}.",
            file=discord.File(
                io.BytesIO(("\n".join(diff) + "\n").encode("utf-8")),
                filename="servertag_permission_diff.txt",
            ),
        )

    @tagrole.command(name="exportsnapshot")
    async def tagrole_exportsnapshot(self, ctx: commands.Context):
        """Download the stored role-permission snapshot as JSON."""
        data = await self.config.guild(ctx.guild).role_snapshot()
        if not data:
            return await ctx.send("No snapshot stored. Run tagrole snapshot first.")
        raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        await ctx.send(file=discord.File(io.BytesIO(raw), filename="servertag_roles_snapshot.json"))

    @tagrole.command(name="check")
    async def tagrole_check(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Correct all of a member's tag/booster rewards using fresh Discord data."""
        member = member or ctx.author
        result = await self._refresh(ctx.guild, member.id)
        await ctx.send(f"{member.mention}: reconciliation result: **{result}**.")

    @tagrole.command(name="sync")
    async def tagrole_sync(self, ctx: commands.Context):
        """Reconcile existing members in bulk; respects Discord API rate limits."""
        settings = await self.config.guild(ctx.guild).all()
        if not settings["enabled"] or not self._reward_ids(settings):
            return await ctx.send("Configure a reward role and enable the cog first.")
        lock = self._sync_locks.setdefault(ctx.guild.id, asyncio.Lock())
        if lock.locked():
            return await ctx.send("A ServerTag sync is already running here.")
        await ctx.send("Reconciling tag and booster reward roles using Discord member data...")
        counts = {key: 0 for key in ("checked", "added", "removed", "updated", "unchanged", "unknown", "failed", "unavailable", "skipped", "disabled")}
        async with lock:
            try:
                after = None
                while True:
                    batch = await self.bot.http.get_members(ctx.guild.id, 1000, after)
                    if not batch:
                        break
                    ids = []
                    for raw in batch:
                        try:
                            uid = int(raw["user"]["id"])
                        except (KeyError, TypeError, ValueError):
                            continue
                        ids.append(uid)
                        if raw["user"].get("bot"):
                            continue
                        counts["checked"] += 1
                        result = await self._reconcile_record(ctx.guild, raw)
                        if result in counts:
                            counts[result] += 1
                    if not ids:
                        break
                    after = max(ids)
                    if len(batch) < 1000:
                        break
            except (discord.Forbidden, discord.HTTPException):
                log.exception("ServerTag sync aborted for guild %s", ctx.guild.id)
                await ctx.send("Sync interrupted by a Discord API error; partial results may have been applied.")
                return
        await ctx.send(
            "**ServerTag sync finished:** "
            + ", ".join(f"{key}={value}" for key, value in counts.items() if value or key == "checked")
        )
