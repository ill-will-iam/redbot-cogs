"""Small, per-server administration event logger for Red V3."""

import io
import logging

import discord
from redbot.core import Config, commands


log = logging.getLogger("red.illwill.adminlog")


def label(value):
    """Keep names readable without allowing names to change log formatting."""
    return discord.utils.escape_markdown(str(value))


def identity(user):
    return f"{label(user)} (ID: {user.id})"


def describe_channel(channel):
    return f"{label(channel.name)} (ID: {channel.id})" if channel else "None"


def message_text(message):
    parts = [message.content or "[No text content]"]
    if message.attachments:
        parts.append("Attachments:\n" + "\n".join(a.url for a in message.attachments))
    if message.stickers:
        parts.append("Stickers: " + ", ".join(f"{s.name} ({s.id})" for s in message.stickers))
    return "\n\n".join(parts)


class AdminLog(commands.Cog):
    """Record member, message, voice, and server changes in an admin channel."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=2026101308295901, force_registration=True)
        self.config.register_guild(channel_id=None)

    async def destination(self, guild):
        if not guild or await self.bot.cog_disabled_in_guild(self, guild):
            return None
        channel_id = await self.config.guild(guild).channel_id()
        return guild.get_channel(channel_id) if channel_id else None

    async def emit(self, guild, title, description, *, text=None):
        """Preserve full long records in a text attachment and never ping users."""
        channel = await self.destination(guild)
        if channel is None:
            return False
        perms = channel.permissions_for(guild.me)
        if not (perms.view_channel and perms.send_messages and perms.embed_links):
            log.warning("AdminLog cannot send embeds in configured channel %s", channel.id)
            return False
        embed = discord.Embed(
            title=title[:256], description=description[:3500],
            colour=discord.Colour.blurple(), timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"Server ID: {guild.id}")
        kwargs = {"embed": embed, "allowed_mentions": discord.AllowedMentions.none()}
        record = "\n\n".join(part for part in (description, text) if part)
        if text:
            embed.add_field(name="Message content", value=label(text)[:1000] or "[Empty]", inline=False)
        if len(description) > 3500 or (text and len(label(text)) > 1000):
            if perms.attach_files:
                kwargs["file"] = discord.File(
                    io.BytesIO(record.encode("utf-8")), filename="adminlog-record.txt"
                )
                embed.add_field(name="Full record", value="See the attached text file.", inline=False)
            else:
                embed.add_field(
                    name="Full record unavailable",
                    value="Preview truncated. Give the bot Attach Files to preserve long records.",
                    inline=False,
                )
        try:
            await channel.send(**kwargs)
        except discord.HTTPException:
            log.warning("AdminLog could not send a record to channel %s", channel.id, exc_info=True)
            return False
        finally:
            if "file" in kwargs:
                kwargs["file"].close()
        return True

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def adminlog(self, ctx):
        """Configure server logging. Use `[p]adminlog channel #channel`."""
        await ctx.send_help()

    @adminlog.command(name="channel")
    async def set_channel(self, ctx, channel: discord.TextChannel):
        """Choose this server's log channel and enable logging."""
        if channel.guild.id != ctx.guild.id:
            await ctx.send("Choose a text channel in this server.")
            return
        perms = channel.permissions_for(ctx.me)
        if not all((perms.view_channel, perms.send_messages, perms.embed_links, perms.attach_files)):
            await ctx.send("I need View Channel, Send Messages, Embed Links, and Attach Files there.")
            return
        # Verify access before saving a destination that may not work.
        try:
            await channel.send("AdminLog enabled here.", allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            await ctx.send("I couldn't send to that channel; please check its permissions.")
            return
        await self.config.guild(ctx.guild).channel_id.set(channel.id)
        await ctx.send(f"Administration logs will go to {channel.mention}.")

    @adminlog.command(name="off")
    async def turn_off(self, ctx):
        """Disable logging in this server without deleting existing records."""
        await self.config.guild(ctx.guild).channel_id.set(None)
        await ctx.send("Administration logging disabled.")

    @adminlog.command(name="status")
    async def status(self, ctx):
        """Show the log destination, permissions, and required intents."""
        channel_id = await self.config.guild(ctx.guild).channel_id()
        channel = ctx.guild.get_channel(channel_id) if channel_id else None
        if channel:
            perms = channel.permissions_for(ctx.me)
            missing = [name for name in ("view_channel", "send_messages", "embed_links", "attach_files")
                       if not getattr(perms, name)]
            destination = f"{channel.mention}; missing permissions: {', '.join(missing) or 'none'}"
        else:
            destination = "Off" if channel_id is None else f"Configured channel {channel_id} no longer exists"
        intents = self.bot.intents
        await ctx.send(
            f"**AdminLog**\nChannel: {destination}\n"
            f"Member events: {'on' if intents.members else 'OFF — enable Server Members Intent'}\n"
            f"Message text: {'on' if intents.message_content else 'OFF — enable Message Content Intent'}\n"
            f"Voice events: {'on' if intents.voice_states else 'OFF'}\n"
            f"Ban events: {'on' if intents.moderation else 'OFF'}\n"
            f"Message events: {'on' if intents.guild_messages else 'OFF'}\n"
            "Deleted text is available only for messages in the bot's cache."
        )

    @adminlog.command(name="test")
    async def test_log(self, ctx):
        """Send a sample record to check the destination."""
        ok = await self.emit(ctx.guild, "Logging test", f"Requested by {identity(ctx.author)}")
        await ctx.send("Test record sent." if ok else "No record sent. Use [p]adminlog status to check setup.")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        created = discord.utils.format_dt(member.created_at, "F")
        await self.emit(member.guild, "Member joined", f"{identity(member)}\nAccount created: {created}")

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        await self.emit(member.guild, "Member left / removed", identity(member))

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        changes = []
        if before.nick != after.nick:
            changes.append(f"Nickname: {label(before.nick or '[None]')} → {label(after.nick or '[None]')}")
        old, new = {r.id: r for r in before.roles}, {r.id: r for r in after.roles}
        added, removed = new.keys() - old.keys(), old.keys() - new.keys()
        if added:
            changes.append("Roles added: " + ", ".join(f"{label(new[r].name)} ({r})" for r in sorted(added)))
        if removed:
            changes.append("Roles removed: " + ", ".join(f"{label(old[r].name)} ({r})" for r in sorted(removed)))
        if before.timed_out_until != after.timed_out_until:
            until = discord.utils.format_dt(after.timed_out_until, "F") if after.timed_out_until else "Removed"
            changes.append(f"Timeout: {until}")
        if before.guild_avatar != after.guild_avatar:
            changes.append("Server avatar changed.")
        if changes:
            await self.emit(after.guild, "Member updated", identity(after) + "\n" + "\n".join(changes))

    @commands.Cog.listener()
    async def on_user_update(self, before, after):
        changes = []
        for attr in ("name", "global_name"):
            if getattr(before, attr) != getattr(after, attr):
                changes.append(f"{attr}: {label(getattr(before, attr))} → {label(getattr(after, attr))}")
        if before.avatar != after.avatar:
            changes.append("Profile avatar changed.")
        if changes:
            for guild in self.bot.guilds:
                if guild.get_member(after.id):
                    await self.emit(guild, "User profile updated", identity(after) + "\n" + "\n".join(changes))

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        await self.emit(guild, "Member banned", identity(user))

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        await self.emit(guild, "Member unbanned", identity(user))

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        changes = []
        if before.channel != after.channel:
            if before.channel is None:
                changes.append(f"Joined: {describe_channel(after.channel)}")
            elif after.channel is None:
                changes.append(f"Left: {describe_channel(before.channel)}")
            else:
                changes.append(f"Moved: {describe_channel(before.channel)} → {describe_channel(after.channel)}")
        for attr, name in (("self_mute", "Self mute"), ("self_deaf", "Self deaf"),
                           ("mute", "Server mute"), ("deaf", "Server deaf"),
                           ("self_stream", "Streaming"), ("self_video", "Camera"),
                           ("suppress", "Stage audience")):
            if getattr(before, attr) != getattr(after, attr):
                changes.append(f"{name}: {'on' if getattr(after, attr) else 'off'}")
        if changes:
            await self.emit(member.guild, "Voice activity", identity(member) + "\n" + "\n".join(changes))

    async def message_event_guild(self, payload):
        """Ignore DMs and changes to the log channel to prevent recursion."""
        guild = self.bot.get_guild(payload.guild_id) if payload.guild_id else None
        if not guild:
            return None
        channel_id = await self.config.guild(guild).channel_id()
        if not channel_id or channel_id == payload.channel_id:
            return None
        return guild

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        guild = await self.message_event_guild(payload)
        if guild is None:
            return
        message = payload.cached_message
        if message and self.bot.user and message.author.id == self.bot.user.id:
            return
        details = f"Channel: <#{payload.channel_id}>\nMessage ID: {payload.message_id}"
        if message:
            details += f"\nAuthor: {identity(message.author)}"
            text = message_text(message)
        else:
            text = "Author and original content unavailable: this message was not cached."
        await self.emit(guild, "Message deleted", details, text=text)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload):
        guild = await self.message_event_guild(payload)
        if guild is None:
            return
        cached = {m.id: m for m in payload.cached_messages}
        records = []
        for message_id in sorted(payload.message_ids):
            message = cached.get(message_id)
            if message and self.bot.user and message.author.id == self.bot.user.id:
                continue
            records.append(f"Message ID: {message_id}\n" + (
                f"Author: {identity(message.author)}\n{message_text(message)}" if message else
                "Author and content unavailable (not cached)."
            ))
        if records:
            await self.emit(
                guild, "Messages bulk deleted",
                f"Channel: <#{payload.channel_id}>\nDeleted messages: {len(payload.message_ids)}",
                text="\n\n---\n\n".join(records),
            )

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload):
        # Embed/link-preview updates aren't text edits.
        if "content" not in payload.data:
            return
        guild = await self.message_event_guild(payload)
        if guild is None:
            return
        before = payload.cached_message
        author = before.author if before else None
        author_id = author.id if author else int(payload.data.get("author", {}).get("id", 0))
        if self.bot.user and author_id == self.bot.user.id:
            return
        after_text = payload.data["content"] or "[No text content]"
        if before and before.content == payload.data["content"]:
            return
        details = (
            f"Channel: <#{payload.channel_id}>\nMessage ID: {payload.message_id}\n"
            f"Author: {identity(author) if author else (str(author_id) if author_id else '[Not cached]')}\n"
            f"https://discord.com/channels/{guild.id}/{payload.channel_id}/{payload.message_id}"
        )
        old = message_text(before) if before else "[Original content not cached]"
        await self.emit(guild, "Message edited", details, text=f"BEFORE:\n{old}\n\nAFTER:\n{after_text}")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        await self.emit(channel.guild, "Channel created", describe_channel(channel))

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        await self.emit(channel.guild, "Channel deleted", describe_channel(channel))

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        changes = []
        for attr in ("name", "topic", "category_id", "slowmode_delay", "nsfw", "bitrate", "user_limit"):
            old, new = getattr(before, attr, None), getattr(after, attr, None)
            if old != new:
                changes.append(f"{attr}: {label(old)} → {label(new)}")
        if before.overwrites != after.overwrites:
            changes.append("Channel permission overwrites changed.")
        if changes:
            await self.emit(after.guild, "Channel updated", describe_channel(after) + "\n" + "\n".join(changes))

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        await self.emit(role.guild, "Role created", f"{label(role.name)} (ID: {role.id})")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        await self.emit(role.guild, "Role deleted", f"{label(role.name)} (ID: {role.id})")

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        changes = []
        for attr in ("name", "colour", "hoist", "mentionable", "position"):
            old, new = getattr(before, attr), getattr(after, attr)
            if old != new:
                changes.append(f"{attr}: {label(old)} → {label(new)}")
        if before.permissions != after.permissions:
            changed = [f"{name}: {'on' if enabled else 'off'}" for name, enabled in after.permissions
                       if getattr(before.permissions, name) != enabled]
            changes.append("Permissions: " + ", ".join(changed))
        if changes:
            await self.emit(after.guild, "Role updated", f"{label(after.name)} (ID: {after.id})\n" + "\n".join(changes))

    @commands.Cog.listener()
    async def on_guild_update(self, before, after):
        changes = []
        for attr in ("name", "description", "verification_level", "explicit_content_filter", "icon"):
            old, new = getattr(before, attr), getattr(after, attr)
            if old != new:
                changes.append(f"{attr}: {label(old)} → {label(new)}")
        if changes:
            await self.emit(after, "Server updated", "\n".join(changes))

    async def red_delete_data_for_user(self, *, requester, user_id):
        # No per-user database or extra message cache is maintained by this cog.
        # Posted Discord records are managed by server administrators.
        return
