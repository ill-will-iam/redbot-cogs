"""Simple, per-server birthday reminders for Red-DiscordBot 3.5+."""

import io
import json
import logging
from datetime import datetime, time, date
from typing import Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord.ext import tasks
from redbot.core import Config, commands

from .dates import age_on, display_day, next_birthday, parse_birthday

log = logging.getLogger("red.birthday")


class Birthday(commands.Cog):
    """Remember birthdays and celebrate them in a chosen channel."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=7407271985, force_registration=True)
        self.config.register_member(birthday=None, show_age=False)
        self.config.register_guild(channel_id=None, timezone="UTC", announce_at="09:00", last_announced=None)
        self.check_birthdays.start()

    def cog_unload(self):
        self.check_birthdays.cancel()

    @staticmethod
    def _clean_name(member: discord.Member) -> str:
        return discord.utils.escape_mentions(discord.utils.escape_markdown(member.display_name))

    async def _read_birthday(self, member: discord.Member):
        return await self.config.member(member).birthday()

    async def _set_birthday(self, ctx: commands.Context, raw: str):
        try:
            today = datetime.now(ZoneInfo(await self.config.guild(ctx.guild).timezone())).date()
            birthday = parse_birthday(raw, today=today)
        except ValueError as exc:
            await ctx.send(str(exc))
            return
        await self.config.member(ctx.author).birthday.set(birthday)
        readable = display_day(birthday["month"], birthday["day"])
        year_saved = " Your birth year was saved but is hidden from other members by default." if birthday["year"] else ""
        await ctx.send(f"🎂 {ctx.author.mention}, your birthday is set to **{readable}**!{year_saved}", allowed_mentions=discord.AllowedMentions.none())

    @commands.guild_only()
    @commands.group(name="birthday", invoke_without_command=True)
    async def birthday(self, ctx: commands.Context, *, input_text: Optional[str] = None):
        """Show your birthday, set one directly, or check another member.

        Examples: [p]birthday 07/27/1985 or [p]birthday @member
        """
        if input_text:
            if "/" in input_text:
                await self._set_birthday(ctx, input_text)
                return
            try:
                member = await commands.MemberConverter().convert(ctx, input_text)
            except commands.BadArgument:
                await ctx.send("Use `[p]birthday 07/27/1985`, `[p]birthday set 07/27/1985`, or `[p]birthday @member`.".replace("[p]", ctx.clean_prefix))
                return
        else:
            member = ctx.author

        data = await self._read_birthday(member)
        if not data:
            if member.id == ctx.author.id:
                await ctx.send(f"You haven't set your birthday yet! Try `{ctx.clean_prefix}birthday 07/27/1985`.")
            else:
                await ctx.send(f"{self._clean_name(member)} hasn't set a birthday here.")
            return

        day_text = display_day(data["month"], data["day"])
        today = datetime.now(ZoneInfo(await self.config.guild(ctx.guild).timezone())).date()
        next_day = next_birthday(today, data["month"], data["day"])
        remaining = (next_day - today).days
        suffix = "today! 🎉" if remaining == 0 else ("tomorrow!" if remaining == 1 else f"in **{remaining} days**.")
        age_note = ""
        if data["year"] is not None and await self.config.member(member).show_age():
            age_note = f" Turning **{age_on(next_day, data['year'])}**."
        await ctx.send(f"🎂 **{self._clean_name(member)}**'s birthday is **{day_text}** — {suffix}{age_note}", allowed_mentions=discord.AllowedMentions.none())

    @birthday.command(name="set")
    async def birthday_set(self, ctx: commands.Context, birthday: str):
        """Set your birthday: MM/DD/YYYY or MM/DD (year optional)."""
        await self._set_birthday(ctx, birthday)

    @birthday.command(name="remove", aliases=["delete", "clear"])
    async def birthday_remove(self, ctx: commands.Context):
        """Remove your saved birthday and age visibility setting."""
        await self.config.member(ctx.author).clear()
        await ctx.send("Your birthday has been removed from this server.")

    @birthday.command(name="age")
    async def birthday_age(self, ctx: commands.Context, setting: Literal["on", "off"]):
        """Allow/hide showing your age to others (off by default)."""
        data = await self._read_birthday(ctx.author)
        if not data or data["year"] is None:
            await ctx.send("Set a birthday with a four-digit year first.")
            return
        await self.config.member(ctx.author).show_age.set(setting == "on")
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
        records = await self.config.all_members(guild)
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
        """Remove birthday information for a user in every guild."""
        all_data = await self.config.all_members()
        for guild_id, member_data in all_data.items():
            if user_id in member_data or str(user_id) in member_data:
                await self.config.member_from_ids(int(guild_id), user_id).clear()

    async def red_get_data_for_user(self, *, user_id: int):
        """Provide a portable JSON copy of stored birthday data."""
        all_data = await self.config.all_members()
        owned = {}
        for guild_id, member_data in all_data.items():
            info = member_data.get(user_id, member_data.get(str(user_id)))
            if info and info.get("birthday"):
                owned[str(guild_id)] = info
        if not owned:
            return {}
        return {"birthday.json": io.BytesIO(json.dumps(owned, indent=2).encode("utf-8"))}
