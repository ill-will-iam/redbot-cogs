"""Explicit owner-authorized reset. Never runs from listeners or on startup."""

import hashlib
import json
import os
import secrets
from datetime import datetime, timezone

import discord
from redbot.core.data_manager import cog_data_path


class ResetBlocked(RuntimeError):
    """A prerequisite failed; do not proceed to deletion."""


def role_blocker(role, top_role):
    if role.is_default():
        return None
    if role.managed:
        # Harmless integration/boost roles are unassignable by the API.
        dangerous = ("administrator", "manage_guild", "manage_roles", "manage_channels")
        if any(getattr(role.permissions, flag) for flag in dangerous):
            return f"Privileged managed role {role.id} cannot be stripped."
    elif role >= top_role:
        return f"Role {role.id} is not below the bot's highest role."
    return None


def fingerprint(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()


class ServerReset:
    def __init__(self, cog, ctx):
        self.cog, self.ctx = cog, ctx
        self.bot, self.guild = cog.bot, ctx.guild
        self.path = None
        self.room = None

    async def authorized(self):
        current = await self.bot.fetch_guild(self.guild.id)
        if current.owner_id != self.ctx.author.id or not await self.bot.is_owner(self.ctx.author):
            raise ResetBlocked("Only the current server owner who is also a bot owner can reset it.")
        return current

    async def plan(self):
        current = await self.authorized()
        if "COMMUNITY" in current.features:
            raise ResetBlocked("Disable Community in server settings first; required Community channels cannot all be deleted.")
        if not self.bot.intents.members:
            raise ResetBlocked("The Members intent must be enabled to enumerate every member.")
        if await self.cog.config.guild(self.guild).snapshot() is not None:
            raise ResetBlocked("Restore the existing Haven seal snapshot first.")
        roles = {r.id: r for r in await self.guild.fetch_roles()}
        me = await self.guild.fetch_member(self.bot.user.id)
        # Rebuild permissions from freshly fetched roles, not cached guild permissions.
        bot_roles = [roles[r.id] for r in me.roles]
        if not any(r.permissions.administrator for r in bot_roles if not r.is_default()):
            raise ResetBlocked("The bot needs Administrator on its own role, independent of @everyone.")
        me_top = max(bot_roles)
        members = [m async for m in self.guild.fetch_members(limit=None)]
        channels = await self.guild.fetch_channels()
        records, retained = [], []
        for member in members:
            if member.id in (current.owner_id, me.id):
                continue
            assigned = [roles[r.id] for r in member.roles if not r.is_default()]
            for role in assigned:
                # Compare against fresh role hierarchy.
                error = role_blocker(role, me_top)
                if error:
                    raise ResetBlocked(f"Member {member.id}: {error}")
                if role.managed:
                    retained.append([member.id, role.id])
            removable = [r.id for r in assigned if not r.managed]
            if removable and assigned and max(assigned) >= me_top:
                raise ResetBlocked(f"Member {member.id} is at or above the bot in the hierarchy.")
            records.append({"id": member.id, "roles": sorted(removable)})
        return {
            "guild": self.guild.id, "owner": current.owner_id,
            "roles": sorted([[r.id, r.permissions.value, r.position, r.managed] for r in roles.values()]),
            "members": sorted(records, key=lambda m: m["id"]),
            "retained_managed": sorted(retained),
            "channels": sorted([[c.id, c.name, c.type.value] for c in channels]),
            "features": sorted(current.features),
        }

    def audit(self, event, **details):
        # Write intent before every request and completion after it. No invite codes,
        # tokens or message contents are recorded. Disk errors stop further actions.
        record = {"time": datetime.now(timezone.utc).isoformat(), "actor": self.ctx.author.id,
                  "guild": self.guild.id, "event": event, **details}
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    async def action(self, name, target, operation):
        self.audit("intent", action=name, target=target)
        result = await operation()
        self.audit("success", action=name, target=target)
        return result

    async def verify_isolation(self):
        current = await self.authorized()
        if "INVITES_DISABLED" not in current.features:
            raise ResetBlocked("Discord has not confirmed paused invites; deletion stopped.")
        roles = {r.id: r for r in await self.guild.fetch_roles()}
        if roles[self.guild.id].permissions.value != 0:
            raise ResetBlocked("@everyone permissions changed; deletion stopped.")
        async for member in self.guild.fetch_members(limit=None):
            if member.id in (current.owner_id, self.bot.user.id):
                continue
            for assigned in member.roles:
                role = roles[assigned.id]
                if role.is_default():
                    continue
                if not role.managed or any(getattr(role.permissions, p) for p in
                                          ("administrator", "manage_guild", "manage_roles", "manage_channels")):
                    raise ResetBlocked(f"Member {member.id} still has a removable or privileged role; deletion stopped.")

    async def execute(self, plan):
        run_id = secrets.token_hex(8)
        self.path = cog_data_path(self.cog) / f"reset-{self.guild.id}-{run_id}.jsonl"
        self.audit("snapshot", plan=plan)
        state = {"run": run_id, "state": "running", "audit": self.path.name}
        await self.cog.config.guild(self.guild).reset_last.set(state)
        reason = f"Haven reset {run_id}; guild/bot owner {self.ctx.author.id} confirmed"
        try:
            # Discord may reject this on unsupported guilds. Abort before any deletions.
            await self.action("pause_invites", self.guild.id,
                              lambda: self.guild.edit(invites_disabled=True, reason=reason))
            current = await self.bot.fetch_guild(self.guild.id)
            if "INVITES_DISABLED" not in current.features:
                raise ResetBlocked("Discord did not confirm the invite pause.")
            roles = {r.id: r for r in await self.guild.fetch_roles()}
            await self.action("clear_everyone_permissions", self.guild.id,
                              lambda: roles[self.guild.id].edit(permissions=discord.Permissions.none(), reason=reason))
            for record in plan["members"]:
                if not record["roles"]:
                    continue
                try:
                    member = await self.guild.fetch_member(record["id"])
                except discord.NotFound:
                    self.audit("member_left", target=record["id"])
                    continue
                await self.action("remove_member_roles", member.id,
                                  lambda: member.remove_roles(*(roles[r] for r in record["roles"]), reason=reason, atomic=True))
            await self.verify_isolation()
            owner = await self.guild.fetch_member(self.ctx.author.id)
            me = await self.guild.fetch_member(self.bot.user.id)
            self.room = await self.action("create_owner_channel", self.guild.id,
                lambda: self.guild.create_text_channel("haven-owner", overwrites={
                    self.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    owner: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
                    me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
                }, reason=reason))
            state["channel"] = self.room.id
            await self.cog.config.guild(self.guild).reset_last.set(state)
            await self.room.send("Owner reset is running. Old channels and their messages will be permanently deleted.")
            # Only delete the exact reviewed channel IDs. Newly created channels stop
            # the run instead of silently expanding the owner's confirmed scope.
            channels = await self.guild.fetch_channels()
            expected = {row[0] for row in plan["channels"]}
            actual = {c.id for c in channels if c.id != self.room.id}
            if actual != expected:
                raise ResetBlocked("Channel list changed after confirmation; deletion stopped.")
            for channel in sorted(channels, key=lambda c: isinstance(c, discord.CategoryChannel)):
                if channel.id == self.room.id:
                    continue
                await self.authorized()
                await self.action("delete_channel", channel.id, lambda: channel.delete(reason=reason))
            await self.verify_isolation()
            remaining = await self.guild.fetch_channels()
            if {c.id for c in remaining} != {self.room.id}:
                raise ResetBlocked("Unexpected channels remain; reset is incomplete.")
            state["state"] = "complete"
            self.audit("complete", channel=self.room.id)
        except BaseException as exc:
            state["state"] = "incomplete"
            state["error"] = type(exc).__name__
            self.audit("incomplete", error=type(exc).__name__)
            raise
        finally:
            await self.cog.config.guild(self.guild).reset_last.set(state)
        await self.room.send("Reset verified: invites paused, assignable roles removed from other members, and only this channel remains. The server owner and FATBOY retain access. Deleted messages cannot be restored.")
