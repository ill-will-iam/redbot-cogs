"""Haven: reversible lockdown plus a separately confirmed owner-only reset."""

from __future__ import annotations

import asyncio
import secrets
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Union

import discord
from redbot.core import Config, commands

from .reset import ResetBlocked, ServerReset, fingerprint


OverwriteTarget = Union[discord.Role, discord.Member]


class Haven(commands.Cog):
    """Owner-only reversible server channel lockdown and permission recovery."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=8481726062026, force_registration=True
        )
        self.config.register_guild(snapshot=None, sealed=False, delegates=[], reset_last=None)
        self._locks: Dict[int, asyncio.Lock] = {}

    def _lock(self, guild_id: int) -> asyncio.Lock:
        return self._locks.setdefault(guild_id, asyncio.Lock())

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Only the guild owner or an explicitly delegated Administrator may use Haven."""
        if ctx.guild is None:
            return False
        if ctx.author.id == ctx.guild.owner_id:
            return True
        if not ctx.author.guild_permissions.administrator:
            return False
        return ctx.author.id in await self.config.guild(ctx.guild).delegates()

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
        """Track @everyone and every role/member overwrite that allows posting."""
        existing = channel.overwrites
        everyone = guild.default_role
        targets = [(everyone, channel.overwrites_for(everyone), everyone in existing)]
        readonly_flags = (
            "send_messages", "send_messages_in_threads", "send_tts_messages",
            "add_reactions", "create_public_threads", "create_private_threads",
            "speak", "stream", "request_to_speak", "send_voice_messages",
            "use_soundboard", "use_external_sounds", "send_polls", "create_polls",
            "manage_messages", "manage_threads", "manage_webhooks",
        )
        for target, overwrite in existing.items():
            if target == everyone:
                continue
            if any(
                flag in discord.Permissions.VALID_FLAGS and getattr(overwrite, flag, None) is True
                for flag in readonly_flags
            ):
                targets.append((target, overwrite, True))
        return targets

    @staticmethod
    def _read_only_overwrite(target, original, everyone):
        updated = discord.PermissionOverwrite.from_pair(*original.pair())
        readonly_flags = (
            "send_messages", "send_messages_in_threads", "send_tts_messages",
            "add_reactions", "create_public_threads", "create_private_threads",
            "speak", "stream", "request_to_speak", "send_voice_messages",
            "use_soundboard", "use_external_sounds", "send_polls", "create_polls",
            "manage_messages", "manage_threads", "manage_webhooks",
        )
        for flag in readonly_flags:
            if flag in discord.Permissions.VALID_FLAGS and (
                target == everyone or getattr(original, flag, None) is True
            ):
                setattr(updated, flag, False)
        # Do not alter view_channel: private channels remain private.
        return updated

    @commands.group(name="haven", invoke_without_command=True)
    @commands.guild_only()
    async def haven(self, ctx: commands.Context):
        """Owner/delegated Administrator: inspect, seal, restore, status."""
        await ctx.send(
            "**Haven** — reversible read-only server mode: "
            "`haven inspect`, `haven seal`, `haven restore`, `haven status`. "
            "Destructive reset (server owner AND bot owner only): `haven nuke` "
            "or `haven nuke preview`. "
            "Owner-only delegation: `haven authorize @member` and "
            "`haven revoke @member`. The separate nuke command permanently deletes channels and messages."
        )

    @haven.command(name="nuke")
    @commands.is_owner()
    @commands.guild_only()
    async def haven_nuke(self, ctx: commands.Context, mode: str = "confirm"):
        """Server AND bot owner: preview, confirm, and permanently reset this server."""
        # Explicit check as well as decorators: delegates never gain reset access.
        if ctx.guild is None or ctx.author.id != ctx.guild.owner_id or not await self.bot.is_owner(ctx.author):
            await ctx.send("Only the server owner who is also a bot owner may reset this server.")
            return
        if mode not in ("confirm", "preview"):
            await ctx.send("Use `haven nuke preview` for a dry run or `haven nuke` to start confirmation.")
            return
        lock = self._lock(ctx.guild.id)
        if lock.locked():
            await ctx.send("Another Haven operation is running. Wait for it to finish.")
            return
        async with lock:
            reset = ServerReset(self, ctx)
            try:
                plan = await reset.plan()
                await ctx.send(
                    f"**PERMANENT SERVER RESET — {ctx.guild.id}**\n"
                    f"Delete {len(plan['channels'])} channels/categories and their messages; "
                    f"remove {sum(len(m['roles']) for m in plan['members'])} role assignments "
                    "from everyone except the server owner and this bot; clear @everyone permissions; "
                    "pause invites; leave one private owner channel.\n"
                    f"{len(plan['retained_managed'])} harmless managed role assignments cannot be removed. "
                    "Role definitions remain. Members are not kicked. **Deleted messages and channels "
                    "cannot be restored.** The audit file is not a content backup."
                )
                if mode == "preview":
                    return
                token = secrets.token_hex(4)
                phrase = f"DELETE {ctx.guild.id} {token}"
                await ctx.send(f"To confirm this exact plan, type `{phrase}` here within 60 seconds.")

                def check(message):
                    return (message.author.id == ctx.author.id and message.channel.id == ctx.channel.id
                            and message.guild is not None and message.guild.id == ctx.guild.id
                            and message.content.strip() == phrase)

                try:
                    await self.bot.wait_for("message", check=check, timeout=60)
                except asyncio.TimeoutError:
                    await ctx.send("Reset cancelled. No changes made.")
                    return
                fresh = await reset.plan()
                if fingerprint(fresh) != fingerprint(plan):
                    await ctx.send("Server state changed. Nothing changed by Haven; run a fresh preview.")
                    return
                await reset.execute(fresh)
            except (ResetBlocked, discord.HTTPException, OSError, TypeError) as exc:
                # The command channel may already be gone; prefer the owner room,
                # then DM. Never report success on a partially completed reset.
                detail = str(exc) if isinstance(exc, ResetBlocked) else type(exc).__name__
                message = f"Haven reset stopped: {detail}. No further actions will run. Check `haven status` and the local reset audit; changes already applied remain."
                destination = reset.room or ctx.author
                try:
                    await destination.send(message)
                except discord.HTTPException:
                    pass

    @haven.command(name="authorize")
    async def haven_authorize(self, ctx: commands.Context, member: discord.Member):
        """Server owner: explicitly authorize a current Administrator to operate Haven."""
        if ctx.author.id != ctx.guild.owner_id:
            await ctx.send("Only the server owner can delegate Haven access.")
            return
        if not member.guild_permissions.administrator or member.bot:
            await ctx.send("Choose a human member with the Administrator permission.")
            return
        async with self._lock(ctx.guild.id):
            ids = await self.config.guild(ctx.guild).delegates()
            if member.id not in ids:
                ids.append(member.id)
                await self.config.guild(ctx.guild).delegates.set(ids)
        await ctx.send(f"{member.mention} is now authorized to operate Haven.")

    @haven.command(name="revoke")
    async def haven_revoke(self, ctx: commands.Context, member: discord.Member):
        """Server owner: revoke Haven operating authorization."""
        if ctx.author.id != ctx.guild.owner_id:
            await ctx.send("Only the server owner can revoke Haven access.")
            return
        async with self._lock(ctx.guild.id):
            ids = await self.config.guild(ctx.guild).delegates()
            await self.config.guild(ctx.guild).delegates.set(
                [member_id for member_id in ids if member_id != member.id]
            )
        await ctx.send(f"{member.mention}'s Haven authorization was revoked.")

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
            f"Administrator roles (will retain Administrator privileges): "
            f"**{admin_list}**\n"
            "This will make channels read-only for non-administrators, while "
            "preserving channel visibility and private channel access. "
            "Discord Administrators bypass channel overwrites and remain able to post. "
            "Category-synced channels are covered through their category."
        )

    @haven.command(name="status")
    async def haven_status(self, ctx: commands.Context):
        """Show whether a restorable permission snapshot is present."""
        reset = await self.config.guild(ctx.guild).reset_last()
        if reset and ctx.author.id == ctx.guild.owner_id:
            await ctx.send(f"Last destructive reset: **{reset['state']}**. Run: `{reset['run']}`. "
                           f"Local audit: `{reset['audit']}`. Channel: {reset.get('channel', 'not created')}. "
                           "`haven restore` does not undo a destructive reset.")
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
        """Make channels read-only for non-administrators with a recovery snapshot."""
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
                f"**CONFIRM READ-ONLY LOCKDOWN** for `{guild.name}`.\n"
                f"Reply with `SEAL {guild.id}` within 45 seconds. "
                "Non-administrators will be unable to post or react, but will "
                "keep their current channel visibility. Administrators bypass "
                "the restrictions. No roles or server contents are deleted."
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
                    new = self._read_only_overwrite(target, original, guild.default_role)
                    try:
                        await channel.set_permissions(
                            target, overwrite=new,
                            reason=f"Haven read-only lockdown initiated by {ctx.author.id}",
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
                            reason=f"Haven permissions restored by {ctx.author.id}",
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
