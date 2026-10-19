"""Global user birthdays and per-server celebrations for Red-DiscordBot 3.5+."""

import io
import json
import logging
from datetime import datetime, time, date, timezone
from typing import Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord.ext import tasks
from redbot.core import Config, commands

from .dates import age_on, display_day, next_birthday, parse_birthday

log = logging.getLogger("red.birthday")


class Birthday(commands.Cog):
    """Save a birthday once for all servers using this bot."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=7407271985, force_registration=True)
        self.config.register_user(birthday=None, show_age=False)
        # Retain the old MEMBER schema solely for explicit migration/deletion.
        self.config.register_member(birthday=None, show_age=False)
        self.config.register_guild(channel_id=None, timezone="UTC", announce_at="09:00", last_announced=None)
        self.check_birthdays.start()

    def cog_unload(self):
        self.check_birthdays.cancel()

    @staticmethod
    def _clean_name(member: discord.abc.User) -> str:
        return discord.utils.escape_mentions(discord.utils.escape_markdown(member.display_name))

    async def _today_for_ctx(self, ctx: commands.Context) -> date:
        """Use the current server's timezone, or UTC in a DM."""
        if ctx.guild is None:
            return datetime.now(timezone.utc).date()
        return datetime.now(ZoneInfo(await self.config.guild(ctx.guild).timezone())).date()

    async def _read_birthday(self, user: discord.abc.User):
        return await self.config.user(user).birthday()

    async def _clear_legacy_user(self, user_id: int):
        """Erase this user's obsolete per-guild birthday records."""
        all_members = await self.config.all_members()
        for guild_id, users in all_members.items():
            if user_id in users or str(user_id) in users:
                await self.config.member_from_ids(int(guild_id), user_id).clear()

    async def _set_birthday(self, ctx: commands.Context, raw: str):
        try:
            birthday = parse_birthday(raw, today=await self._today_for_ctx(ctx))
        except ValueError as exc:
            await ctx.send(str(exc))
            return
        await self.config.user(ctx.author).birthday.set(birthday)
        # A changed birthday cannot inherit a previous age-disclosure opt-in.
        await self.config.user(ctx.author).show_age.set(False)
        await self._clear_legacy_user(ctx.author.id)
        readable = display_day(birthday["month"], birthday["day"])
        year_saved = " Your birth year is private; your age is hidden by default." if birthday["year"] else ""
        await ctx.send(f"🎂 Birthday saved globally as **{readable}**! I'll remember it in every server where I'm present.{year_saved}", allowed_mentions=discord.AllowedMentions.none())

    @commands.group(name="birthday", invoke_without_command=True)
    async def birthday(self, ctx: commands.Context, *, input_text: Optional[str] = None):
        """Show your birthday, set one directly, or check another member.

        Examples: [p]birthday 01/01/2000 or [p]birthday @member
        """
        if input_text:
            if "/" in input_text:
                await self._set_birthday(ctx, input_text)
                return
            if ctx.guild is None:
                await ctx.send("In DMs you can view or set your own birthday. To check another member, use this command in a server.")
                return
            try:
                member = await commands.MemberConverter().convert(ctx, input_text)
            except commands.BadArgument:
                await ctx.send("Use `[p]birthday 01/01/2000`, `[p]birthday set 01/01/2000`, or `[p]birthday @member`.".replace("[p]", ctx.clean_prefix))
                return
        else:
            member = ctx.author

        data = await self._read_birthday(member)
        if not data:
            if member.id == ctx.author.id:
                await ctx.send(f"You haven't set your global birthday yet! Try `{ctx.clean_prefix}birthday 01/01/2000` or `{ctx.clean_prefix}birthday import` in the server where you previously saved it.")
            else:
                await ctx.send(f"{self._clean_name(member)} hasn't set a global birthday.")
            return

        day_text = display_day(data["month"], data["day"])
        today = await self._today_for_ctx(ctx)
        next_day = next_birthday(today, data["month"], data["day"])
        remaining = (next_day - today).days
        suffix = "today! 🎉" if remaining == 0 else ("tomorrow!" if remaining == 1 else f"in **{remaining} days**.")
        age_note = ""
        if data["year"] is not None and await self.config.user(member).show_age():
            age_note = f" Turning **{age_on(next_day, data['year'])}**."
        await ctx.send(f"🎂 **{self._clean_name(member)}**'s birthday is **{day_text}** — {suffix}{age_note}", allowed_mentions=discord.AllowedMentions.none())

    @birthday.command(name="set")
    async def birthday_set(self, ctx: commands.Context, birthday: str):
        """Set your birthday: MM/DD/YYYY or MM/DD (year optional)."""
        await self._set_birthday(ctx, birthday)

    @birthday.command(name="import")
    @commands.guild_only()
    async def birthday_import(self, ctx: commands.Context):
        """Opt in to importing your own birthday previously saved in this server."""
        if await self._read_birthday(ctx.author):
            await ctx.send("You already have a global birthday. To change it, use the birthday set command.")
            return
        legacy = await self.config.member(ctx.author).birthday()
        if not legacy:
            await ctx.send("No old birthday was found for you in this server. You can set a global birthday directly instead.")
            return
        try:
            next_birthday(await self._today_for_ctx(ctx), legacy["month"], legacy["day"])
        except (KeyError, ValueError, TypeError):
            await ctx.send("Your old birthday isn't valid. Please set a new birthday manually.")
            return
        await self.config.user(ctx.author).birthday.set(legacy)
        # An opt-in from one guild is not consent to expose age in every guild.
        await self.config.user(ctx.author).show_age.set(False)
        await self._clear_legacy_user(ctx.author.id)
        await ctx.send(
            f"🎂 Your birthday **{display_day(legacy['month'], legacy['day'])}** is now saved globally. "
            "Age sharing remains off, and your old server-specific records were cleared."
        )

    @birthday.command(name="remove", aliases=["delete", "clear"])
    async def birthday_remove(self, ctx: commands.Context):
        """Remove your global birthday and any old per-server data."""
        await self.config.user(ctx.author).clear()
        await self._clear_legacy_user(ctx.author.id)
        await ctx.send("Your birthday has been removed globally, including any old server-specific records.")

    @birthday.command(name="age")
    async def birthday_age(self, ctx: commands.Context, setting: Literal["on", "off"]):
        """Allow/hide showing your age to others (off by default)."""
        data = await self._read_birthday(ctx.author)
        if not data or data["year"] is None:
            await ctx.send("Set a birthday with a four-digit year first.")
            return
        await self.config.user(ctx.author).show_age.set(setting == "on")
        await ctx.send(f"Showing your age to other members is now **{setting}**.")

    async def _resolve_member(self, guild: discord.Guild, user_id: int):
        member = guild.get_member(user_id)
        if member is not None:
            return member
        try:
            return await guild.fetch_member(user_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    async def _birthdays_in(self, guild: discord.Guild, today: date):
        """Return present members with configured birthdays, sorted by next observed date."""
        records = await self.config.all_users()
        entries = []
        for user_id, values in records.items():
            data = values.get("birthday")
            if not data:
                continue
            try:
                upcoming = next_birthday(today, data["month"], data["day"])
            except (ValueError, KeyError, TypeError):
                continue
            entries.append((upcoming, int(user_id), data, bool(values.get("show_age"))))
        entries.sort(key=lambda entry: (entry[0], entry[1]))
        return entries

    @birthday.command(name="upcoming", aliases=["list", "next"])
    @commands.guild_only()
    async def birthday_upcoming(self, ctx: commands.Context, count: int = 10):
        """Show the next 1–20 member birthdays (10 by default)."""
        if not 1 <= count <= 20:
            await ctx.send("Choose a number between 1 and 20.")
            return
        today = datetime.now(ZoneInfo(await self.config.guild(ctx.guild).timezone())).date()
        entries = await self._birthdays_in(ctx.guild, today)
        lines = []
        for upcoming, user_id, data, show_age in entries:
            member = await self._resolve_member(ctx.guild, user_id)
            if member is None:
                continue
            days = (upcoming - today).days
            when = "today" if days == 0 else ("tomorrow" if days == 1 else f"in {days} days")
            extra = f" · turning {age_on(upcoming, data['year'])}" if show_age and data["year"] is not None else ""
            lines.append(f"• **{self._clean_name(member)}** — {upcoming:%b %d} ({when}){extra}")
            if len(lines) >= count:
                break
        if not lines:
            await ctx.send("No birthdays have been saved by current server members yet.")
            return
        await ctx.send("🎂 **Upcoming birthdays**\n" + "\n".join(lines), allowed_mentions=discord.AllowedMentions.none())

    @birthday.command(name="today")
    @commands.guild_only()
    async def birthday_today(self, ctx: commands.Context):
        """See who's celebrating today (according to the server timezone)."""
        today = datetime.now(ZoneInfo(await self.config.guild(ctx.guild).timezone())).date()
        entries = await self._birthdays_in(ctx.guild, today)
        names = []
        for upcoming, user_id, _data, _show_age in entries:
            if upcoming != today:
                break
            member = await self._resolve_member(ctx.guild, user_id)
            if member is not None:
                names.append(f"**{self._clean_name(member)}**")
        await ctx.send("🎉 Today's birthdays: " + ", ".join(names) if names else "No birthdays today. 🎂", allowed_mentions=discord.AllowedMentions.none())

    @birthday.command(name="channel")
    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    async def birthday_channel(self, ctx: commands.Context, *, channel: Optional[str] = None):
        """Set a birthday announcement channel, show it, or disable with 'off'."""
        if channel is None:
            current = await self.config.guild(ctx.guild).channel_id()
            await ctx.send(f"Birthday announcement channel: {f'<#{current}>' if current else 'disabled'}.", allowed_mentions=discord.AllowedMentions.none())
            return
        if channel.lower() in ("off", "disable", "none"):
            await self.config.guild(ctx.guild).channel_id.set(None)
            await ctx.send("Automatic birthday announcements disabled.")
            return
        try:
            destination = await commands.TextChannelConverter().convert(ctx, channel)
        except commands.BadArgument:
            await ctx.send("Please mention a text channel, e.g. `#birthdays`, or use `off`.")
            return
        me = ctx.guild.me
        if not destination.permissions_for(me).send_messages:
            await ctx.send("I don't have permission to send messages in that channel.")
            return
        await self.config.guild(ctx.guild).channel_id.set(destination.id)
        await ctx.send(f"Birthday announcements will be posted in {destination.mention}.", allowed_mentions=discord.AllowedMentions.none())

    @birthday.command(name="timezone", aliases=["tz"])
    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    async def birthday_timezone(self, ctx: commands.Context, *, name: Optional[str] = None):
        """Set an IANA timezone, e.g. America/Vancouver or America/New_York."""
        if name is None:
            await ctx.send(f"Birthday timezone: `{await self.config.guild(ctx.guild).timezone()}`")
            return
        try:
            ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            await ctx.send("Unknown timezone. Example: `America/Vancouver` or `America/New_York`.")
            return
        await self.config.guild(ctx.guild).timezone.set(name)
        await ctx.send(f"Birthday timezone set to `{name}`.")

    @birthday.command(name="time")
    @commands.admin_or_permissions(manage_guild=True)
    @commands.guild_only()
    async def birthday_time(self, ctx: commands.Context, hhmm: Optional[str] = None):
        """Set daily announcement time HH:MM, 24-hour format in server timezone."""
        if hhmm is None:
            await ctx.send(f"Announcement time: `{await self.config.guild(ctx.guild).announce_at()}` (server timezone).")
            return
        try:
            moment = datetime.strptime(hhmm, "%H:%M").time()
            if len(hhmm) != 5:
                raise ValueError()
        except ValueError:
            await ctx.send("Use 24-hour `HH:MM`, such as `09:00` or `19:30`.")
            return
        await self.config.guild(ctx.guild).announce_at.set(moment.strftime("%H:%M"))
        await ctx.send(f"Birthday announcements are set for **{moment:%H:%M}** in the server timezone.")

    @tasks.loop(minutes=5)
    async def check_birthdays(self):
        """One announcement per guild per local calendar day; catches up after short downtime."""
        for guild in list(self.bot.guilds):
            try:
                await self._announce_for_guild(guild)
            except Exception:
                log.exception("Birthday announcement check failed in guild %s", guild.id)

    @check_birthdays.before_loop
    async def before_check_birthdays(self):
        await self.bot.wait_until_ready()

    async def _announce_for_guild(self, guild: discord.Guild):
        settings = await self.config.guild(guild).all()
        channel_id = settings.get("channel_id")
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        now = datetime.now(ZoneInfo(settings["timezone"]))
        today = now.date()
        if settings.get("last_announced") == today.isoformat():
            return
        announcement_time = time.fromisoformat(settings["announce_at"])
        if now.time().replace(tzinfo=None) < announcement_time:
            return
        entries = await self._birthdays_in(guild, today)
        lines = []
        for upcoming, user_id, data, show_age in entries:
            if upcoming != today:
                break
            member = await self._resolve_member(guild, user_id)
            if member is None:
                continue
            extra = f" — turning **{age_on(today, data['year'])}**!" if show_age and data["year"] is not None else "!"
            lines.append(f"🎈 Happy birthday, **{self._clean_name(member)}**{extra}")
        if not lines:
            return
        await channel.send("🎉 **It's birthday time!** 🎂\n" + "\n".join(lines) + "\nHope you have a great day!", allowed_mentions=discord.AllowedMentions.none())
        await self.config.guild(guild).last_announced.set(today.isoformat())

    async def red_delete_data_for_user(
        self,
        *,
        requester: Literal["discord_deleted_user", "owner", "user", "user_strict"],
        user_id: int,
    ):
        """Remove both global and legacy birthday information for a user."""
        await self.config.user_from_id(user_id).clear()
        await self._clear_legacy_user(user_id)

    async def red_get_data_for_user(self, *, user_id: int):
        """Provide a portable JSON copy of global and obsolete local records."""
        owned = {}
        global_record = await self.config.user_from_id(user_id).all()
        if global_record.get("birthday"):
            owned["global"] = global_record
        all_members = await self.config.all_members()
        legacy = {}
        for guild_id, members in all_members.items():
            old = members.get(user_id, members.get(str(user_id)))
            if old and old.get("birthday"):
                legacy[str(guild_id)] = old
        if legacy:
            owned["legacy_per_server"] = legacy
        if not owned:
            return {}
        return {"birthday.json": io.BytesIO(json.dumps(owned, indent=2).encode("utf-8"))}
