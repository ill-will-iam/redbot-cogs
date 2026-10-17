"""Lightweight deleted-message sniping for Red-DiscordBot 3.5+."""

from datetime import datetime, timezone
from typing import List, Optional

import discord
from redbot.core import commands

from .cache import SnipeStore, SnipedMessage


def _format_embed(entry: SnipedMessage, position: int, total: int) -> discord.Embed:
    """Render a cached deletion without pinging anyone."""
    description = discord.utils.escape_mentions(entry.content)
    if len(description) > 3500:
        description = description[:3497] + "..."
    if not description:
        description = "*No text content.*"

    embed = discord.Embed(
        title="Deleted message",
        description=description,
        color=discord.Color.dark_teal(),
        timestamp=entry.deleted_at,
    )
    embed.set_author(name=f"{entry.author_name[:170]} (ID: {entry.author_id})"[:256])
    if entry.attachments:
        links = [
            f"[{discord.utils.escape_markdown(name[:80])}]({url})"
            for name, url in entry.attachments[:10]
        ]
        attachments = "\n".join(links)
        embed.add_field(
            name="Attachments (links may no longer work)",
            value=attachments[:1024] or "(none)",
            inline=False,
        )
    if entry.stickers:
        stickers = ", ".join(entry.stickers)
        embed.add_field(name="Stickers", value=stickers[:1024], inline=False)
    embed.set_footer(text=f"{position}/{total} | Deleted at (UTC) | Cache expires after 24 hours")
    return embed


class _SnipePages(discord.ui.View):
    """A small, invoker-only viewer; stored records stay in the cog's cache."""

    def __init__(
        self,
        store: SnipeStore,
        guild_id: int,
        channel_id: int,
        message_ids: List[int],
        user_id: int,
    ):
        super().__init__(timeout=180)
        self.store = store
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.message_ids = message_ids
        self.user_id = user_id
        self.page = 0
        self.response_message: Optional[discord.Message] = None
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page >= len(self.message_ids) - 1

    def _page_embed(self) -> Optional[discord.Embed]:
        entry = self.store.get(
            self.guild_id, self.channel_id, self.message_ids[self.page]
        )
        if entry is None:
            return None
        return _format_embed(entry, self.page + 1, len(self.message_ids))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Only the person who ran $snipe can control these pages.",
                ephemeral=True,
            )
            return False
        return True

    async def _show(self, interaction: discord.Interaction) -> None:
        embed = self._page_embed()
        if embed is None:
            await interaction.response.send_message(
                "That deleted message is no longer in the snipe cache.", ephemeral=True
            )
            return
        self._sync_buttons()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        await self._show(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < len(self.message_ids) - 1:
            self.page += 1
        await self._show(interaction)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(view=None)

    async def on_timeout(self) -> None:
        for component in self.children:
            if isinstance(component, discord.ui.Button):
                component.disabled = True
        if self.response_message is not None:
            try:
                await self.response_message.edit(view=self)
            except (discord.HTTPException, discord.Forbidden):
                pass


class Snipe(commands.Cog):
    """View recent deleted messages in a channel. Moderator access only."""

    __author__ = "Will"
    __version__ = "1.0.0"

    def __init__(self, bot):
        self.bot = bot
        self.store = SnipeStore(max_per_channel=50, retention_hours=24)

    def _remember_cached(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        attachments = tuple((a.filename, a.url) for a in message.attachments)
        stickers = tuple(item.name for item in message.stickers)
        if not (message.content or attachments or stickers):
            return
        entry = SnipedMessage(
            message_id=message.id,
            author_id=message.author.id,
            author_name=message.author.display_name,
            content=message.content,
            attachments=attachments,
            stickers=stickers,
            deleted_at=datetime.now(timezone.utc),
        )
        self.store.remember(message.guild.id, message.channel.id, entry)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        # Only cached messages contain recoverable content; a raw ID cannot restore text.
        if payload.guild_id is not None and payload.cached_message is not None:
            self._remember_cached(payload.cached_message)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent) -> None:
        if payload.guild_id is None:
            return
        # Sort oldest first because the store prepends the newest entry.
        for message in sorted(payload.cached_messages, key=lambda item: item.id):
            self._remember_cached(message)

    @commands.group(name="snipe", invoke_without_command=True)
    @commands.guild_only()
    @commands.mod_or_permissions(manage_messages=True)
    async def snipe(self, ctx: commands.Context, count: int = 1):
        """Show the latest deleted message here; optionally browse up to 50.

        Examples: [p]snipe, [p]snipe 5, [p]snipe 20.
        """
        if not 1 <= count <= self.store.max_per_channel:
            await ctx.send("Choose a number of messages from 1 to 50.")
            return
        entries = self.store.recent(ctx.guild.id, ctx.channel.id, count)
        if not entries:
            await ctx.send("No recently deleted messages are cached in this channel.")
            return
        if not ctx.channel.permissions_for(ctx.guild.me).embed_links:
            await ctx.send("I need the **Embed Links** permission to show sniped messages.")
            return
        if len(entries) == 1:
            await ctx.send(embed=_format_embed(entries[0], 1, 1), allowed_mentions=discord.AllowedMentions.none())
            return
        pages = _SnipePages(
            self.store, ctx.guild.id, ctx.channel.id,
            [entry.message_id for entry in entries], ctx.author.id,
        )
        pages.response_message = await ctx.send(
            embed=_format_embed(entries[0], 1, len(entries)),
            view=pages,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @snipe.command(name="clear")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def snipe_clear(self, ctx: commands.Context, scope: str = "all"):
        """Clear all server snipe history, or just this channel.

        Examples: [p]snipe clear, [p]snipe clear here.
        """
        scope = scope.lower()
        if scope not in ("all", "here"):
            await ctx.send("Use [p]snipe clear or [p]snipe clear here.".replace("[p]", ctx.clean_prefix))
            return
        channel_id = ctx.channel.id if scope == "here" else None
        total = self.store.clear(ctx.guild.id, channel_id)
        destination = "this channel" if scope == "here" else "this entire server"
        await ctx.send(f"Cleared **{total}** cached deleted message(s) from {destination}.")

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """Honor Red's user-data deletion flow for the in-memory cache."""
        self.store.delete_user(user_id)
