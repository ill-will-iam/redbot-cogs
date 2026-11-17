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
    __version__ = "2.2.1"

    def __init__(self, bot):
        self.bot = bot
        # Reuse v1's identifier and role_id key so existing tag roles survive upgrades.
        self.config = Config.get_conf(self, identifier=78721092413512, force_registration=True)
        self.config.register_global(server_id=None)
        self.config.register_guild(
            enabled=False,
            role_id=None,
            basic_role_id=None,
            boost_role_id=None,
            boost_requires_no_tag=False,
            boost_tag_role_id=None,
            role_snapshot={},
            privileged_role_approvals={},
        )
        self._member_locks: Dict[Tuple[int, int], asyncio.Lock] = {}
        self._sync_locks: Dict[int, asyncio.Lock] = {}
        self._binding_lock = asyncio.Lock()

    async def red_delete_data_for_user(self, *, requester, user_id):
        """No per-user data is stored by this cog."""
        return

    async def _in_bound_server(self, guild: Optional[discord.Guild]) -> bool:
        return guild is not None and guild.id == await self.config.server_id()

    async def cog_check(self, ctx: commands.Context) -> bool:
        # Red checks the group before dispatching a subcommand, including bind.
        if ctx.command is self.tagrole or ctx.command is self.tagrole_bind:
            return True
        return await self._check_bound_context(ctx)

    async def _check_bound_context(self, ctx: commands.Context) -> bool:
        if await self._in_bound_server(ctx.guild):
            return True
        if await self.bot.is_owner(ctx.author):
            await ctx.send(
                f"Run `{ctx.clean_prefix}tagrole bind` in the server you want to use."
            )
        return False

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

    def _role_issue(
        self, guild: discord.Guild, role: discord.Role, approvals=None
    ) -> Optional[str]:
        if not self._manageable(guild, role):
            return "I need Manage Roles; the reward role must be unmanaged and below my top role."
        if self._dangerous(role):
            permissions = [
                name for name in RESTRICTED_PERMISSIONS
                if getattr(role.permissions, name, False)
            ]
            if not isinstance(approvals, dict) or (
                approvals.get(str(role.id)) != role.permissions.value
            ):
                return (
                    "That reward role grants elevated permissions: "
                    + ", ".join(permissions)
                    + ". The server owner must explicitly approve it with "
                    + "tagrole approve @Role I_ACCEPT_PRIVILEGES, then retry. "
                    + "Anyone meeting the reward conditions may receive these permissions."
                )
        return None

    @staticmethod
    def _reward_ids(settings):
        return {
            key: settings.get(key)
            for key in ("role_id", "boost_role_id", "boost_tag_role_id")
            if settings.get(key) is not None
        }

    async def _set_reward(
        self, ctx, key: str, role: discord.Role, label: str, *,
        boost_requires_no_tag: bool = False,
    ):
        guild_config = self.config.guild(ctx.guild)
        async with guild_config.all() as settings:
            issue = self._role_issue(
                ctx.guild, role, settings.get("privileged_role_approvals")
            )
            if issue:
                return await ctx.send(issue)
            if ctx.author.id != ctx.guild.owner_id and role >= ctx.author.top_role:
                return await ctx.send("You cannot configure a role at or above your highest role.")
            used = self._reward_ids(settings)
            if any(existing_key != key and role.id == rid for existing_key, rid in used.items()):
                return await ctx.send("Each reward must use a different role.")
            if role.id == settings.get("basic_role_id"):
                return await ctx.send("The reward cannot also be the basic eligibility role.")
            old = settings.get(key)
            settings[key] = role.id
            settings["enabled"] = True
            if key == "boost_role_id":
                settings["boost_requires_no_tag"] = boost_requires_no_tag
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
        """Reconcile the configured custom rewards for one member."""
        if not await self._in_bound_server(guild):
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
        if not settings["enabled"]:
            return "disabled"
        if not configured:
            return "unavailable"

        primary = user.get("primary_guild", ...)
        tag_state = (
            wearing_guild_tag(primary, guild.id) if primary is not ... else None
        )
        premium_role = guild.premium_subscriber_role
        boosting = booster_state(raw, premium_role.id if premium_role else None)
        if boosting is None and premium_role is None:
            boosting = False
        basic_id = settings.get("basic_role_id")
        has_basic = basic_id is None or basic_id == guild.id or basic_id in current_ids

        wanted = wanted_roles(
            tag_state,
            boosting,
            has_basic,
            settings.get("role_id"),
            settings.get("boost_tag_role_id"),
            settings.get("boost_role_id"),
            boost_requires_no_tag=settings["boost_requires_no_tag"],
        )
        if not wanted:
            return "unknown"

        lock = self._member_locks.setdefault((guild.id, user_id), asyncio.Lock())
        queued = lock.locked()
        async with lock:
            if not queued and all(
                (role_id in current_ids) == desired for role_id, desired in wanted.items()
            ):
                return "unchanged"

            try:
                member = await guild.fetch_member(user_id)
            except discord.NotFound:
                return "unavailable"
            except (discord.Forbidden, discord.HTTPException):
                log.exception("Could not fetch member %s in guild %s", user_id, guild.id)
                return "failed"

            current_ids = {role.id for role in member.roles}
            applied = []
            failures = 0
            async with self._binding_lock:
                if not await self._in_bound_server(guild):
                    return "disabled"
                # Revoke the outgoing tier before granting the incoming one.
                for role_id, desired in sorted(wanted.items(), key=lambda item: item[1]):
                    if (role_id in current_ids) == desired:
                        continue
                    role = guild.get_role(role_id)
                    if role is None or not self._manageable(guild, role):
                        failures += 1
                        continue
                    if desired and (
                        (settings["boost_requires_no_tag"] and failures)
                        or self._role_issue(guild, role, settings["privileged_role_approvals"])
                    ):
                        failures += 1
                        continue
                    try:
                        if desired:
                            await member.add_roles(role, reason="ServerTag reward granted")
                            applied.append("added")
                        else:
                            await member.remove_roles(role, reason="ServerTag reward revoked")
                            applied.append("removed")
                    except discord.HTTPException:
                        log.exception("Failed to manage role %s for user %s", role_id, user_id)
                        failures += 1
            if failures:
                return "failed"
            if not applied:
                return "unchanged"
            return "updated" if len(applied) > 1 else applied[0]

    async def _refresh(self, guild, user_id, *, primary_guild=...):
        if not await self._in_bound_server(guild):
            return "disabled"
        if not await self.config.guild(guild).enabled():
            return "disabled"
        try:
            payload = await self.bot.http.get_member(guild.id, user_id)
        except discord.NotFound:
            return "unavailable"
        except (discord.Forbidden, discord.HTTPException):
            log.exception("Could not retrieve member %s for tag/boost check", user_id)
            return "failed"
        if primary_guild is not ...:
            payload["user"].setdefault("primary_guild", primary_guild)
        return await self._reconcile_record(guild, payload)

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        """Respond to changes in the server tag displayed on a user's profile."""
        if after.bot or not hasattr(after, "primary_guild"):
            return
        server_id = await self.config.server_id()
        if server_id is None:
            return
        old, new = before.primary_guild, after.primary_guild
        wore_tag = old.identity_enabled is True and old.id == server_id
        wears_tag = new.identity_enabled is True and new.id == server_id
        if wore_tag == wears_tag:
            return
        guild = self.bot.get_guild(server_id)
        if guild is not None and guild.get_member(after.id) is not None:
            await self._refresh(
                guild, after.id,
                primary_guild={"identity_guild_id": new.id, "identity_enabled": new.identity_enabled},
            )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self._refresh(member.guild, member.id)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Respond to changes in boost status and the basic membership role."""
        if after.bot or not await self._in_bound_server(after.guild):
            return
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
        if (
            before.premium_since != after.premium_since
            or boost_role_changed
            or basic_changed
            or not hasattr(after, "primary_guild")
        ):
            await self._refresh(after.guild, after.id)

    @commands.group(name="tagrole", aliases=["servertag"], invoke_without_command=True)
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def tagrole(self, ctx: commands.Context):
        """Configure tag and boost rewards and audit existing role permissions."""
        if await self._check_bound_context(ctx):
            await ctx.send_help()

    @tagrole.command(name="bind")
    @commands.guild_only()
    @commands.is_owner()
    async def tagrole_bind(self, ctx: commands.Context):
        """Choose the one server where ServerTag can manage rewards."""
        async with self._binding_lock:
            previous = await self.config.server_id()
            await self.config.server_id.set(ctx.guild.id)
        message = f"ServerTag is bound to {ctx.guild.name}."
        if previous is not None and previous != ctx.guild.id:
            message += " Previously assigned rewards in the former server can be removed there manually."
        await ctx.send(message, allowed_mentions=discord.AllowedMentions.none())

    @tagrole.command(name="approve")
    async def tagrole_approve(
        self, ctx: commands.Context, role: discord.Role, confirmation: str = ""
    ):
        """Owner-only: approve one elevated reward role's CURRENT permission bits.

        Usage: tagrole approve @Role I_ACCEPT_PRIVILEGES
        """
        if ctx.author.id != ctx.guild.owner_id:
            return await ctx.send("Only the server owner can approve elevated reward roles.")
        if not self._manageable(ctx.guild, role):
            return await ctx.send(
                "That role is managed by Discord, is @everyone, or sits above my top role."
            )
        if not self._dangerous(role):
            return await ctx.send(
                "That role has no elevated server permissions. Approval is not needed."
            )
        flagged = [
            name for name in RESTRICTED_PERMISSIONS
            if getattr(role.permissions, name, False)
        ]
        if confirmation != "I_ACCEPT_PRIVILEGES":
            return await ctx.send(
                f"{role.mention} grants: {', '.join(flagged)}. "
                "An ordinary member may gain these privileges by equipping "
                "your server tag (and, for the upgraded role, boosting). "
                "To allow this exact role and permission set, the server owner must run "
                f"{ctx.clean_prefix}tagrole approve @Role I_ACCEPT_PRIVILEGES."
            )
        async with self.config.guild(ctx.guild).privileged_role_approvals() as approvals:
            approvals[str(role.id)] = role.permissions.value
        await ctx.send(
            f"Approved {role.mention} with its CURRENT elevated permissions: "
            + ", ".join(flagged)
            + ". Approval expires if the role's guild permission bits change."
        )

    @tagrole.command(name="revokeapproval")
    async def tagrole_revokeapproval(self, ctx: commands.Context, role: discord.Role):
        """Owner-only: stop authorizing new updates to an elevated reward role."""
        if ctx.author.id != ctx.guild.owner_id:
            return await ctx.send("Only the server owner can revoke role approvals.")
        async with self.config.guild(ctx.guild).privileged_role_approvals() as approvals:
            approvals.pop(str(role.id), None)
        await ctx.send(
            f"Approval removed for {role.mention}. "
            "Existing reward-role assignments have not been removed."
        )

    @tagrole.command(name="setrole")
    async def tagrole_setrole(self, ctx: commands.Context, role: discord.Role):
        """Set the normal server-tag reward (also used by v1)."""
        await self._set_reward(ctx, "role_id", role, "Basic tag")

    @tagrole.command(name="setboostrole")
    async def tagrole_setboostrole(self, ctx: commands.Context, role: discord.Role):
        """Set a custom role awarded while boosting, whether tagged or not."""
        await self._set_reward(ctx, "boost_role_id", role, "Booster")

    @tagrole.command(name="setboostonlyrole")
    async def tagrole_setboostonlyrole(self, ctx: commands.Context, role: discord.Role):
        """Reward active boosters whose profiles display no tag from this server."""
        await self._set_reward(
            ctx, "boost_role_id", role, "Boost-only", boost_requires_no_tag=True
        )

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
        """Stop managing the configured booster reward."""
        async with self.config.guild(ctx.guild).all() as settings:
            settings["boost_role_id"] = None
            settings["boost_requires_no_tag"] = False
        await ctx.send("Booster reward unset. Remove any old assignments manually.")

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
            issue = self._role_issue(
                ctx.guild, role, settings.get("privileged_role_approvals")
            )
            status = "approved" if self._dangerous(role) and not issue else ("safe" if not issue else "BLOCKED")
            return f"{role.mention} ({status})"
        audit = settings.get("role_snapshot") or {}
        boost_label = (
            "Boost-only reward" if settings["boost_requires_no_tag"] else "Booster reward (any tag)"
        )
        await ctx.send(
            f"**ServerTag {self.__version__}** — {'Enabled' if settings['enabled'] else 'Disabled'}\n"
            f"Bound server: {ctx.guild.name} ({ctx.guild.id})\n"
            f"Basic eligibility: {fmt('basic_role_id') if settings.get('basic_role_id') else 'All members'}\n"
            f"Basic tag reward: {fmt('role_id')}\n"
            f"{boost_label}: {fmt('boost_role_id')}\n"
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
            if role is None or self._role_issue(
                ctx.guild, role, settings.get("privileged_role_approvals")
            ):
                return await ctx.send("A configured reward role is missing or not approved. Check tagrole status.")
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
        async with self.config.guild(ctx.guild).all() as settings:
            settings.update(
                enabled=False, role_id=None, boost_role_id=None,
                boost_tag_role_id=None, basic_role_id=None, boost_requires_no_tag=False,
            )
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
                while await self._in_bound_server(ctx.guild):
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
