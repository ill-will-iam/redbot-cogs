"""A chat-first frog rescue game, without external services or dependencies."""

import asyncio
import logging
import math
import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

import discord
from redbot.core import Config, commands

from .words import WORDS

LOG = logging.getLogger("red.will.frogpond")
COLOUR = 0x73C75A
MIN_ROUNDS = 10
MAX_ROUNDS = 20
DEFAULT_ROUNDS = 10


def scramble(word):
    """Never display the answer unchanged, even if random shuffles repeat."""
    letters = list(word)
    for _ in range(12):
        random.shuffle(letters)
        shuffled = "".join(letters)
        if shuffled != word:
            return shuffled.upper()
    for index in range(1, len(word)):
        shuffled = word[index:] + word[:index]
        if shuffled != word:
            return shuffled.upper()
    raise ValueError("A puzzle needs at least two different letters.")


def vowel_hint(word):
    return " ".join(letter.upper() if letter in "aeiou" else "_" for letter in word)


@dataclass
class PondGame:
    channel: object
    starter_id: int
    puzzles: list
    seconds: int
    golden_round: int
    points: Counter = field(default_factory=Counter)
    solves: Counter = field(default_factory=Counter)
    event: asyncio.Event = field(default_factory=asyncio.Event)
    answer: str = ""
    round_index: int = 0
    deadline: float = 0.0
    accepting: bool = False
    winner_id: Optional[int] = None
    award: int = 0
    hops: int = 0
    cancelled: bool = False
    task: Optional[asyncio.Task] = None
    watcher: Optional[asyncio.Task] = None


class FrogPond(commands.Cog):
    """Unscramble pond words, catch golden flies, and get the frog home."""

    __author__ = "Will"
    __version__ = "1.1.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=524913102026, force_registration=True)
        self.config.register_guild(seconds=25, scores={}, remaining_words=[], last_word="")
        # At most one game per server, with two small tasks per active game.
        self.games = {}
        self._data_lock = asyncio.Lock()

    def format_help_for_context(self, ctx):
        return (
            f"{super().format_help_for_context(ctx)}\n\n"
            f"Creator: {self.__author__}\nVersion: {self.__version__}"
        )

    async def cog_check(self, ctx):
        return ctx.guild is not None

    def cog_unload(self):
        for game in list(self.games.values()):
            self._cancel(game)

    def _active(self, game):
        return not game.cancelled and self.games.get(game.channel.guild.id) is game

    def _cancel(self, game):
        game.cancelled = True
        game.accepting = False
        game.event.set()
        if self.games.get(game.channel.guild.id) is game:
            self.games.pop(game.channel.guild.id, None)
        game.points.clear()
        game.solves.clear()
        game.winner_id = None
        game.starter_id = 0
        current = asyncio.current_task()
        tasks = []
        for task in (game.task, game.watcher):
            if task and task is not current and not task.done():
                task.cancel()
                tasks.append(task)
        return tasks

    def _acro_active(self, channel):
        acro = self.bot.get_cog("AcroGame")
        game = getattr(acro, "rounds", {}).get(channel.guild.id)
        return game is not None and game.channel_id == channel.id

    async def _available(self, game):
        if not self._active(game):
            return False
        disabled = await self.bot.cog_disabled_in_guild(self, game.channel.guild)
        if not self._active(game):
            return False
        if disabled or self._acro_active(game.channel):
            self._cancel(game)
            return False
        return True

    async def _watch(self, game):
        try:
            while await self._available(game):
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        except Exception:
            LOG.exception("Frog Pond watcher failed")
            self._cancel(game)

    async def _send(self, game, **kwargs):
        if not await self._available(game):
            return False
        await game.channel.send(allowed_mentions=discord.AllowedMentions.none(), **kwargs)
        return await self._available(game)

    async def _wait_until(self, game, deadline):
        remaining = max(0, deadline - asyncio.get_running_loop().time())
        try:
            await asyncio.wait_for(game.event.wait(), timeout=remaining)
        except asyncio.TimeoutError:
            pass

    async def _draw_puzzles(self, guild, count):
        """Reserve puzzles from a saved server deck. Caller holds _data_lock."""
        bank = dict(WORDS)
        async with self.config.guild(guild).all() as settings:
            # Stable answer keys tolerate bank updates without stale list indices.
            raw_queue = settings.get("remaining_words", [])
            queue = []
            seen = set()
            if isinstance(raw_queue, list):
                for word in raw_queue:
                    if isinstance(word, str) and word in bank and word not in seen:
                        queue.append(word)
                        seen.add(word)
            chosen = []
            while len(chosen) < count:
                if not queue:
                    queue = list(bank)
                    random.shuffle(queue)
                    # A crossing spanning two decks still has no duplicates.
                    # Also prevent the last old word starting the next crossing.
                    deferred = set(chosen) or {settings.get("last_word", "")}
                    queue = ([word for word in queue if word not in deferred]
                             + [word for word in queue if word in deferred])
                take = min(count - len(chosen), len(queue))
                chosen.extend(queue[:take])
                del queue[:take]
            settings["remaining_words"] = queue
            settings["last_word"] = chosen[-1]
        return [(word, bank[word]) for word in chosen]

    async def _award(self, game):
        # Serializing this with privacy requests prevents deleted scores returning.
        async with self._data_lock:
            if not await self._available(game) or game.winner_id is None:
                return False
            user_id = game.winner_id
            async with self.config.guild(game.channel.guild).scores() as scores:
                row = scores.setdefault(str(user_id), {"points": 0, "solved": 0})
                row["points"] += game.award
                row["solved"] += 1
            game.points[user_id] += game.award
            game.solves[user_id] += 1
            game.hops += 1
            return True

    async def _run(self, game):
        try:
            for index, (word, clue) in enumerate(game.puzzles):
                if not await self._available(game):
                    return
                game.round_index = index
                game.answer = word
                game.winner_id = None
                game.event.clear()
                game.accepting = False
                golden = index == game.golden_round
                embed = discord.Embed(
                    title=f"🐸 Frog Pond • Lily pad {index + 1}/{len(game.puzzles)}",
                    description=(
                        f"**Unscramble: `{scramble(word)}`**\n{clue}\n\n"
                        f"Type the word in chat! You have **{game.seconds} seconds**.\n"
                        + ("✨ **Golden fly! Double points this round.**\n" if golden else "")
                        + f"Hops made: **{game.hops}** • Escape target: "
                        f"**{math.ceil(len(game.puzzles) * 0.6)}**"
                    ),
                    colour=COLOUR,
                )
                if not await self._send(game, embed=embed):
                    return
                start = asyncio.get_running_loop().time()
                game.deadline = start + game.seconds
                game.accepting = True
                for fraction in (0.5, 0.75, 1.0):
                    await self._wait_until(game, start + game.seconds * fraction)
                    if not await self._available(game):
                        return
                    if game.winner_id is not None or fraction == 1.0:
                        break
                    hint = (
                        f"Starts with **{word[0].upper()}** • **{len(word)} letters**"
                        if fraction == 0.5 else f"Vowels: `{vowel_hint(word)}`"
                    )
                    if not await self._send(game, content=f"🐸 Hint: {hint}"):
                        return
                game.accepting = False
                if game.winner_id is not None:
                    if not await self._award(game):
                        return
                    message = (
                        f"🐸 **Hop!** <@{game.winner_id}> solved **{word.upper()}** "
                        f"and earned **{game.award} points**."
                    )
                else:
                    message = f"💦 Splash! The word was **{word.upper()}**."
                if not await self._send(game, content=message):
                    return
                if index + 1 < len(game.puzzles):
                    await asyncio.sleep(2)
            target = math.ceil(len(game.puzzles) * 0.6)
            outcome = (
                "🏡 You got the frog home!" if game.hops >= target
                else "💦 The frog is staying in the pond. Try another crossing!"
            )
            rows = [
                f"**{rank}.** <@{user_id}> — **{points}** points"
                for rank, (user_id, points) in enumerate(game.points.most_common(10), 1)
            ]
            await self._send(game, embed=discord.Embed(
                title="🐸 Frog Pond • Crossing complete",
                description=f"{outcome}\n**{game.hops}/{len(game.puzzles)}** successful hops.\n\n"
                + ("\n".join(rows) or "No puzzles solved this time."),
                colour=COLOUR,
            ))
        except asyncio.CancelledError:
            pass
        except discord.HTTPException:
            LOG.warning("Frog Pond stopped: could not send to channel %s", game.channel.id)
        except Exception:
            LOG.exception("Frog Pond game failed")
        finally:
            self._cancel(game)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild is None or message.author.bot:
            return
        game = self.games.get(message.guild.id)
        if not game or message.channel.id != game.channel.id or not game.accepting:
            return
        # Exact single-word guesses only; unrelated conversation is untouched.
        if message.content.strip().casefold() != game.answer:
            return
        round_index = game.round_index
        if not await self._available(game):
            return
        if not await self.bot.ignored_channel_or_guild(message):
            return
        if not await self.bot.allowed_by_whitelist_blacklist(message.author):
            return
        now = asyncio.get_running_loop().time()
        # Recheck after awaits: a concurrent winner, stop or new round wins precedence.
        if (
            not self._active(game) or not game.accepting or game.winner_id is not None
            or round_index != game.round_index or now >= game.deadline
        ):
            return
        elapsed = game.seconds - (game.deadline - now)
        base = 3 if elapsed < game.seconds * 0.5 else (2 if elapsed < game.seconds * 0.75 else 1)
        game.award = base * (2 if game.round_index == game.golden_round else 1)
        game.winner_id = message.author.id
        game.accepting = False
        game.event.set()

    @commands.group(name="frog", invoke_without_command=True)
    @commands.guild_only()
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def frog(self, ctx):
        """Start Frog Pond, or use start, stop, rules, top, score and time."""
        await self._start(ctx, DEFAULT_ROUNDS)

    @frog.command(name="start")
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def frog_start(self, ctx, rounds: int = DEFAULT_ROUNDS):
        """Start a crossing with 10–20 puzzles (default 10). Anyone can guess."""
        await self._start(ctx, rounds)

    async def _start(self, ctx, rounds):
        if not MIN_ROUNDS <= rounds <= MAX_ROUNDS:
            await ctx.send("Choose between **10 and 20** lily pads.")
            return
        if not self.bot.intents.message_content:
            await ctx.send("Enable **Message Content Intent** and restart the bot to read guesses.")
            return
        if self._acro_active(ctx.channel):
            await ctx.send("Finish AcroGame in this channel before starting Frog Pond.")
            return
        async with self._data_lock:
            if await self.bot.cog_disabled_in_guild(self, ctx.guild):
                return
            existing = self.games.get(ctx.guild.id)
            if existing:
                await ctx.send(f"A frog is already crossing in <#{existing.channel.id}>.")
                return
            seconds = await self.config.guild(ctx.guild).seconds()
            puzzles = await self._draw_puzzles(ctx.guild, rounds)
            game = PondGame(
                channel=ctx.channel, starter_id=ctx.author.id,
                puzzles=puzzles, seconds=seconds,
                golden_round=random.randrange(rounds),
            )
            self.games[ctx.guild.id] = game
            game.task = asyncio.create_task(self._run(game))
            game.watcher = asyncio.create_task(self._watch(game))

    @frog.command(name="stop")
    async def frog_stop(self, ctx):
        """The starter, a moderator or the bot owner can stop a crossing."""
        game = self.games.get(ctx.guild.id)
        if not game:
            await ctx.send("No frog is crossing right now.")
            return
        permitted = (
            ctx.author.id == game.starter_id
            or ctx.author.guild_permissions.manage_guild
            or await self.bot.is_mod(ctx.author) or await self.bot.is_owner(ctx.author)
        )
        if not permitted:
            await ctx.send("Only the starter or a moderator can stop this crossing.")
            return
        tasks = self._cancel(game)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await ctx.send("🐸 Frog Pond stopped. Points already earned are kept.")

    @frog.command(name="rules")
    async def frog_rules(self, ctx):
        """Explain the game and scoring."""
        prefix = ctx.clean_prefix
        await ctx.send(
            "🐸 **Frog Pond**\nUnscramble the word using its clue and type it in chat. "
            "The first correct answer makes the frog hop and earns **3 points**. "
            "After the halfway hint: **2**; after the vowel hint: **1**. "
            "One **golden-fly** round doubles points. Solve at least **60%** of the "
            "puzzles together to get the frog home!\n"
            f"`{prefix}frog` starts 10 puzzles; `{prefix}frog start 20` starts 20.\n"
            "The server's question deck cycles only after every answer is drawn.\n"
            f"`{prefix}frog top` shows server scores. Anyone can join by guessing."
        )

    @frog.command(name="top", aliases=["leaderboard"])
    async def frog_top(self, ctx):
        """Show the server's top ten frogs by total points."""
        scores = await self.config.guild(ctx.guild).scores()
        top = sorted(scores.items(), key=lambda item: (-item[1]["points"], int(item[0])))[:10]
        rows = [
            f"**{rank}.** <@{user_id}> — **{row['points']}** points • {row['solved']} solved"
            for rank, (user_id, row) in enumerate(top, 1)
        ]
        await ctx.send(
            "🐸 **Frog Pond leaderboard**\n" + ("\n".join(rows) or "No scores yet. Start a crossing!"),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @frog.command(name="score")
    async def frog_score(self, ctx):
        """Show your own server points and solved-puzzle count."""
        scores = await self.config.guild(ctx.guild).scores()
        row = scores.get(str(ctx.author.id), {"points": 0, "solved": 0})
        await ctx.send(f"🐸 You have **{row['points']} points** from **{row['solved']} solved puzzles.")

    @frog.command(name="time")
    @commands.admin_or_permissions(manage_guild=True)
    async def frog_time(self, ctx, seconds: int):
        """Set the time per puzzle (10–60 seconds; default 25). Applies next game."""
        if not 10 <= seconds <= 60:
            await ctx.send("Choose between **10 and 60 seconds**.")
            return
        async with self._data_lock:
            await self.config.guild(ctx.guild).seconds.set(seconds)
        await ctx.send(f"🐸 Future crossings will allow **{seconds} seconds** per puzzle.")

    async def red_delete_data_for_user(self, *, requester, user_id):
        async with self._data_lock:
            tasks = []
            for game in list(self.games.values()):
                if user_id == game.starter_id or user_id == game.winner_id or user_id in game.points:
                    tasks.extend(self._cancel(game))
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            for guild_id in await self.config.all_guilds():
                async with self.config.guild_from_id(guild_id).scores() as scores:
                    scores.pop(str(user_id), None)

