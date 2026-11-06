"""Branded status and profile panel for FATBOY (Red-DiscordBot 3.5+)."""

import datetime
import logging
import re
import sys

import discord
from redbot.core import Config, __version__ as red_version, commands

log = logging.getLogger("red.fatboyinfo")

DEFAULT_DESCRIPTION = (
    "Games, chaos, useful tools, and questionable judgment. "
    "Built for the community, operated by Will."
)
MAX_COG_FIELDS = 4


def cog_field_pages(names, limit=1000, max_pages=MAX_COG_FIELDS):
    """Split escaped cog names into Discord-embed-safe fields."""
    pages = []
    current = ""
    displayed = 0
    for name in names:
        safe_name = discord.utils.escape_markdown(str(name))
        token = safe_name if not current else ", " + safe_name
        if current and len(current) + len(token) > limit:
            pages.append(current)
            current = ""
            token = safe_name
        if len(pages) >= max_pages:
            break
        current += token[:limit]
        displayed += 1
    if current and len(pages) < max_pages:
        pages.append(current)
    omitted = len(names) - displayed
    if omitted and pages:
        suffix = f"\n...and {omitted} more. Use your bot's cogs command for the full list."
        pages[-1] = pages[-1][: limit - len(suffix)] + suffix
    return pages


class FatboyInfo(commands.Cog):
    """Shows an owner-customizable FATBOY profile and live bot statistics."""

    __author__ = "Will & North"
    __version__ = "1.0.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=0xFA7B0101, force_registration=True)
        self.config.register_global(
            owner_label="Will",
            description=DEFAULT_DESCRIPTION,
            accent=0x7C3AED,
            use_info_alias=True,
        )
        self._alias_command = None
        self._saved_core_info = None

    async def activate_info_alias(self):
        """Replace only Red's Core info command, never another third-party command."""
        if not await self.config.use_info_alias():
            self._restore_info()
            return False

        current = self.bot.get_command("info")
        if current is self._alias_command and current is not None:
            return True
        if current is not None and current.cog_name != "Core":
            log.warning("Cannot register ~info: it belongs to %s.", current.cog_name)
            return False

        if current is not None:
            self._saved_core_info = current
            self.bot.remove_command("info")

        # Discord.py treats a class method callback as (self, ctx). Passing
        # the bound method (which exposes only ctx) raises a signature error
        # at command creation time. Use a local one-argument function instead.
        try:
            async def info_callback(ctx):
                await self._send_profile(ctx)

            alias = commands.command(
                name="info", help="Show FATBOY's custom bot profile."
            )(info_callback)
            self.bot.add_command(alias)
        except Exception:
            log.exception("Could not register FATBOY's info alias; restoring Core info.")
            self._restore_info()
            return False
        self._alias_command = alias
        return True

    def _restore_info(self):
        """Undo only the alias we installed and restore Core's original command."""
        if self._alias_command is not None:
            if self.bot.get_command("info") is self._alias_command:
                self.bot.remove_command("info")
            self._alias_command = None
        if self._saved_core_info is not None:
            if self.bot.get_command("info") is None:
                try:
                    self.bot.add_command(self._saved_core_info)
                except Exception:
                    log.exception("Could not restore Red Core's original info command.")
            self._saved_core_info = None

    def cog_unload(self):
        self._restore_info()

    @commands.command(name="fatboy", aliases=["fatboyinfo", "fbinfo"])
    async def fatboy(self, ctx):
        """Display FATBOY's profile, uptime, loaded cogs and current stats."""
        await self._send_profile(ctx)

    async def _send_profile(self, ctx):
        bot_user = self.bot.user
        name = discord.utils.escape_markdown(
            discord.utils.escape_mentions(bot_user.display_name if bot_user else "FATBOY")
        )
        owner = discord.utils.escape_markdown(
            discord.utils.escape_mentions(await self.config.owner_label())
        )
        description = discord.utils.escape_mentions(await self.config.description())
        color = await self.config.accent()
        guild_count = len(self.bot.guilds)
        member_slots = sum((guild.member_count or 0) for guild in self.bot.guilds)
        cog_names = sorted(self.bot.cogs.keys(), key=str.casefold)
        latency = self.bot.latency
        latency_text = f"{latency * 1000:.0f} ms" if latency is not None and latency >= 0 else "Unknown"
        started = getattr(self.bot, "uptime", None)
        if isinstance(started, datetime.datetime):
            if started.tzinfo is None:
                started = started.replace(tzinfo=datetime.timezone.utc)
            uptime_text = f"{discord.utils.format_dt(started, style='R')}"
        else:
            uptime_text = "Unavailable"

        framework = f"Red {red_version} / discord.py {discord.__version__}"
        python_version = ".".join(map(str, sys.version_info[:3]))
        prefix = ctx.clean_prefix

        if not await ctx.embed_requested():
            await ctx.send(
                f"**{name} — Bot Profile**\n{description}\n"
                f"**Owner:** {owner}\n"
                f"**Uptime:** {uptime_text}\n"
                f"**Servers:** {guild_count:,} | **Member slots:** {member_slots:,}\n"
                f"**Loaded cogs:** {len(cog_names)} | **Ping:** {latency_text}\n"
                f"**Version:** {framework} | Python {python_version}\n"
                f"Use {prefix}cogs for the complete cog list.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        embed = discord.Embed(
            title=f"{name} // BOT PROFILE",
            description=description,
            color=discord.Color(color),
            timestamp=discord.utils.utcnow(),
        )
        if bot_user:
            embed.set_thumbnail(url=bot_user.display_avatar.url)
        embed.add_field(
            name="Owner",
            value=f"**{owner}** · [GitHub](https://github.com/ill-will-iam)",
            inline=True,
        )
        embed.add_field(name="Uptime", value=uptime_text, inline=True)
        embed.add_field(name="Gateway latency", value=latency_text, inline=True)
        embed.add_field(name="Servers", value=f"{guild_count:,}", inline=True)
        embed.add_field(name="Member slots", value=f"{member_slots:,}", inline=True)
        embed.add_field(name="Loaded cogs", value=str(len(cog_names)), inline=True)
        embed.add_field(
            name="Running on",
            value=f"{framework}\nPython {python_version}",
            inline=False,
        )
        for i, page in enumerate(cog_field_pages(cog_names), start=1):
            embed.add_field(
                name=f"Active cogs ({i})" if i > 1 else "Active cogs",
                value=page,
                inline=False,
            )
        embed.set_footer(
            text=f"FATBOY • {prefix}help for commands • Bot ID {bot_user.id if bot_user else 'n/a'}"
        )
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @commands.group(name="fatboyset", invoke_without_command=True)
    @commands.is_owner()
    async def fatboyset(self, ctx):
        """Owner-only customization for FATBOY's profile."""
        await ctx.send_help()

    @fatboyset.command(name="show")
    @commands.is_owner()
    async def fatboyset_show(self, ctx):
        """Show current FatboyInfo configuration."""
        owner = await self.config.owner_label()
        description = await self.config.description()
        accent = await self.config.accent()
        enabled = await self.config.use_info_alias()
        active = self.bot.get_command("info") is self._alias_command and self._alias_command is not None
        await ctx.send(
            f"Owner: {owner}\nDescription: {description}\n"
            f"Color: #{accent:06X}\n"
            f"Info alias requested: {'yes' if enabled else 'no'}\n"
            f"Info alias active: {'yes' if active else 'no'}",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @fatboyset.command(name="owner")
    @commands.is_owner()
    async def fatboyset_owner(self, ctx, *, label: str):
        """Set the public owner display name (max 80 characters)."""
        label = label.strip()
        if not 1 <= len(label) <= 80:
            await ctx.send("Owner label must be 1–80 characters.")
            return
        await self.config.owner_label.set(label)
        await ctx.send("Owner label updated.")

    @fatboyset.command(name="description")
    @commands.is_owner()
    async def fatboyset_description(self, ctx, *, text: str):
        """Change the profile description (max 450 characters)."""
        text = text.strip()
        if not 1 <= len(text) <= 450:
            await ctx.send("Description must be 1–450 characters.")
            return
        await self.config.description.set(text)
        await ctx.send("Profile description updated.")

    @fatboyset.command(name="color")
    @commands.is_owner()
    async def fatboyset_color(self, ctx, hex_color: str):
        """Set embed color using a six-digit hex value, e.g. #7C3AED."""
        if not re.fullmatch(r"#?[0-9A-Fa-f]{6}", hex_color):
            await ctx.send("Provide a six-digit color, for example #7C3AED.")
            return
        await self.config.accent.set(int(hex_color.lstrip("#"), 16))
        await ctx.send("Profile accent color updated.")

    @fatboyset.command(name="infoalias")
    @commands.is_owner()
    async def fatboyset_infoalias(self, ctx, enabled: bool):
        """Enable or disable the reversible ~info replacement (on/off)."""
        await self.config.use_info_alias.set(enabled)
        if enabled:
            active = await self.activate_info_alias()
            if active:
                await ctx.send("~info now displays FATBOY's profile.")
            else:
                await ctx.send(
                    "The ~info alias is occupied by another cog. "
                    "Use ~fatboy instead; no existing command was overwritten."
                )
        else:
            self._restore_info()
            await ctx.send("Red's original ~info command has been restored.")
