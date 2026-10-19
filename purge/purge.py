"""Staff-only, selective message purging for Red-DiscordBot 3.5+."""

from __future__ import annotations

import asyncio
import re
from typing import Callable, Optional, Set

import discord
from redbot.core import commands


MAX_DELETE = 500
MAX_SCAN = 5000
DEFAULT_SCAN = 1000
LINK_RE = re.compile(
    r"(?:https?://|www\.|discord\.gg/|discord(?:app)?\.com/invite/)",
    flags=re.IGNORECASE,
)

MessageCheck = Callable[[discord.Message], bool]


class Purge(commands.Cog):
    """Delete recent messages in the current channel, optionally using filters."""

    __author__ = "Will"
    __version__ = "1.1.0"

    def __init__(self, bot):
        self.bot = bot
        self._active_channels: Set[int] = set()

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data is stored by this cog."""
        return

    async def _reject(self, ctx: commands.Context) -> None:
        """Signal an invalid, cancelled, or failed purge without sending a message."""
        try:
            await ctx.message.add_reaction("❌")
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def _confirm(self, ctx: commands.Context) -> bool:
        """Require the invoker's reaction for large purges, without chat messages."""
        try:
            await ctx.message.add_reaction("✅")
            await ctx.message.add_reaction("❌")
        except (discord.Forbidden, discord.HTTPException):
            # No reaction confirmation means no large deletion.
            try:
                await ctx.message.clear_reactions()
            except (discord.Forbidden, discord.HTTPException):
                pass
            return False

        try:
            reaction = await self.bot.wait_for(
                "raw_reaction_add",
                timeout=30,
                check=lambda event: (
                    event.message_id == ctx.message.id
                    and event.channel_id == ctx.channel.id
                    and event.user_id == ctx.author.id
                    and str(event.emoji) in {"✅", "❌"}
                ),
            )
            return str(reaction.emoji) == "✅"
        except asyncio.TimeoutError:
            return False
        finally:
            try:
                await ctx.message.clear_reactions()
            except (discord.Forbidden, discord.HTTPException):
                pass

    async def _run(
        self,
        ctx: commands.Context,
        *,
        count: int,
        label: str,
        matcher: MessageCheck,
        scan: int,
        before: Optional[discord.Object] = None,
        after: Optional[discord.Object] = None,
    ):
        if not 1 <= count <= MAX_DELETE or not 1 <= scan <= MAX_SCAN:
            return await self._reject(ctx)

        channel = ctx.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return await self._reject(ctx)

        if channel.id in self._active_channels:
            return await self._reject(ctx)

        self._active_channels.add(channel.id)
        try:
            protected = {ctx.message.id}
            if count > 100 and not await self._confirm(ctx):
                return await self._reject(ctx)

            matched = 0

            def should_delete(message: discord.Message) -> bool:
                nonlocal matched
                if message.id in protected or matched >= count:
                    return False
                if not matcher(message):
                    return False
                matched += 1
                return True

            try:
                await channel.purge(
                    limit=scan + len(protected),
                    check=should_delete,
                    before=before,
                    after=after,
                    oldest_first=False,
                    bulk=True,
                    reason=f"Moderator purge ({label}) by {ctx.author} ({ctx.author.id})",
                )
            except (discord.Forbidden, discord.HTTPException):
                return await self._reject(ctx)

            try:
                await ctx.message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass
        finally:
            self._active_channels.discard(channel.id)

    @commands.group(name="purge", invoke_without_command=True)
    @commands.guild_only()
    @commands.mod_or_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge_group(self, ctx: commands.Context, count: Optional[int] = None):
        """Delete the last N messages here, or choose a filtered subcommand.

        Example: [p]purge 25
        See [p]help purge for filtered commands.
        """
        if count is None:
            return await self._reject(ctx)
        await self._run(
            ctx,
            count=count,
            label="recent messages",
            matcher=lambda m: True,
            scan=count + 1,
        )

    @purge_group.command(name="all")
    async def purge_all(self, ctx: commands.Context, count: int):
        """Delete N recent messages in this channel. Example: [p]purge all 50."""
        await self._run(
            ctx, count=count, label="recent messages", matcher=lambda m: True, scan=count + 1
        )

    @purge_group.command(name="user")
    async def purge_user(
        self, ctx: commands.Context, member: discord.Member, count: int = 50, scan: int = DEFAULT_SCAN
    ):
        """Delete up to N messages by a member from the last SCAN messages.

        Example: [p]purge user @Someone 30
        """
        await self._run(
            ctx,
            count=count,
            label=f"from user ID {member.id}",
            matcher=lambda m: m.author.id == member.id,
            scan=scan,
        )

    @purge_group.command(name="userid")
    async def purge_userid(
        self, ctx: commands.Context, user_id: int, count: int = 50, scan: int = DEFAULT_SCAN
    ):
        """Purge by numeric user ID, including members who left the server."""
        if user_id <= 0:
            return await self._reject(ctx)
        await self._run(
            ctx,
            count=count,
            label=f"from user ID {user_id}",
            matcher=lambda m: m.author.id == user_id,
            scan=scan,
        )

    @purge_group.command(name="me", aliases=["mine"])
    async def purge_me(self, ctx: commands.Context, count: int = 50, scan: int = DEFAULT_SCAN):
        """Delete your own recent messages. Example: [p]purge me 25."""
        await self._run(
            ctx,
            count=count,
            label=f"from user ID {ctx.author.id}",
            matcher=lambda m: m.author.id == ctx.author.id,
            scan=scan,
        )

    @purge_group.command(name="bots")
    async def purge_bots(self, ctx: commands.Context, count: int = 50, scan: int = DEFAULT_SCAN):
        """Delete messages sent by bots."""
        await self._run(
            ctx, count=count, label="bot messages", matcher=lambda m: m.author.bot, scan=scan
        )

    @purge_group.command(name="webhooks")
    async def purge_webhooks(
        self, ctx: commands.Context, count: int = 50, scan: int = DEFAULT_SCAN
    ):
        """Delete messages sent by webhooks."""
        await self._run(
            ctx,
            count=count,
            label="webhook messages",
            matcher=lambda m: m.webhook_id is not None,
            scan=scan,
        )

    @purge_group.command(name="links")
    async def purge_links(self, ctx: commands.Context, count: int = 50, scan: int = DEFAULT_SCAN):
        """Delete messages containing HTTP(S), www, or Discord invite links."""
        await self._run(
            ctx,
            count=count,
            label="messages with links",
            matcher=lambda m: bool(LINK_RE.search(m.content)),
            scan=scan,
        )

    @purge_group.command(name="files", aliases=["attachments", "media"])
    async def purge_files(self, ctx: commands.Context, count: int = 50, scan: int = DEFAULT_SCAN):
        """Delete messages with uploaded attachments."""
        await self._run(
            ctx,
            count=count,
            label="messages with attachments",
            matcher=lambda m: bool(m.attachments),
            scan=scan,
        )

    @purge_group.command(name="embeds")
    async def purge_embeds(self, ctx: commands.Context, count: int = 50, scan: int = DEFAULT_SCAN):
        """Delete messages containing embeds."""
        await self._run(
            ctx,
            count=count,
            label="messages with embeds",
            matcher=lambda m: bool(m.embeds),
            scan=scan,
        )

    @purge_group.command(name="contains", aliases=["text", "keyword"])
    async def purge_contains(self, ctx: commands.Context, count: int, *, phrase: str):
        """Delete messages containing text (case-insensitive).

        Example: [p]purge contains 25 unwanted phrase
        Searches the latest 1000 messages.
        """
        phrase = phrase.strip()
        if not phrase:
            return await self._reject(ctx)
        if len(phrase) > 200:
            return await self._reject(ctx)
        lowered = phrase.casefold()
        await self._run(
            ctx,
            count=count,
            label="messages containing selected text",
            matcher=lambda m: lowered in m.content.casefold(),
            scan=DEFAULT_SCAN,
        )

    @purge_group.command(name="before")
    async def purge_before(self, ctx: commands.Context, message_id: int, count: int):
        """Delete up to N messages older than a message ID."""
        if message_id <= 0:
            return await self._reject(ctx)
        await self._run(
            ctx,
            count=count,
            label=f"messages before {message_id}",
            matcher=lambda m: True,
            scan=count + 1,
            before=discord.Object(id=message_id),
        )

    @purge_group.command(name="after")
    async def purge_after(self, ctx: commands.Context, message_id: int, count: int):
        """Delete up to N messages newer than a message ID."""
        if message_id <= 0:
            return await self._reject(ctx)
        await self._run(
            ctx,
            count=count,
            label=f"messages after {message_id}",
            matcher=lambda m: True,
            scan=count + 1,
            after=discord.Object(id=message_id),
        )
