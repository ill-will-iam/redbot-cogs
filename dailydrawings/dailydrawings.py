"""Daily paper drawing challenges with a saved schedule and button voting."""

import asyncio
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
import logging
import random
import re
from typing import Optional
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from redbot.core import Config, commands

from .topics import TOPICS

LOG = logging.getLogger("red.will.dailydrawings")
UTC = timezone.utc
DRAW_SECONDS = 15 * 60
VOTE_SECONDS = 5 * 60
MIN_ARTISTS = 3
COLOUR = 0xE9B44C
DEFAULTS = dict(
    channel_id=None, enabled=False, time="20:00", timezone="America/New_York",
    last_run_date="", remaining_topics=[], last_topic="", active={},
)
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


def now_utc():
    return datetime.now(UTC)


def scheduled_at(day, settings):
    hour, minute = map(int, settings["time"].split(":"))
    return datetime.combine(day, time(hour, minute), ZoneInfo(settings["timezone"])).astimezone(UTC)


def is_due(settings, now):
    if not settings["enabled"] or not settings["channel_id"] or settings.get("active"):
        return False
    day = now.astimezone(ZoneInfo(settings["timezone"])).date()
    if settings["last_run_date"] == day.isoformat():
        return False
    # Catch up after a short outage, without surprising people the next morning.
    return 0 <= (now - scheduled_at(day, settings)).total_seconds() < 3600


def next_start(settings, now):
    day = now.astimezone(ZoneInfo(settings["timezone"])).date()
    if is_due(settings, now):
        return now
    if settings["last_run_date"] == day.isoformat() or scheduled_at(day, settings) <= now:
        day += timedelta(days=1)
    return scheduled_at(day, settings)


def pick_topic(settings):
    bank = {prompt: category for category, prompt in TOPICS}
    remaining = list(dict.fromkeys(
        prompt for prompt in settings["remaining_topics"] if prompt in bank
    ))
    if not remaining:
        remaining = list(bank)
        random.shuffle(remaining)
        if len(remaining) > 1 and remaining[0] == settings.get("last_topic"):
            remaining[0], remaining[1] = remaining[1], remaining[0]
    prompt = remaining.pop(0)
    settings["remaining_topics"] = remaining
    settings["last_topic"] = prompt
    return bank[prompt], prompt


def image_attachment(attachments):
    """Accept one attached still image; links and animated files are not entries."""
    if len(attachments) != 1:
        return None
    attachment = attachments[0]
    content_type = (attachment.content_type or "").lower()
    if not attachment.filename.lower().endswith(IMAGE_EXTENSIONS):
        return None
    if content_type and content_type not in {"image/png", "image/jpeg", "image/webp"}:
        return None
    return attachment


@dataclass
class DrawingRound:
    guild_id: int
    channel_id: int
    token: str
    category: str
    topic: str
    draw_deadline: float
    phase: str = "announcing"
    vote_deadline: float = 0
    announcement_id: int = 0
    entries: dict = field(default_factory=dict)
    votes: dict = field(default_factory=dict)
    ballots: list = field(default_factory=list)
    views: dict = field(default_factory=dict)
    task: Optional[asyncio.Task] = None
    watcher: Optional[asyncio.Task] = None

    def data(self):
        return dict(
            guild_id=self.guild_id, channel_id=self.channel_id, token=self.token,
            category=self.category, topic=self.topic, draw_deadline=self.draw_deadline,
            phase=self.phase, vote_deadline=self.vote_deadline,
            announcement_id=self.announcement_id,
            entries={str(user_id): entry.copy() for user_id, entry in self.entries.items()},
            votes={str(user_id): entry_id for user_id, entry_id in self.votes.items()},
            ballots=[ballot.copy() for ballot in self.ballots],
        )

    @classmethod
    def restore(cls, data):
        game = cls(
            guild_id=int(data["guild_id"]), channel_id=int(data["channel_id"]),
            token=data["token"], category=data["category"], topic=data["topic"],
            draw_deadline=float(data["draw_deadline"]), phase=data["phase"],
            vote_deadline=float(data["vote_deadline"]),
            announcement_id=int(data["announcement_id"]),
            entries={int(key): value for key, value in data["entries"].items()},
            votes={int(key): int(value) for key, value in data["votes"].items()},
            ballots=data["ballots"],
        )
        if game.phase not in {"drawing", "voting"}:
            raise ValueError("Round was interrupted between phases")
        return game


class VoteView(discord.ui.View):
    def __init__(self, cog, game, entry_id, number):
        super().__init__(timeout=None)
        self.cog, self.game_token, self.entry_id = cog, game.token, entry_id
        button = discord.ui.Button(
            label=f"Vote for #{number}", style=discord.ButtonStyle.success,
            custom_id=f"daily-drawing:{game.token}:{entry_id}", emoji="🗳️",
        )
        button.callback = self.vote
        self.add_item(button)

    async def vote(self, interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        text = await self.cog.cast_vote(interaction, self.game_token, self.entry_id)
        await interaction.followup.send(text, ephemeral=True)


class DailyDrawings(commands.Cog):
    """Daily drawing on paper, fifteen minutes to create, then a community vote."""

    __author__ = "Will"
    __version__ = "1.0.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=52491310202602, force_registration=True)
        self.config.register_guild(**DEFAULTS)
        self.rounds = {}
        self._state_lock = asyncio.Lock()
        self._scheduler_task = None
        self._unloading = False

    def format_help_for_context(self, ctx):
        return (f"{super().format_help_for_context(ctx)}\n\n"
                f"Creator: {self.__author__}\nVersion: {self.__version__}")

    async def cog_load(self):
        self._scheduler_task = asyncio.create_task(self._scheduler())

    def cog_unload(self):
        # Keep the last saved state so a reload can recover an open window.
        self._unloading = True
        if self._scheduler_task:
            self._scheduler_task.cancel()
        for game in list(self.rounds.values()):
            self._detach(game)

    def _alive(self, game):
        return not self._unloading and self.rounds.get(game.guild_id) is game

    def _detach(self, game):
        if self.rounds.get(game.guild_id) is game:
            self.rounds.pop(game.guild_id)
        for view in game.views.values():
            view.stop()
        current = asyncio.current_task()
        tasks = []
        for task in (game.task, game.watcher):
            if task and task is not current and not task.done():
                task.cancel()
                tasks.append(task)
        return tasks

    async def _save(self, game):
        await self.config.guild_from_id(game.guild_id).active.set(game.data())

    def _channel(self, game):
        return self.bot.get_channel(game.channel_id)

    def _permissions(self, channel):
        permissions = channel.permissions_for(channel.guild.me)
        required = ("view_channel", "send_messages", "embed_links", "read_message_history")
        return [permission for permission in required if not getattr(permissions, permission)]

    async def _available(self, game):
        if not self._alive(game):
            return False
        guild = self.bot.get_guild(game.guild_id)
        disabled = guild is None or await self.bot.cog_disabled_in_guild(self, guild)
        if not self._alive(game):
            return False
        if disabled or self._channel(game) is None:
            await self._end(game)
            return False
        return True

    async def _disable_ballots(self, game):
        channel = self._channel(game)
        for message_id, view in game.views.items():
            for button in view.children:
                button.disabled = True
            view.stop()
            if channel:
                try:
                    await channel.get_partial_message(message_id).edit(view=view)
                except discord.HTTPException:
                    pass

    async def _end(self, game):
        async with self._state_lock:
            if not self._alive(game):
                return
            tasks = self._detach(game)
            await self.config.guild_from_id(game.guild_id).active.set({})
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self._disable_ballots(game)
        game.entries.clear()
        game.votes.clear()
        game.ballots.clear()

    async def _send(self, game, **kwargs):
        if not await self._available(game):
            return None
        return await self._channel(game).send(allowed_mentions=discord.AllowedMentions.none(), **kwargs)

    async def _watch(self, game):
        try:
            while await self._available(game):
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        except Exception:
            LOG.exception("Daily Drawings watcher failed")
            await self._end(game)

    def _launch(self, game):
        game.task = asyncio.create_task(self._run(game))
        game.watcher = asyncio.create_task(self._watch(game))

    async def _run(self, game):
        try:
            if game.phase == "drawing":
                await asyncio.sleep(max(0, game.draw_deadline - now_utc().timestamp()))
                if await self._available(game):
                    await self._open_voting(game)
            if game.phase == "voting" and await self._available(game):
                await asyncio.sleep(max(0, game.vote_deadline - now_utc().timestamp()))
                if await self._available(game):
                    await self._finish_voting(game)
        except asyncio.CancelledError:
            pass
        except Exception:
            LOG.exception("Daily Drawings round failed in guild %s", game.guild_id)
            await self._end(game)

    async def _restore(self):
        for guild_id in await self.config.all_guilds():
            async with self._state_lock:
                # Re-read under the deletion/write lock instead of restoring a stale snapshot.
                settings = await self.config.guild_from_id(int(guild_id)).all()
                if not settings.get("active") or int(guild_id) in self.rounds:
                    continue
                try:
                    game = DrawingRound.restore(settings["active"])
                    if game.guild_id != int(guild_id) or game.channel_id != settings["channel_id"]:
                        raise ValueError("Saved channel does not match configuration")
                    if not settings["enabled"] or self._channel(game) is None:
                        raise ValueError("Round no longer has an enabled channel")
                except (KeyError, TypeError, ValueError):
                    await self.config.guild_from_id(int(guild_id)).active.set({})
                    LOG.warning("Discarded interrupted Daily Drawings round in guild %s", guild_id)
                    continue
                self.rounds[game.guild_id] = game
            if not await self._available(game):
                continue
            if game.phase == "drawing" and now_utc().timestamp() >= game.draw_deadline + VOTE_SECONDS:
                await self._send(game, content="🖍️ The previous drawing round expired while the bot was offline. "
                                              "We'll meet again at the next daily drawing time.")
                await self._end(game)
                continue
            if game.phase == "voting":
                for ballot in game.ballots:
                    if ballot["entry_id"] not in game.entries:
                        continue
                    view = VoteView(self, game, ballot["entry_id"], ballot["number"])
                    game.views[ballot["message_id"]] = view
                    self.bot.add_view(view, message_id=ballot["message_id"])
            self._launch(game)

    async def _scheduler(self):
        try:
            await self.bot.wait_until_red_ready()
            await self._restore()
            while not self._unloading:
                settings_by_guild = await self.config.all_guilds()
                for guild_id, settings in settings_by_guild.items():
                    try:
                        if is_due(settings, now_utc()):
                            guild = self.bot.get_guild(int(guild_id))
                            if guild:
                                await self._start_round(guild, scheduled=True)
                    except Exception:
                        LOG.exception("Daily drawing schedule check failed in guild %s", guild_id)
                await asyncio.sleep(30)
        except asyncio.CancelledError:
            pass

    async def _start_round(self, guild, *, scheduled=False):
        async with self._state_lock:
            settings = await self.config.guild(guild).all()
            if not settings["enabled"] or not settings["channel_id"]:
                return "Set a channel first with the draw channel command."
            if scheduled and not is_due(settings, now_utc()):
                return "The configured daily time is not due."
            if guild.id in self.rounds:
                return "A drawing round is already running."
            if settings.get("active"):
                return "A saved drawing round is being restored. Try again in a moment."
            if await self.bot.cog_disabled_in_guild(self, guild):
                return "Daily Drawings is disabled in this server."
            channel = self.bot.get_channel(settings["channel_id"])
            if channel is None:
                return "The drawing channel is unavailable."
            missing = self._permissions(channel)
            if missing:
                return "Missing permissions in the drawing channel: " + ", ".join(missing)
            if not self.bot.intents.message_content:
                return "Enable Message Content Intent and restart the bot to receive image attachments."
            today = now_utc().astimezone(ZoneInfo(settings["timezone"])).date().isoformat()
            if settings["last_run_date"] == today:
                return "Today's drawing challenge has already been announced. The next one is tomorrow."
            category, topic = pick_topic(settings)
            game = DrawingRound(guild.id, channel.id, uuid4().hex, category, topic,
                                now_utc().timestamp() + DRAW_SECONDS)
            self.rounds[guild.id] = game
            settings["last_run_date"] = today
            settings["active"] = game.data()
            await self.config.guild(guild).set(settings)
        try:
            embed = discord.Embed(
                title="🖍️ It's time to draw!",
                description=(f"**Today's topic:** {topic}\n**Theme:** {category.title()}\n\n"
                             "We need **3 or more artists**! You have **15 minutes**.\n"
                             "Use **pen, pencil, crayons, markers or other physical materials "
                             "on paper**. **No digital drawing, AI, tracing apps or digital "
                             "assistance.** A photo or scan of your paper drawing is fine.\n\n"
                             "Upload **one photo** of your drawing here before "
                             f"<t:{int(game.draw_deadline)}:t> (<t:{int(game.draw_deadline)}:R>).\n"
                             "One entry each; a new photo replaces your earlier entry. "
                             "Then we vote! The winner gets props and cheers. 🎉"),
                colour=COLOUR,
            )
            announcement = await self._send(game, embed=embed)
            async with self._state_lock:
                if not self._alive(game) or announcement is None:
                    return "The round could not be opened."
                game.announcement_id = announcement.id
                game.phase = "drawing"
                await self._save(game)
                self._launch(game)
            return None
        except Exception:
            LOG.exception("Could not announce daily drawing in guild %s", guild.id)
            await self._end(game)
            return "The announcement failed; check the bot's permissions and logs."

    async def _allowed(self, source):
        user = source.user if isinstance(source, discord.Interaction) else source.author
        return (not user.bot and await self.bot.ignored_channel_or_guild(source)
                and await self.bot.allowed_by_whitelist_blacklist(user))

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild is None or message.author.bot or not message.attachments:
            return
        game = self.rounds.get(message.guild.id)
        if not game or game.channel_id != message.channel.id or game.phase != "drawing":
            return
        if not await self._available(game) or not await self._allowed(message):
            return
        attachment = image_attachment(message.attachments)
        if attachment is None:
            await message.reply("Please attach **one PNG, JPG or WebP photo** of your paper drawing.",
                                mention_author=False, allowed_mentions=discord.AllowedMentions.none())
            return
        async with self._state_lock:
            if not self._alive(game) or game.phase != "drawing" or now_utc().timestamp() >= game.draw_deadline:
                return
            replacing = message.author.id in game.entries
            game.entries[message.author.id] = dict(
                message_id=message.id, attachment_id=attachment.id, image_url=attachment.url,
            )
            await self._save(game)
        await message.reply("🖍️ Drawing replaced!" if replacing else "🖍️ Drawing entered! Good luck!",
                            mention_author=False, allowed_mentions=discord.AllowedMentions.none())

    async def _open_voting(self, game):
        async with self._state_lock:
            if not self._alive(game) or game.phase != "drawing":
                return
            game.phase = "preparing"
            await self._save(game)
            entries = list(game.entries.items())
        if len(entries) < MIN_ARTISTS:
            await self._send(game, content=(f"🖍️ Drawing time is up! We received **{len(entries)}** "
                                           "entries, but need **at least 3** for voting. "
                                           "Props to everyone who drew—let's try again tomorrow! 🎨"))
            await self._end(game)
            return
        random.shuffle(entries)
        for number, (user_id, entry) in enumerate(entries, 1):
            if not await self._available(game):
                return
            view = VoteView(self, game, user_id, number)
            embed = discord.Embed(title=f"🎨 Entry #{number}", description=game.topic, colour=COLOUR)
            embed.set_image(url=entry["image_url"])
            ballot_message = await self._send(game, embed=embed, view=view)
            async with self._state_lock:
                if not self._alive(game) or ballot_message is None:
                    view.stop()
                    return
                game.ballots.append(dict(entry_id=user_id, message_id=ballot_message.id, number=number))
                game.views[ballot_message.id] = view
                await self._save(game)
        async with self._state_lock:
            if not self._alive(game):
                return
            game.phase = "voting"
            game.vote_deadline = now_utc().timestamp() + VOTE_SECONDS
            await self._save(game)
        await self._send(game, content=("🗳️ **Voting is open for 5 minutes!**\n"
                                      "Use the button beneath your favourite drawing. "
                                      "Everyone gets **one vote**; changing it replaces your previous vote. "
                                      "You cannot vote for yourself.\n"
                                      f"Voting closes <t:{int(game.vote_deadline)}:R>."))

    async def cast_vote(self, interaction, token, entry_id):
        if interaction.guild is None or interaction.user.bot:
            return "Only server members can vote."
        game = self.rounds.get(interaction.guild.id)
        if not game or game.token != token or game.channel_id != interaction.channel_id:
            return "This drawing round has ended."
        if not await self._available(game):
            return "This drawing round has ended."
        if not await self._allowed(interaction):
            return "You cannot vote here."
        async with self._state_lock:
            if not self._alive(game) or game.phase != "voting":
                return "Voting is not open for this round."
            if now_utc().timestamp() >= game.vote_deadline:
                return "Voting has closed."
            if entry_id not in game.entries:
                return "That entry is no longer in the round."
            if entry_id == interaction.user.id:
                return "You cannot vote for your own drawing."
            previous = game.votes.get(interaction.user.id)
            game.votes[interaction.user.id] = entry_id
            await self._save(game)
        return "🗳️ Vote changed!" if previous is not None else "🗳️ Vote recorded! Thanks for cheering the artists on."

    async def _finish_voting(self, game):
        async with self._state_lock:
            if not self._alive(game) or game.phase != "voting":
                return
            game.phase = "finishing"
            await self._save(game)
            tally = Counter(entry_id for entry_id in game.votes.values() if entry_id in game.entries)
            highest = max(tally.values(), default=0)
            winners = [user_id for user_id, count in tally.items() if count == highest]
        if not winners:
            await self._send(game, content="🎨 No votes this time—props and cheers to everyone who drew! 👏")
        else:
            title = "🎉 Daily Drawing winner!" if len(winners) == 1 else "🎉 Daily Drawing joint winners!"
            # Keep even a large shared tie within Discord's embed size limit.
            for offset in range(0, len(winners), 100):
                names = ", ".join(f"<@{user_id}>" for user_id in winners[offset:offset + 100])
                embed = discord.Embed(
                    title=title,
                    description=f"{names}\n**{highest} vote{'s' if highest != 1 else ''}** each!\n\n"
                                f"**Topic:** {game.topic}\nProps, cheers and a big round of applause! 👏🖍️",
                    colour=COLOUR,
                )
                if len(winners) == 1 and winners[0] in game.entries:
                    embed.set_image(url=game.entries[winners[0]]["image_url"])
                await self._send(game, embed=embed)
        await self._end(game)

    async def _remove_entry(self, game, user_id):
        async with self._state_lock:
            if not self._alive(game) or game.phase not in {"drawing", "voting"}:
                return "Entries cannot be removed at this moment."
            if game.entries.pop(user_id, None) is None:
                return "That user has no entry in this round."
            game.votes = {voter: target for voter, target in game.votes.items() if target != user_id}
            removed = [ballot for ballot in game.ballots if ballot["entry_id"] == user_id]
            game.ballots = [ballot for ballot in game.ballots if ballot["entry_id"] != user_id]
            cancel = game.phase == "voting" and len(game.entries) < MIN_ARTISTS
            await self._save(game)
        for ballot in removed:
            view = game.views.get(ballot["message_id"])
            if view:
                for button in view.children:
                    button.disabled = True
                view.stop()
                try:
                    await self._channel(game).get_partial_message(ballot["message_id"]).edit(view=view)
                except discord.HTTPException:
                    pass
        if cancel:
            await self._send(game, content="Voting cancelled: fewer than three eligible drawings remain.")
            await self._end(game)
        return "Entry removed from the round. The original Discord image remains."

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        await self._deleted_message(payload.guild_id, payload.channel_id, payload.message_id)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload):
        for message_id in payload.message_ids:
            await self._deleted_message(payload.guild_id, payload.channel_id, message_id)

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload):
        game = self.rounds.get(payload.guild_id)
        if not game or game.channel_id != payload.channel_id or "attachments" not in payload.data:
            return
        for entry in game.entries.values():
            if entry["message_id"] == payload.message_id:
                remaining_ids = {int(attachment["id"]) for attachment in payload.data["attachments"]}
                if entry["attachment_id"] not in remaining_ids:
                    await self._deleted_message(payload.guild_id, payload.channel_id, payload.message_id)
                return

    async def _deleted_message(self, guild_id, channel_id, message_id):
        game = self.rounds.get(guild_id)
        if not game or game.channel_id != channel_id:
            return
        for user_id, entry in list(game.entries.items()):
            if entry["message_id"] == message_id:
                if game.phase == "preparing":
                    await self._end(game)
                else:
                    await self._remove_entry(game, user_id)
                return
        if message_id == game.announcement_id or any(ballot["message_id"] == message_id for ballot in game.ballots):
            # Missing gallery buttons would make continued voting unfair.
            await self._end(game)

    @commands.group(name="draw", aliases=["dailydraw"], invoke_without_command=True)
    @commands.guild_only()
    async def draw(self, ctx):
        """Daily paper drawing challenges. Use channel, time, status, start or off."""
        await DailyDrawings.draw_status.callback(self, ctx)

    @draw.command(name="status")
    async def draw_status(self, ctx):
        """Show the configured channel, daily schedule and active round."""
        settings = await self.config.guild(ctx.guild).all()
        channel = f"<#{settings['channel_id']}>" if settings["channel_id"] else "Not configured"
        status = "On" if settings["enabled"] else "Off"
        next_run = f"<t:{int(next_start(settings, now_utc()).timestamp())}:F>" if settings["enabled"] else "Paused"
        game = self.rounds.get(ctx.guild.id)
        current = (f"{game.phase.title()} • {len(game.entries)} entries • {len(game.votes)} votes"
                   if game else "No active round")
        target = self.bot.get_channel(settings["channel_id"]) if settings["channel_id"] else None
        permission_status = (", ".join(self._permissions(target)) or "none") if target else "channel unavailable"
        intent_status = "on" if self.bot.intents.message_content else "off"
        await ctx.send(f"🖍️ **Daily Drawings**\nChannel: {channel}\nDaily announcements: **{status}**\n"
                       f"Schedule: **{settings['time']} {settings['timezone']}**\nNext: {next_run}\n"
                       f"Round: {current}\nDrawing: **15 minutes** • Voting: **5 minutes** • Minimum: **3 artists**"
                       f"\nMessage Content Intent: **{intent_status}** • Missing permissions: **{permission_status}**",
                       allowed_mentions=discord.AllowedMentions.none())

    @draw.command(name="channel")
    @commands.admin_or_permissions(manage_guild=True)
    async def draw_channel(self, ctx, channel: discord.TextChannel):
        """Set the daily drawing channel and enable daily announcements."""
        missing = self._permissions(channel)
        if missing:
            await ctx.send("Missing permissions there: " + ", ".join(missing))
            return
        game = self.rounds.get(ctx.guild.id)
        if game:
            await self._end(game)
        async with self._state_lock:
            settings = await self.config.guild(ctx.guild).all()
            settings.update(channel_id=channel.id, enabled=True)
            await self.config.guild(ctx.guild).set(settings)
        await ctx.send(f"🖍️ Daily Drawings enabled in {channel.mention}. Time: **{settings['time']} {settings['timezone']}**; "
                       f"use `{ctx.clean_prefix}draw time HH:MM` to change it.",
                       allowed_mentions=discord.AllowedMentions.none())

    @draw.command(name="time")
    @commands.admin_or_permissions(manage_guild=True)
    async def draw_time(self, ctx, daily_time: str, timezone_name: Optional[str] = None):
        """Set a 24-hour daily time, optionally with an IANA timezone name."""
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", daily_time):
            await ctx.send("Use a 24-hour time such as **20:00** or **21:00**.")
            return
        async with self._state_lock:
            settings = await self.config.guild(ctx.guild).all()
            zone = timezone_name or settings["timezone"]
            try:
                ZoneInfo(zone)
            except (ZoneInfoNotFoundError, ValueError):
                await ctx.send("Unknown timezone. Use **America/New_York** for Eastern time.")
                return
            settings.update(time=daily_time, timezone=zone)
            await self.config.guild(ctx.guild).set(settings)
        await ctx.send(f"🖍️ Daily drawing time set to **{daily_time} {zone}**. This applies to future rounds.")

    @draw.command(name="start")
    @commands.admin_or_permissions(manage_guild=True)
    async def draw_start(self, ctx):
        """Announce today's challenge now. Counts as today's daily announcement."""
        error = await self._start_round(ctx.guild)
        if error:
            await ctx.send(error)
        elif ctx.channel.id != (await self.config.guild(ctx.guild).channel_id()):
            await ctx.send("Today's drawing challenge is open in the configured channel.")

    @draw.command(name="cancel")
    @commands.admin_or_permissions(manage_guild=True)
    async def draw_cancel(self, ctx):
        """Cancel the current round; the next scheduled day is unaffected."""
        game = self.rounds.get(ctx.guild.id)
        if not game:
            await ctx.send("There is no active drawing round.")
            return
        await self._send(game, content="🖍️ This drawing round has been cancelled by staff.")
        await self._end(game)
        await ctx.send("Drawing round cancelled.")

    @draw.command(name="off")
    @commands.admin_or_permissions(manage_guild=True)
    async def draw_off(self, ctx):
        """Pause daily announcements and cancel any active round."""
        async with self._state_lock:
            await self.config.guild(ctx.guild).enabled.set(False)
        game = self.rounds.get(ctx.guild.id)
        if game:
            await self._end(game)
        await ctx.send("Daily Drawings paused. Set the channel again to enable it.")

    @draw.command(name="remove")
    @commands.admin_or_permissions(manage_guild=True)
    async def draw_remove(self, ctx, member: discord.Member):
        """Remove a drawing for rule violations. Does not delete the Discord photo."""
        game = self.rounds.get(ctx.guild.id)
        await ctx.send(await self._remove_entry(game, member.id) if game else "There is no active drawing round.")

    async def red_delete_data_for_user(self, *, requester, user_id):
        # Cancel first, while writes/callbacks are excluded by the same lock.
        affected = []
        async with self._state_lock:
            for game in list(self.rounds.values()):
                if user_id in game.entries or user_id in game.votes:
                    tasks = self._detach(game)
                    await self.config.guild_from_id(game.guild_id).active.set({})
                    affected.append((game, tasks))
            # Include saved rounds not yet restored after cog_load.
            for guild_id, settings in (await self.config.all_guilds()).items():
                active = settings.get("active", {})
                if str(user_id) in active.get("entries", {}) or str(user_id) in active.get("votes", {}):
                    await self.config.guild_from_id(int(guild_id)).active.set({})
        for game, tasks in affected:
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await self._disable_ballots(game)
            game.entries.clear()
            game.votes.clear()
            game.ballots.clear()
