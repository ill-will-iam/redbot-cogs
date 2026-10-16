"""Haven: owner-only, reversible Discord server visibility lockdown.

Deliberately does not delete channels, remove users, alter roles, or grant
privileges. This cog is intended for administrators of their own servers.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Union

import discord
from redbot.core import Config, commands


OverwriteTarget = Union[discord.Role, discord.Member]


class Haven(commands.Cog):
    """Owner-only reversible server channel lockdown and permission recovery."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=8481726062026, force_registration=True
        )
        self.config.register_guild(snapshot=None, sealed=False)
        self._locks: Dict[int, asyncio.Lock] = {}

    def _lock(self, guild_id: int) -> asyncio.Lock:
        return self._locks.setdefault(guild_id, asyncio.Lock())

    async def cog_check(self, ctx: commands.Context) -> bool:
        # Discord guild ownership is checked, not just Red's "bot owner" role.
        return ctx.guild is not None and ctx.author.id == ctx.guild.owner_id

    @staticmethod
    def _eligible_channels(guild: discord.Guild):
        # Channels synced with a category inherit its overwrites. Changing them
        # individually would break synchronization, so change category only.
        for channel in guild.channels:
            if channel.category is not None and channel.permissions_synced:
                continue
            yield channel

    @staticmethod
    def _target_is_administrator(target: OverwriteTarget) -> bool:
        if isinstance(target, discord.Role):
            return target.permissions.administrator
        if isinstance(target, discord.Member):
            return target.guild_permissions.administrator
        return False

    @staticmethod
    def _record(target: OverwriteTarget, original: discord.PermissionOverwrite, existed: bool) -> dict:
        allow, deny = original.pair()
        return {
            "id": target.id,
            "type": "role" if isinstance(target, discord.Role) else "member",
            "existed": existed,
            "allow": allow.value,
            "deny": deny.value,
        }

    @classmethod
    def _targets(cls, guild: discord.Guild, channel) -> List[Tuple[OverwriteTarget, discord.PermissionOverwrite, bool]]:
        existing = channel.overwrites
        result = []
        # @everyone deny prevents ordinary public role access.
        everyone = guild.default_role
        result.append((everyone, channel.overwrites_for(everyone), everyone in existing))

        # Explicit member/role channel grants override @everyone denies. Remove
        # only view grants for those explicit targets. Admins still bypass.
        for target, overwrite in existing.items():
            if target.id == everyone.id and isinstance(target, discord.Role):
                continue
            if cls._target_is_administrator(target):
                continue
            if overwrite.view_channel is True:
                result.append((target, overwrite, True))
        return result

    @commands.group(name="haven", invoke_without_command=True)
    @commands.guild_only()
    async def haven(self, ctx: commands.Context):
        """Server owner utilities: inspect, seal, restore, status."""
        await ctx.send(
            "**Haven** — reversible server lockdown. Commands: "
            "`haven inspect`, `haven seal`, `haven restore`, `haven status`. "
            "No members, roles, channels, or messages are deleted."
        )

    @haven.command(name="inspect")
    async def haven_inspect(self, ctx: commands.Context):
        """Show what Haven would change and list privileged roles."""
        guild = ctx.guild
        independent = list(self._eligible_channels(guild))
        grants = sum(len(self._targets(guild, ch)) for ch in independent)
        admins = [role for role in guild.roles if role.permissions.administrator]
        admin_list = ", ".join(discord.utils.escape_markdown(r.name) for r in admins[:12]) or "None"
        if len(admins) > 12:
            admin_list += f" (+{len(admins) - 12} more)"
        await ctx.send(
            f"**Haven preview for {discord.utils.escape_markdown(guild.name)}**\n"
            f"Channels/categories to update: **{len(independent)}**\n"
            f"Permission overwrites to save: **{grants}**\n"
            f"Administrator roles (will remain able to view channels): "
            f"**{admin_list}**\n"
            "This will hide channels from non-admins, not remove members or roles. "
            "Category-synced channels are covered through their category. "
            "Member/role changes after a seal may complicate restoration."
        )

    @haven.command(name="status")
    async def haven_status(self, ctx: commands.Context):
        """Show whether a restorable permission snapshot is present."""
        data = await self.config.guild(ctx.guild).snapshot()
        sealed = await self.config.guild(ctx.guild).sealed()
        if not data:
            await ctx.send("Haven is inactive; no permission snapshot is stored.")
            return
        await ctx.send(
            f"Haven snapshot present. State: {'sealed or partially sealed' if sealed else 'pending'}. "
            f"Captured: {data.get('created', 'unknown')}. "
            f"Targets: {len(data.get('channels', {}))} channels/categories. "
            "Run `haven restore` to revert saved permission overwrites."
        )

    @haven.command(name="seal")
    async def haven_seal(self, ctx: commands.Context):
        """Hide all channels from non-administrators, with a recovery snapshot."""
        guild = ctx.guild
        me = guild.me
        if me is None or not me.guild_permissions.administrator:
            await ctx.send(
                "Haven requires the bot to already have **Administrator**. "
                "This ensures the bot can access and restore locked channels."
            )
            return

        async with self._lock(guild.id):
            if await self.config.guild(guild).snapshot() is not None:
                await ctx.send("A snapshot already exists. Restore before sealing again.")
                return

            await ctx.send(
                f"**CONFIRM SERVER LOCKDOWN** for `{guild.name}`.\n"
                f"Reply with `SEAL {guild.id}` within 45 seconds. This hides "
                "channels from ordinary members; **it does not remove other "
                "administrators**, who bypass channel permissions. "
                "Nothing is deleted."
            )

            def check(message: discord.Message) -> bool:
                return (
                    message.author.id == ctx.author.id
                    and message.channel.id == ctx.channel.id
                    and message.content.strip() == f"SEAL {guild.id}"
                )

            try:
                await self.bot.wait_for("message", check=check, timeout=45)
            except asyncio.TimeoutError:
                await ctx.send("Lockdown cancelled (confirmation timed out).")
                return

            # Snapshot the entire planned operation before changing anything.
            plan = []
            snapshot = {}
            for channel in self._eligible_channels(guild):
                targets = self._targets(guild, channel)
                record = [self._record(target, overwrite, existed) for target, overwrite, existed in targets]
                snapshot[str(channel.id)] = {"name": channel.name, "targets": record}
                plan.append((channel, targets))
            data = {
                "created": datetime.now(timezone.utc).isoformat(),
                "guild_id": guild.id,
                "channels": snapshot,
            }
            await self.config.guild(guild).snapshot.set(data)
            await self.config.guild(guild).sealed.set(True)

            changed = 0
            errors = []
            for channel, targets in plan:
                for target, original, _ in targets:
                    new = discord.PermissionOverwrite.from_pair(*original.pair())
                    new.view_channel = False
                    new.send_messages = False
                    new.connect = False
                    try:
                        await channel.set_permissions(
                            target, overwrite=new,
                            reason=f"Haven lockdown initiated by guild owner {ctx.author.id}",
                        )
                        changed += 1
                    except (discord.Forbidden, discord.HTTPException) as exc:
                        errors.append(f"{channel.name}: {type(exc).__name__}")

            note = (
                f"Haven lockdown attempted. Applied **{changed}** permission changes "
                f"across **{len(plan)}** channels/categories. "
                "Use `haven restore` to reverse the changes."
            )
            if errors:
                note += f" **{len(errors)} changes failed**. Examples: " + ", ".join(errors[:4])
            await ctx.send(note)

    @haven.command(name="restore")
    async def haven_restore(self, ctx: commands.Context):
        """Restore saved permission overwrites (retriable on partial failure)."""
        guild = ctx.guild
        async with self._lock(guild.id):
            data = await self.config.guild(guild).snapshot()
            if not data:
                await ctx.send("No Haven snapshot found; nothing to restore.")
                return
            if data.get("guild_id") != guild.id:
                await ctx.send("Snapshot guild ID mismatch. No changes made.")
                return

            await ctx.send(
                f"**CONFIRM PERMISSION RESTORE**: reply `RESTORE {guild.id}` "
                "within 45 seconds. This replaces the channel overwrites Haven saved."
            )

            def check(message: discord.Message) -> bool:
                return (
                    message.author.id == ctx.author.id
                    and message.channel.id == ctx.channel.id
                    and message.content.strip() == f"RESTORE {guild.id}"
                )

            try:
                await self.bot.wait_for("message", check=check, timeout=45)
            except asyncio.TimeoutError:
                await ctx.send("Restore cancelled (confirmation timed out).")
                return

            restored = 0
            errors = []
            for channel_id, details in data["channels"].items():
                channel = guild.get_channel(int(channel_id))
                if channel is None:
                    errors.append(f"missing channel {channel_id}")
                    continue
                for item in details["targets"]:
                    if item["type"] == "role":
                        target = guild.get_role(int(item["id"]))
                    else:
                        target = guild.get_member(int(item["id"]))
                        if target is None:
                            # Fetch only when a member isn't already cached.
                            try:
                                target = await guild.fetch_member(int(item["id"]))
                            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                                target = None
                    if target is None:
                        # Missing targets no longer have an overwrite to restore.
                        continue
                    original = (
                        discord.PermissionOverwrite.from_pair(
                            discord.Permissions(item["allow"]),
                            discord.Permissions(item["deny"]),
                        )
                        if item["existed"] else None
                    )
                    try:
                        await channel.set_permissions(
                            target, overwrite=original,
                            reason=f"Haven permissions restored by guild owner {ctx.author.id}",
                        )
                        restored += 1
                    except (discord.Forbidden, discord.HTTPException) as exc:
                        errors.append(f"{details['name']}: {type(exc).__name__}")

            if errors:
                # Do NOT lose recovery state; owner can retry after fixing perms.
                await ctx.send(
                    f"Restored **{restored}** overwrites, but **{len(errors)}** errors "
                    "occurred. Snapshot retained for a retry. "
                    "Examples: " + ", ".join(errors[:4])
                )
                return
            await self.config.guild(guild).snapshot.set(None)
            await self.config.guild(guild).sealed.set(False)
            await ctx.send(
                f"Haven restored **{restored}** saved overwrites. "
                "Recovery snapshot cleared."
            )
