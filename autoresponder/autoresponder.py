"""Per-server persistent, moderator-managed trigger/reply AutoResponder for Fatboy."""

import asyncio
import time
from typing import Dict, List, Pattern, Tuple

import discord
from redbot.core import Config, commands
from redbot.core.utils.chat_formatting import pagify

from .matching import (
    MAX_RULES,
    compile_rules,
    find_response,
    normalize_trigger,
    parse_rule_input,
)


class AutoResponder(commands.Cog):
    """Make Fatboy speak when a configured word or phrase is said."""

    __author__ = "Will"
    __version__ = "1.0.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=519374281122, force_registration=True)
        self.config.register_guild(rules={}, enabled=True, cooldown=15)
        self._rules: Dict[int, Dict[str, str]] = {}
        self._compiled: Dict[int, List[Tuple[str, Pattern[str]]]] = {}
        self._enabled: Dict[int, bool] = {}
        self._cooldown: Dict[int, int] = {}
        self._last_reply: Dict[Tuple[int, int, str], float] = {}
        self._locks: Dict[int, asyncio.Lock] = {}

    def _lock(self, guild_id: int) -> asyncio.Lock:
        return self._locks.setdefault(guild_id, asyncio.Lock())

    async def cog_load(self):
        for guild_id, saved in (await self.config.all_guilds()).items():
            self._set_cache(int(guild_id), saved)

    def cog_unload(self):
        self._last_reply.clear()

    def _set_cache(self, guild_id: int, settings: dict):
        rules = dict(settings.get("rules", {}))
        self._rules[guild_id] = rules
        self._compiled[guild_id] = compile_rules(rules)
        self._enabled[guild_id] = bool(settings.get("enabled", True))
        self._cooldown[guild_id] = int(settings.get("cooldown", 15))
        self._last_reply = {
            k: v for k, v in self._last_reply.items()
            if k[0] != guild_id or k[2] in rules
        }

    @staticmethod
    def _safe(value: str) -> str:
        return discord.utils.escape_mentions(discord.utils.escape_markdown(value))

    @commands.group(name="ar", aliases=["autoresponder"], invoke_without_command=True)
    @commands.guild_only()
    async def ar(self, ctx: commands.Context):
        """Manage word-triggered responses. Run [p]ar help."""
        p = ctx.clean_prefix
        await ctx.send(
            "**AutoResponder** — automatic server-wide replies to chosen words.\n"
            f"Example: `{p}ar add hello | Hey there!`\n"
            f"Use `{p}ar help` for all commands.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @ar.command(name="help")
    async def ar_help(self, ctx: commands.Context):
        """Show command examples."""
        p = ctx.clean_prefix
        await ctx.send(
            "**AutoResponder commands** (Manage Server permission required to edit settings)\n"
            f"`{p}ar add hello | Hey there!` — create trigger\n"
            f"`{p}ar edit hello | Different reply!` — update trigger\n"
            f"`{p}ar remove hello` — delete trigger\n"
            f"`{p}ar list` — list triggers\n"
            f"`{p}ar show hello` — show saved response\n"
            f"`{p}ar test hello everyone` — preview a response without sending it\n"
            f"`{p}ar enable` / `{p}ar disable` — toggle autoresponses\n"
            f"`{p}ar cooldown 15` — set 0–300 second cooldown per trigger/channel\n"
            f"`{p}ar status` — current settings\n\n"
            "All text channels and threads. Whole-word, case-insensitive matching. "
            "One response per message. Bot messages and bot commands are ignored. "
            "Bot replies never ping anyone.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @ar.command(name="add", aliases=["set"])
    @commands.has_guild_permissions(manage_guild=True)
    async def ar_add(self, ctx: commands.Context, *, rule: str):
        """Add a trigger: [p]ar add hello | Hello there!"""
        try:
            trigger, response = parse_rule_input(rule)
        except ValueError as exc:
            await ctx.send(str(exc))
            return
        async with self._lock(ctx.guild.id):
            rules = await self.config.guild(ctx.guild).rules()
            if trigger in rules:
                await ctx.send(
                    f"`{self._safe(trigger)}` already exists. Use `{ctx.clean_prefix}ar edit` to change it.",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                return
            if len(rules) >= MAX_RULES:
                await ctx.send(f"This server has reached the {MAX_RULES}-trigger limit.")
                return
            rules[trigger] = response
            await self.config.guild(ctx.guild).rules.set(rules)
            self._rules[ctx.guild.id] = dict(rules)
            self._compiled[ctx.guild.id] = compile_rules(rules)
        await ctx.send(
            f"**Added:** `{self._safe(trigger)}` → {self._safe(response)}",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @ar.command(name="edit", aliases=["update"])
    @commands.has_guild_permissions(manage_guild=True)
    async def ar_edit(self, ctx: commands.Context, *, rule: str):
        """Edit a trigger: [p]ar edit hello | New response"""
        try:
            trigger, response = parse_rule_input(rule)
        except ValueError as exc:
            await ctx.send(str(exc))
            return
        async with self._lock(ctx.guild.id):
            rules = await self.config.guild(ctx.guild).rules()
            if trigger not in rules:
                await ctx.send(f"`{self._safe(trigger)}` does not exist. Use `{ctx.clean_prefix}ar add`.")
                return
            rules[trigger] = response
            await self.config.guild(ctx.guild).rules.set(rules)
            self._rules[ctx.guild.id] = dict(rules)
            self._compiled[ctx.guild.id] = compile_rules(rules)
        await ctx.send(
            f"**Updated:** `{self._safe(trigger)}` → {self._safe(response)}",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @ar.command(name="remove", aliases=["delete", "del"])
    @commands.has_guild_permissions(manage_guild=True)
    async def ar_remove(self, ctx: commands.Context, *, trigger: str):
        """Remove a word/phrase trigger."""
        trigger = normalize_trigger(trigger)
        async with self._lock(ctx.guild.id):
            rules = await self.config.guild(ctx.guild).rules()
            if trigger not in rules:
                await ctx.send(f"`{self._safe(trigger)}` isn't configured.")
                return
            del rules[trigger]
            await self.config.guild(ctx.guild).rules.set(rules)
            self._set_cache(ctx.guild.id, {
                "rules": rules,
                "enabled": self._enabled.get(ctx.guild.id, True),
                "cooldown": self._cooldown.get(ctx.guild.id, 15),
            })
        await ctx.send(f"Removed trigger `{self._safe(trigger)}`.")

    @ar.command(name="list", aliases=["triggers"])
    async def ar_list(self, ctx: commands.Context):
        """List active trigger phrases."""
        rules = await self.config.guild(ctx.guild).rules()
        if not rules:
            await ctx.send(f"No triggers configured. Use `{ctx.clean_prefix}ar add hello | Hey!`.")
            return
        entries = [f"{i}. `{self._safe(word)}`" for i, word in enumerate(sorted(rules), 1)]
        for page in pagify("\n".join(entries), page_length=1750, delims=["\n"]):
            await ctx.send(
                f"**AutoResponder triggers ({len(rules)})**\n{page}",
                allowed_mentions=discord.AllowedMentions.none(),
            )

    @ar.command(name="show")
    async def ar_show(self, ctx: commands.Context, *, trigger: str):
        """Show a configured reply."""
        trigger = normalize_trigger(trigger)
        rules = await self.config.guild(ctx.guild).rules()
        if trigger not in rules:
            await ctx.send("That trigger is not configured.")
            return
        await ctx.send(
            f"**Trigger:** `{self._safe(trigger)}`\n**Reply:** {self._safe(rules[trigger])}",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @ar.command(name="test")
    async def ar_test(self, ctx: commands.Context, *, phrase: str):
        """Preview a match without starting the cooldown."""
        rules = await self.config.guild(ctx.guild).rules()
        trigger = find_response(phrase, compile_rules(rules))
        if trigger is None:
            await ctx.send("No autoresponder trigger matches that text.")
            return
        await ctx.send(
            f"**Matched:** `{self._safe(trigger)}`\n**Would reply:** {self._safe(rules[trigger])}",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @ar.command(name="enable")
    @commands.has_guild_permissions(manage_guild=True)
    async def ar_enable(self, ctx: commands.Context):
        """Enable automatic replies across this guild."""
        await self.config.guild(ctx.guild).enabled.set(True)
        self._enabled[ctx.guild.id] = True
        await ctx.send("AutoResponder is **enabled** for this server.")

    @ar.command(name="disable")
    @commands.has_guild_permissions(manage_guild=True)
    async def ar_disable(self, ctx: commands.Context):
        """Disable replies without deleting the rules."""
        await self.config.guild(ctx.guild).enabled.set(False)
        self._enabled[ctx.guild.id] = False
        await ctx.send("AutoResponder is **disabled**. Existing rules are saved.")

    @ar.command(name="cooldown")
    @commands.has_guild_permissions(manage_guild=True)
    async def ar_cooldown(self, ctx: commands.Context, seconds: int):
        """Set per-trigger/per-channel cooldown (0–300 seconds)."""
        if not 0 <= seconds <= 300:
            await ctx.send("Choose a cooldown between 0 and 300 seconds.")
            return
        await self.config.guild(ctx.guild).cooldown.set(seconds)
        self._cooldown[ctx.guild.id] = seconds
        await ctx.send(f"Cooldown set to **{seconds} seconds** per trigger per channel.")

    @ar.command(name="status")
    async def ar_status(self, ctx: commands.Context):
        """Show current server-wide status."""
        settings = await self.config.guild(ctx.guild).all()
        await ctx.send(
            "**AutoResponder — server-wide**\n"
            f"Enabled: **{'yes' if settings['enabled'] else 'no'}**\n"
            f"Triggers: **{len(settings['rules'])}** / {MAX_RULES}\n"
            f"Cooldown: **{settings['cooldown']} seconds** per trigger/channel\n"
            "Matching: whole words and phrases, ignoring case, one reply per message."
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Reply to human messages in any server text channel or thread."""
        if (
            message.guild is None
            or message.author.bot
            or message.webhook_id is not None
            or not message.content
            or not self._enabled.get(message.guild.id, True)
            or not self._compiled.get(message.guild.id)
        ):
            return
        if await self.bot.cog_disabled_in_guild(self, message.guild):
            return
        # Ignore configured command-prefix messages, even unrecognized commands.
        ctx = await self.bot.get_context(message)
        if ctx.prefix is not None:
            return
        guild_id = message.guild.id
        trigger = find_response(message.content, self._compiled[guild_id])
        if trigger is None:
            return
        throttle_key = (guild_id, message.channel.id, trigger)
        async with self._lock(guild_id):
            if not self._enabled.get(guild_id, True):
                return
            response = self._rules.get(guild_id, {}).get(trigger)
            if response is None:
                return
            now = time.monotonic()
            previous = self._last_reply.get(throttle_key, float("-inf"))
            if now - previous < self._cooldown.get(guild_id, 15):
                return
            self._last_reply[throttle_key] = now
            if len(self._last_reply) > 5000:
                cutoff = now - 600
                self._last_reply = {
                    key: timestamp for key, timestamp in self._last_reply.items()
                    if timestamp >= cutoff
                }
        try:
            await message.channel.send(
                response,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.HTTPException):
            async with self._lock(guild_id):
                if self._last_reply.get(throttle_key) == now:
                    self._last_reply.pop(throttle_key, None)

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """Stores no personal user IDs or message history."""
        return
