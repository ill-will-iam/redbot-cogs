"""ChaosChat: make Fatboy sporadically join human conversations with nonsense."""

import asyncio
import logging
import random
import time
from typing import Dict, Tuple

import discord
from redbot.core import Config, commands

from .responses import generate_response

log = logging.getLogger("red.chaoschat")


class ChaosChat(commands.Cog):
    """A chaotic, offline conversational gremlin with proper anti-spam controls."""

    __author__ = "Will & North"
    __version__ = "1.1.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=630189274551, force_registration=True)
        self.config.register_guild(
            enabled=False,
            chance=8,  # Chance per eligible human message, in percent.
            mode="feral",  # tame, wild, feral
            slavic_chance=25,  # % of feral/wild replies in a Slavic language
            slavic_language="random",  # russian/polish/ukrainian/czech/serbian
            cooldown=75,  # Minimum seconds between random replies anywhere in a guild.
            channel_cooldown=120,
            user_cooldown=240,
            direct=True,  # Respond to bot mentions and replies to the bot.
            followups=True,  # At most one follow-up to the same person.
            only_channels=[],  # Empty means any channel (subject to exclusions).
            blocked_channels=[],
            reply_count=0,
        )
        # All transient state. User IDs and message text are NEVER persisted.
        self._last_guild: Dict[int, float] = {}
        self._last_channel: Dict[Tuple[int, int], float] = {}
        self._last_user: Dict[Tuple[int, int], float] = {}
        self._pending: Dict[Tuple[int, int, int], float] = {}
        self._locks: Dict[int, asyncio.Lock] = {}
        self._sent_since_cleanup = 0

    def cog_unload(self):
        self._last_guild.clear()
        self._last_channel.clear()
        self._last_user.clear()
        self._pending.clear()
        self._locks.clear()

    def _prune(self, now: float):
        """Keep temporary anti-spam tables bounded on long-running bots."""
        self._sent_since_cleanup += 1
        if self._sent_since_cleanup < 200:
            return
        self._sent_since_cleanup = 0
        for records in (self._last_guild, self._last_channel, self._last_user):
            for key, timestamp in list(records.items()):
                if now - timestamp > 7200:
                    records.pop(key, None)
        for key, timestamp in list(self._pending.items()):
            if now - timestamp > 90:
                self._pending.pop(key, None)
        # Clear locks for guilds not seen recently, except the currently held ones.
        for guild_id, lock in list(self._locks.items()):
            if guild_id not in self._last_guild and not lock.locked():
                self._locks.pop(guild_id, None)

    @staticmethod
    def _channel_id(message):
        # Threads inherit their parent channel's allow/block policy.
        channel = message.channel
        return channel.parent_id if isinstance(channel, discord.Thread) else channel.id

    def _directed_at_bot(self, message) -> bool:
        user = self.bot.user
        if user is None:
            return False
        if user in message.mentions:
            return True
        ref = message.reference
        resolved = getattr(ref, "resolved", None)
        return isinstance(resolved, discord.Message) and resolved.author.id == user.id

    @staticmethod
    def _toggle_value(value: str):
        value = value.lower()
        if value in ("on", "yes", "true", "enable", "enabled"):
            return True
        if value in ("off", "no", "false", "disable", "disabled"):
            return False
        return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        guild = message.guild
        if guild is None or message.author.bot or message.webhook_id is not None:
            return
        if not message.content or not message.content.strip():
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return

        # Ignore all regular commands (including unrecognized commands using the
        # configured prefix). Allow @Fatboy conversational mentions that aren't
        # real commands, even if mention-as-prefix is enabled.
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return
        if ctx.prefix is not None:
            bot_user = self.bot.user
            mentioned_as_prefix = bool(bot_user) and message.content.lstrip().startswith(
                (f"<@{bot_user.id}>", f"<@!{bot_user.id}>")
            )
            if not mentioned_as_prefix:
                return

        settings = await self.config.guild(guild).all()
        if not settings["enabled"]:
            return
        parent_id = self._channel_id(message)
        only = settings["only_channels"]
        if only and parent_id not in only:
            return
        if parent_id in settings["blocked_channels"]:
            return

        me = guild.me
        if me is None:
            return
        perms = message.channel.permissions_for(me)
        if not perms.view_channel:
            return
        if isinstance(message.channel, discord.Thread):
            if not perms.send_messages_in_threads:
                return
        elif not perms.send_messages:
            return

        directed = bool(settings["direct"]) and self._directed_at_bot(message)
        if not directed and len(message.content.strip()) < 3:
            return
        now = time.monotonic()
        guild_key = guild.id
        channel_key = (guild.id, message.channel.id)
        user_key = (guild.id, message.author.id)
        pending_key = (guild.id, message.channel.id, message.author.id)

        # A per-guild lock protects cooldown decisions from concurrent events.
        lock = self._locks.setdefault(guild.id, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            last_guild = self._last_guild.get(guild_key, float("-inf"))
            last_channel = self._last_channel.get(channel_key, float("-inf"))
            last_user = self._last_user.get(user_key, float("-inf"))

            pending_since = self._pending.get(pending_key)
            followup = False
            if pending_since is not None:
                if now - pending_since > 90:
                    self._pending.pop(pending_key, None)
                elif settings["followups"] and now - pending_since >= 3:
                    # Only one possible continuation of the previous exchange.
                    self._pending.pop(pending_key, None)
                    followup = random.random() < 0.72

            if followup:
                # Short cooldown to allow an actual exchange, capped at 1 extra turn.
                if now - last_user < 3 or now - last_channel < 3 or now - last_guild < 3:
                    return
            elif directed:
                # An explicit @mention/reply is responsive, but never spammable.
                if now - last_user < 12 or now - last_channel < 8 or now - last_guild < 5:
                    return
            else:
                if (
                    now - last_guild < settings["cooldown"]
                    or now - last_channel < settings["channel_cooldown"]
                    or now - last_user < settings["user_cooldown"]
                ):
                    return
                if random.random() * 100 >= settings["chance"]:
                    return

            response = generate_response(
                message.content, mode=settings["mode"], followup=followup,
                slavic_chance=settings["slavic_chance"],
                slavic_language=settings["slavic_language"],
            )
            try:
                await message.reply(
                    response,
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except (discord.Forbidden, discord.HTTPException):
                log.debug("Could not reply in channel %s", message.channel.id, exc_info=True)
                return

            # Only successful sends count or update cooldowns.
            self._last_guild[guild_key] = now
            self._last_channel[channel_key] = now
            self._last_user[user_key] = now
            if not followup and settings["followups"]:
                self._pending[pending_key] = now
            await self.config.guild(guild).reply_count.set(settings["reply_count"] + 1)
            self._prune(now)

    @commands.group(name="chaoschat", aliases=["chaos"], invoke_without_command=True)
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def chaoschat(self, ctx: commands.Context):
        """Configure Fatboy's spontaneous chaotic conversations."""
        await self._help_text(ctx)

    async def _help_text(self, ctx):
        p = ctx.clean_prefix
        await ctx.send(
            "**ChaosChat — fatboy's unsupervised conversational nonsense**\n"
            f"`{p}chaoschat on` / `off` — enable or disable in this server\n"
            f"`{p}chaoschat chance 8` — random replies per eligible message (0-100%)\n"
            f"`{p}chaoschat mode feral` — tame / wild / feral (adult profanity)\n"
            f"`{p}chaoschat slavic 25` — chance to speak a Slavic language (0–100%)\n"
            f"`{p}chaoschat language random` — random/russian/polish/ukrainian/czech/serbian\n"
            f"`{p}chaoschat cooldown 75` — server-wide random reply gap (seconds)\n"
            f"`{p}chaoschat channelcooldown 120` — per-channel random reply gap\n"
            f"`{p}chaoschat usercooldown 240` — per-user random reply gap\n"
            f"`{p}chaoschat direct on` — answer @mentions/replies (rate-limited)\n"
            f"`{p}chaoschat followups on` — sometimes reply once more to same user\n"
            f"`{p}chaoschat channel only #general` — restrict to selected channels\n"
            f"`{p}chaoschat channel add #off-topic` — add another allowed channel\n"
            f"`{p}chaoschat channel all` — allow all channels again\n"
            f"`{p}chaoschat channel block #staff` / `unblock #staff`\n"
            f"`{p}chaoschat status` — show all settings\n"
            f"`{p}chaoschat test Why is the moon angry?` — preview a response\n"
            "No AI service/API key needed. Bot/command messages are ignored. "
            "Thread settings inherit the parent channel.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @chaoschat.command(name="help")
    async def chaos_help(self, ctx: commands.Context):
        """Show all ChaosChat commands and examples."""
        await self._help_text(ctx)

    @chaoschat.command(name="on", aliases=["enable"])
    async def chaos_on(self, ctx: commands.Context):
        """Enable random chatter in this server."""
        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.send("ChaosChat **ON**. Fatboy is now occasionally going to say some truly questionable things.")

    @chaoschat.command(name="off", aliases=["disable"])
    async def chaos_off(self, ctx: commands.Context):
        """Disable random chatter in this server."""
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.send("ChaosChat **OFF**. The goose has been contained.")

    @chaoschat.command(name="chance")
    async def chaos_chance(self, ctx: commands.Context, percent: int):
        """Chance from 0 to 100 percent for eligible random messages."""
        if percent < 0 or percent > 100:
            return await ctx.send("Enter a whole percentage from 0 to 100.")
        await self.config.guild(ctx.guild).chance.set(percent)
        await ctx.send(f"Random reply chance set to **{percent}%** per eligible message.")

    @chaoschat.command(name="mode")
    async def chaos_mode(self, ctx: commands.Context, mode: str):
        """Select tame, wild, or feral nonsense."""
        mode = mode.lower()
        if mode not in ("tame", "wild", "feral"):
            return await ctx.send("Valid modes: `tame`, `wild`, `feral`.")
        await self.config.guild(ctx.guild).mode.set(mode)
        await ctx.send(f"ChaosChat personality set to **{mode}**.")

    @chaoschat.command(name="slavic")
    async def chaos_slavic(self, ctx: commands.Context, percent: int):
        """Set the percent of wild/feral output in a Slavic language (0–100)."""
        if not 0 <= percent <= 100:
            return await ctx.send("Enter a percentage from 0 to 100.")
        await self.config.guild(ctx.guild).slavic_chance.set(percent)
        await ctx.send(f"Slavic-language outbursts: **{percent}%** of generated replies.")

    @chaoschat.command(name="language", aliases=["slaviclanguage"])
    async def chaos_language(self, ctx: commands.Context, language: str):
        """Random Slavic language or one specific language."""
        from .responses import LANGUAGE_ALIASES

        language = LANGUAGE_ALIASES.get(language.lower())
        if language is None:
            return await ctx.send(
                "Choose `random`, `russian`, `polish`, `ukrainian`, `czech`, "
                "or `serbian` (or `ru`, `pl`, `uk`, `cs`, `sr`)."
            )
        await self.config.guild(ctx.guild).slavic_language.set(language)
        await ctx.send(f"Slavic-language selection: **{language}**.")

    async def _set_seconds(self, ctx, key: str, value: int):
        if not 0 <= value <= 3600:
            return await ctx.send("Choose a cooldown between 0 and 3600 seconds.")
        await getattr(self.config.guild(ctx.guild), key).set(value)
        await ctx.send(f"**{key.replace('_', ' ').title()}** set to {value} seconds.")

    @chaoschat.command(name="cooldown")
    async def chaos_cooldown(self, ctx: commands.Context, seconds: int):
        """Server-wide minimum delay between random replies (0-3600 seconds)."""
        await self._set_seconds(ctx, "cooldown", seconds)

    @chaoschat.command(name="channelcooldown")
    async def chaos_channel_cooldown(self, ctx: commands.Context, seconds: int):
        """Per-channel minimum delay between random replies."""
        await self._set_seconds(ctx, "channel_cooldown", seconds)

    @chaoschat.command(name="usercooldown")
    async def chaos_user_cooldown(self, ctx: commands.Context, seconds: int):
        """Per-user minimum delay between random replies."""
        await self._set_seconds(ctx, "user_cooldown", seconds)

    @chaoschat.command(name="direct")
    async def chaos_direct(self, ctx: commands.Context, value: str):
        """Enable or disable replies to direct @mentions/replies."""
        enabled = self._toggle_value(value)
        if enabled is None:
            return await ctx.send("Use `on` or `off`.")
        await self.config.guild(ctx.guild).direct.set(enabled)
        await ctx.send(f"Responses to mentions/direct replies: **{'ON' if enabled else 'OFF'}**.")

    @chaoschat.command(name="followups")
    async def chaos_followups(self, ctx: commands.Context, value: str):
        """Enable or disable one-turn follow-up exchanges."""
        enabled = self._toggle_value(value)
        if enabled is None:
            return await ctx.send("Use `on` or `off`.")
        await self.config.guild(ctx.guild).followups.set(enabled)
        await ctx.send(f"Short follow-up conversations: **{'ON' if enabled else 'OFF'}**.")

    @chaoschat.group(name="channel", invoke_without_command=True)
    async def chaos_channel(self, ctx: commands.Context):
        """Restrict chatter to selected channels, or block specific channels."""
        p = ctx.clean_prefix
        await ctx.send(
            f"`{p}chaoschat channel only #general` — start an allowlist\n"
            f"`{p}chaoschat channel add #off-topic` — extend the allowlist\n"
            f"`{p}chaoschat channel remove #general` — remove from allowlist\n"
            f"`{p}chaoschat channel all` — clear allowlist (all allowed)\n"
            f"`{p}chaoschat channel block #staff` / `unblock #staff` — exclusions\n"
            "Threads inherit their parent's channel rules."
        )

    @staticmethod
    def _target_channel(ctx, channel):
        target = channel or ctx.channel
        return target.parent if isinstance(target, discord.Thread) else target

    @chaos_channel.command(name="only")
    async def chaos_only(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Make this the only allowed channel (repeat `add` for others)."""
        channel = self._target_channel(ctx, channel)
        await self.config.guild(ctx.guild).only_channels.set([channel.id])
        await ctx.send(f"ChaosChat will now speak **only** in {channel.mention} (and its threads).",
                       allowed_mentions=discord.AllowedMentions.none())

    @chaos_channel.command(name="add")
    async def chaos_add(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Add a channel to the allowlist (creates allowlist if empty)."""
        channel = self._target_channel(ctx, channel)
        conf = self.config.guild(ctx.guild).only_channels
        allowed = await conf()
        if channel.id not in allowed:
            allowed.append(channel.id)
            await conf.set(allowed)
        await ctx.send(f"Allowed: {channel.mention}.", allowed_mentions=discord.AllowedMentions.none())

    @chaos_channel.command(name="remove")
    async def chaos_remove(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Remove a channel from the allowlist (empty list means all channels)."""
        channel = self._target_channel(ctx, channel)
        conf = self.config.guild(ctx.guild).only_channels
        allowed = await conf()
        if channel.id not in allowed:
            return await ctx.send("That channel isn't on the allowlist.")
        if len(allowed) == 1:
            return await ctx.send(
                "That's the last allowed channel. Use `chaoschat channel all` "
                "to allow all channels, or `chaoschat off` to stop chatter."
            )
        allowed.remove(channel.id)
        await conf.set(allowed)
        await ctx.send(f"Removed {channel.mention} from the allowlist.",
                       allowed_mentions=discord.AllowedMentions.none())

    @chaos_channel.command(name="all")
    async def chaos_all(self, ctx: commands.Context):
        """Clear the allowlist so all non-blocked channels are eligible."""
        await self.config.guild(ctx.guild).only_channels.set([])
        await ctx.send("All channels eligible again, except explicitly blocked ones.")

    @chaos_channel.command(name="block")
    async def chaos_block(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Exclude a channel from ChaosChat."""
        channel = self._target_channel(ctx, channel)
        conf = self.config.guild(ctx.guild).blocked_channels
        blocked = await conf()
        if channel.id not in blocked:
            blocked.append(channel.id)
            await conf.set(blocked)
        await ctx.send(f"Blocked {channel.mention} (and its threads).",
                       allowed_mentions=discord.AllowedMentions.none())

    @chaos_channel.command(name="unblock")
    async def chaos_unblock(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Remove a channel from the blocklist."""
        channel = self._target_channel(ctx, channel)
        conf = self.config.guild(ctx.guild).blocked_channels
        blocked = await conf()
        if channel.id in blocked:
            blocked.remove(channel.id)
            await conf.set(blocked)
        await ctx.send(f"Unblocked {channel.mention}.", allowed_mentions=discord.AllowedMentions.none())

    @chaoschat.command(name="status")
    async def chaos_status(self, ctx: commands.Context):
        """Display current server settings and total reply count."""
        cfg = await self.config.guild(ctx.guild).all()
        only = ", ".join(f"<#{cid}>" for cid in cfg["only_channels"]) or "All channels"
        blocked = ", ".join(f"<#{cid}>" for cid in cfg["blocked_channels"]) or "None"
        await ctx.send(
            f"**ChaosChat — {ctx.guild.name}**\n"
            f"Enabled: **{cfg['enabled']}** | Chance: **{cfg['chance']}%** "
            f"| Mode: **{cfg['mode']}**\n"
            f"Slavic outbursts: **{cfg['slavic_chance']}%** "
            f"| Language: **{cfg['slavic_language']}**\n"
            f"Cooldowns (server / channel / user): **{cfg['cooldown']} / "
            f"{cfg['channel_cooldown']} / {cfg['user_cooldown']} sec**\n"
            f"Direct replies: **{cfg['direct']}** | Follow-ups: **{cfg['followups']}**\n"
            f"Allowed: {only}\nBlocked: {blocked}\n"
            f"Total ChaosChat replies: **{cfg['reply_count']}**",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @chaoschat.command(name="test")
    async def chaos_test(self, ctx: commands.Context, *, message: str = "What should we do?"):
        """Preview an absurd reply without needing chatter enabled."""
        cfg = await self.config.guild(ctx.guild).all()
        mode = cfg["mode"]
        await ctx.send(
            f"**Sample ({mode}):** {generate_response(message, mode=mode, slavic_chance=cfg['slavic_chance'], slavic_language=cfg['slavic_language'])}",
            allowed_mentions=discord.AllowedMentions.none(),
        )
