"""Persistent, server-wide opt-in banned-word game for Red-DiscordBot 3.5+."""

import asyncio
import random
import re
import time
from typing import Dict, List, Optional

import discord
from redbot.core import Config, commands
from redbot.core.utils.chat_formatting import pagify

MAX_WORDS = 300
MAX_WORD_LENGTH = 48
# A random, common starter word makes each new game immediately playable.
# The uppercase "I" is stored as "i" for case-insensitive matching.
STARTER_WORDS = (
    "i", "it", "what", "me", "you", "we", "they", "us", "the", "a",
    "and", "but", "to", "in", "on", "at", "is", "are", "was",
    "that", "this", "not", "my", "your", "have", "do", "so",
)
# Up to three plain word tokens, including apostrophes and hyphens inside words.
WORD_FORMAT = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*(?:\s+[^\W_]+(?:['’\-][^\W_]+)*){0,2}", re.UNICODE)


def _normalise(word: str) -> str:
    return " ".join(word.strip().casefold().split())


def _safe(text: str) -> str:
    return discord.utils.escape_mentions(discord.utils.escape_markdown(text))


def _new_game(host_id: int) -> dict:
    return {
        "active": True,
        "host_id": host_id,
        "started_at": int(time.time()),
        "players": {},  # user_id -> {playing, joined_at, strikes}
        "words": {},  # normalised text -> {added_by, added_at}
        "total_strikes": 0,
        "announcements": True,
    }


class BannedWords(commands.Cog):
    """One non-expiring banned-word game per guild, across all server channels."""

    __author__ = "Will"
    __version__ = "1.1.0"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=817342960155, force_registration=True)
        self.config.register_guild(game={})
        self._locks: Dict[int, asyncio.Lock] = {}
        self._active_guilds = set()
        self._patterns: Dict[int, Optional[re.Pattern]] = {}

    def _lock(self, guild_id: int) -> asyncio.Lock:
        return self._locks.setdefault(guild_id, asyncio.Lock())

    def _set_pattern(self, guild_id: int, game: dict) -> None:
        words = game.get("words", {})
        if not words:
            self._patterns[guild_id] = None
            return
        # A single regex avoids up to MAX_WORDS separate scans per message.
        pieces = [re.escape(word).replace(r"\ ", r"\s+") for word in sorted(words, key=len, reverse=True)]
        self._patterns[guild_id] = re.compile(r"(?<!\w)(?:" + "|".join(pieces) + r")(?!\w)")

    async def cog_load(self) -> None:
        # An active game is restored after a bot restart or cog reload.
        for guild_id, config in (await self.config.all_guilds()).items():
            game = config.get("game") or {}
            if game.get("active"):
                self._active_guilds.add(int(guild_id))
                self._set_pattern(int(guild_id), game)

    async def _game(self, guild: discord.Guild) -> dict:
        return await self.config.guild(guild).game()

    async def _save(self, guild: discord.Guild, game: dict) -> None:
        await self.config.guild(guild).game.set(game)

    @staticmethod
    def _moderator(member: discord.Member) -> bool:
        return member.guild_permissions.manage_guild or member.guild_permissions.administrator

    @staticmethod
    def _active_player(game: dict, user_id: int) -> bool:
        return bool(game.get("players", {}).get(str(user_id), {}).get("playing"))

    @staticmethod
    def _name(guild: discord.Guild, user_id: int) -> str:
        member = guild.get_member(int(user_id))
        return _safe(member.display_name) if member else f"User {user_id}"

    @commands.group(name="bwg", aliases=["bannedword", "bannedwords"], invoke_without_command=True)
    @commands.guild_only()
    async def bwg(self, ctx: commands.Context):
        """Server-wide banned-word game. Use `~bwg help` for commands."""
        await ctx.send(
            "**Banned Word Game** — one game across the entire server.\n"
            f"`{ctx.clean_prefix}bwg start` (mod) · `{ctx.clean_prefix}bwg join` · "
            f"`{ctx.clean_prefix}bwg add <word>` · `{ctx.clean_prefix}bwg words`\n"
            f"`{ctx.clean_prefix}bwg status` · `{ctx.clean_prefix}bwg score` · "
            f"`{ctx.clean_prefix}bwg leave` · `{ctx.clean_prefix}bwg end` (host/mod)\n"
            "Only opted-in members are scored. No automatic time limit.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @bwg.command(name="help")
    async def bwg_help(self, ctx: commands.Context):
        """Show every game command."""
        p = ctx.clean_prefix
        await ctx.send(
            f"**Banned Word Game commands**\n"
            f"`{p}bwg start` — mod starts the server-wide game with one random common banned word\n"
            f"`{p}bwg join` — opt in to being monitored\n"
            f"`{p}bwg leave` — opt out; keep your accumulated strikes\n"
            f"`{p}bwg add <word>` — participating player adds a banned word (up to 3 words)\n"
            f"`{p}bwg remove <word>` — word author or mod removes it\n"
            f"`{p}bwg words` — list banned words\n"
            f"`{p}bwg score` — show scores, fewest strikes first\n"
            f"`{p}bwg status` — game state and participant totals\n"
            f"`{p}bwg announce on|off` — mod toggles strike announcements\n"
            f"`{p}bwg end` — host or mod ends the game and publishes final scores\n\n"
            "Words apply across all text channels and threads in this server, "
            "case-insensitively. One strike per offending message, even if it "
            "contains several banned words. Bot commands are excluded. "
            "The game stays active across restarts until explicitly ended.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @bwg.command(name="start")
    @commands.has_guild_permissions(manage_guild=True)
    async def start(self, ctx: commands.Context):
        """Start one persistent game for the entire server (mod only)."""
        async with self._lock(ctx.guild.id):
            game = await self._game(ctx.guild)
            if game.get("active"):
                await ctx.send("A server-wide Banned Word Game is already running. Use `bwg status`.")
                return
            game = _new_game(ctx.author.id)
            starter_word = random.choice(STARTER_WORDS)
            game["words"][starter_word] = {
                "added_by": 0,  # Starter word belongs to the game, not a player.
                "added_at": int(time.time()),
            }
            await self._save(ctx.guild, game)
            self._active_guilds.add(ctx.guild.id)
            self._set_pattern(ctx.guild.id, game)
        await ctx.send(
            f"**Banned Word Game has started for the entire server!**\n"
            f"**First banned word: {_safe(starter_word.upper() if starter_word == 'i' else starter_word)}** "
            "(randomly selected).\n"
            f"Join with `{ctx.clean_prefix}bwg join`. Once joined, add banned words with "
            f"`{ctx.clean_prefix}bwg add <word>`. Each message containing a banned word "
            "earns its author one strike, anywhere in the server. "
            "The game has no timer and ends only with the end command.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @bwg.command(name="join")
    async def join(self, ctx: commands.Context):
        """Opt into server-wide monitoring."""
        async with self._lock(ctx.guild.id):
            game = await self._game(ctx.guild)
            if not game.get("active"):
                await ctx.send(f"No game is running. A moderator can use `{ctx.clean_prefix}bwg start`.")
                return
            key = str(ctx.author.id)
            players = game.setdefault("players", {})
            player = players.get(key)
            if player and player.get("playing"):
                await ctx.send("You're already playing.")
                return
            if player:
                player["playing"] = True
            else:
                players[key] = {"playing": True, "joined_at": int(time.time()), "strikes": 0}
            await self._save(ctx.guild, game)
        await ctx.send(
            f"**{_safe(ctx.author.display_name)} joined!** Your messages are now checked "
            f"in every server channel. Add a word with `{ctx.clean_prefix}bwg add <word>`. "
            "Existing banned words apply immediately.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @bwg.command(name="leave")
    async def leave(self, ctx: commands.Context):
        """Opt out; retain existing strikes for the final leaderboard."""
        async with self._lock(ctx.guild.id):
            game = await self._game(ctx.guild)
            if not game.get("active") or not self._active_player(game, ctx.author.id):
                await ctx.send("You're not currently playing.")
                return
            game["players"][str(ctx.author.id)]["playing"] = False
            await self._save(ctx.guild, game)
        await ctx.send(
            "You've left the game. No new strikes will count against you; "
            "your existing score stays on the leaderboard."
        )

    @bwg.command(name="add")
    async def add(self, ctx: commands.Context, *, word: str):
        """Add a banned word or short phrase while opted in."""
        normalized = _normalise(word)
        if not 1 <= len(normalized) <= MAX_WORD_LENGTH or not WORD_FORMAT.fullmatch(normalized) or not any(c.isalpha() for c in normalized):
            await ctx.send("Use 1–48 characters, up to three ordinary words (letters/numbers, optional apostrophes or hyphens).")
            return
        async with self._lock(ctx.guild.id):
            game = await self._game(ctx.guild)
            if not game.get("active"):
                await ctx.send("There isn't an active game.")
                return
            if not self._active_player(game, ctx.author.id):
                await ctx.send(f"Join first with `{ctx.clean_prefix}bwg join`.")
                return
            words = game.setdefault("words", {})
            if normalized in words:
                await ctx.send(f"**{_safe(normalized)}** is already banned.", allowed_mentions=discord.AllowedMentions.none())
                return
            if len(words) >= MAX_WORDS:
                await ctx.send(f"This game has reached the {MAX_WORDS}-word limit.")
                return
            words[normalized] = {"added_by": ctx.author.id, "added_at": int(time.time())}
            await self._save(ctx.guild, game)
            self._set_pattern(ctx.guild.id, game)
        await ctx.send(
            f"**BANNED:** {_safe(normalized)} — added by {_safe(ctx.author.display_name)}. "
            "Now applies server-wide to all opted-in players.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @bwg.command(name="remove")
    async def remove(self, ctx: commands.Context, *, word: str):
        """Remove your own banned word, or any word as a moderator."""
        normalized = _normalise(word)
        async with self._lock(ctx.guild.id):
            game = await self._game(ctx.guild)
            if not game.get("active"):
                await ctx.send("There isn't an active game.")
                return
            entry = game.get("words", {}).get(normalized)
            if not entry:
                await ctx.send("That word isn't banned.")
                return
            if entry.get("added_by") != ctx.author.id and not self._moderator(ctx.author):
                await ctx.send("Only the player who added that word or a moderator can remove it.")
                return
            del game["words"][normalized]
            await self._save(ctx.guild, game)
            self._set_pattern(ctx.guild.id, game)
        await ctx.send(f"Removed **{_safe(normalized)}** from the server-wide banned words.", allowed_mentions=discord.AllowedMentions.none())

    @bwg.command(name="words", aliases=["list"])
    async def words(self, ctx: commands.Context):
        """View the complete server-wide banned word list."""
        game = await self._game(ctx.guild)
        if not game.get("active"):
            await ctx.send("There isn't an active game.")
            return
        words = sorted(game.get("words", {}))
        if not words:
            await ctx.send("No words have been banned yet.")
            return
        lines = [f"{i}. {_safe(word)}" for i, word in enumerate(words, 1)]
        for page in pagify("\n".join(lines), page_length=1750, delims=["\n"]):
            await ctx.send(f"**Banned words ({len(words)})**\n{page}", allowed_mentions=discord.AllowedMentions.none())

    def _scores(self, guild: discord.Guild, game: dict, max_rows: int = 20) -> str:
        players = game.get("players", {})
        if not players:
            return "No players joined."
        order = sorted(players.items(), key=lambda pair: (pair[1].get("strikes", 0), pair[1].get("joined_at", 0)))
        rows: List[str] = []
        for i, (uid, p) in enumerate(order[:max_rows], 1):
            status = "playing" if p.get("playing") else "left"
            rows.append(f"{i}. {self._name(guild, int(uid))}: **{p.get('strikes', 0)}** strike(s) ({status})")
        if len(order) > max_rows:
            rows.append(f"...and {len(order) - max_rows} more players")
        return "\n".join(rows)

    @bwg.command(name="score", aliases=["scores", "leaderboard"])
    async def score(self, ctx: commands.Context):
        """Display the scoreboard; the fewest strikes lead."""
        game = await self._game(ctx.guild)
        if not game.get("active"):
            await ctx.send("There isn't an active game.")
            return
        await ctx.send(
            "**Banned Word Game leaderboard — fewest strikes wins**\n" + self._scores(ctx.guild, game),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @bwg.command(name="status")
    async def status(self, ctx: commands.Context):
        """Show current server-wide game totals."""
        game = await self._game(ctx.guild)
        if not game.get("active"):
            await ctx.send(f"No active game. A moderator can use `{ctx.clean_prefix}bwg start`.")
            return
        players = game.get("players", {})
        participating = sum(1 for p in players.values() if p.get("playing"))
        await ctx.send(
            f"**Banned Word Game: ACTIVE (whole server)**\n"
            f"Players opted in: **{participating}** / {len(players)} ever joined\n"
            f"Banned words: **{len(game.get('words', {}))}**\n"
            f"Total strikes: **{game.get('total_strikes', 0)}**\n"
            f"Strike announcements: **{'on' if game.get('announcements', True) else 'off'}**\n"
            "No timer. Only an explicit end command stops the game."
        )

    @bwg.command(name="announce", aliases=["notifications"])
    @commands.has_guild_permissions(manage_guild=True)
    async def announce(self, ctx: commands.Context, mode: str):
        """Toggle strike notifications without pausing tracking (mod only)."""
        mode = mode.casefold()
        if mode not in ("on", "off"):
            await ctx.send("Usage: `bwg announce on` or `bwg announce off`.")
            return
        async with self._lock(ctx.guild.id):
            game = await self._game(ctx.guild)
            if not game.get("active"):
                await ctx.send("There isn't an active game.")
                return
            game["announcements"] = mode == "on"
            await self._save(ctx.guild, game)
        await ctx.send(f"Banned Word Game strike announcements are now **{mode}**.")

    @bwg.command(name="end", aliases=["stop", "finish"])
    async def end(self, ctx: commands.Context):
        """Explicitly finish the game (starter or server moderator only)."""
        async with self._lock(ctx.guild.id):
            game = await self._game(ctx.guild)
            if not game.get("active"):
                await ctx.send("There isn't an active game.")
                return
            if game.get("host_id") != ctx.author.id and not self._moderator(ctx.author):
                await ctx.send("Only the game starter or a moderator can end it.")
                return
            summary = (
                "**BANNED WORD GAME ENDED — FINAL SCORES**\n"
                + self._scores(ctx.guild, game)
                + f"\n\n**{len(game.get('words', {}))}** banned words · "
                + f"**{game.get('total_strikes', 0)}** total strikes"
            )
            await self._save(ctx.guild, {})
            self._active_guilds.discard(ctx.guild.id)
            self._patterns.pop(ctx.guild.id, None)
        await ctx.send(summary, allowed_mentions=discord.AllowedMentions.none())

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Track messages by opted-in members across every server text channel/thread."""
        if (
            message.guild is None
            or message.author.bot
            or message.webhook_id is not None
            or message.guild.id not in self._active_guilds
            or not message.content
        ):
            return
        # A disabled cog cannot silently continue scoring messages.
        if await self.bot.cog_disabled_in_guild(self, message.guild):
            return
        # OwnerLock protects this listener too, when this cog is locked.
        ownerlock = self.bot.get_cog("OwnerLock")
        if ownerlock is not None and not await ownerlock.allows_event(self.qualified_name, message.author):
            return
        # Commands themselves cannot trigger strikes, including `bwg add`.
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        async with self._lock(message.guild.id):
            if message.guild.id not in self._active_guilds:
                return
            game = await self._game(message.guild)
            if not game.get("active") or not self._active_player(game, message.author.id):
                return
            pattern = self._patterns.get(message.guild.id)
            if not pattern:
                self._set_pattern(message.guild.id, game)
                pattern = self._patterns.get(message.guild.id)
            if not pattern:
                return
            matches = {_normalise(match.group()) for match in pattern.finditer(message.content.casefold())}
            if not matches:
                return
            # One strike per message, no matter how many different matches it contains.
            player = game["players"][str(message.author.id)]
            player["strikes"] = int(player.get("strikes", 0)) + 1
            game["total_strikes"] = int(game.get("total_strikes", 0)) + 1
            await self._save(message.guild, game)
            count = player["strikes"]
            should_announce = game.get("announcements", True)
            show_matches = sorted(matches)[:4]
            more = len(matches) - len(show_matches)

        if should_announce and message.guild.id in self._active_guilds:
            violated = ", ".join(_safe(word) for word in show_matches)
            if more:
                violated += f" (+{more} more)"
            try:
                await message.channel.send(
                    f"**BANNED WORD!** {_safe(message.author.display_name)} said "
                    f"**{violated}**. Strike **#{count}**!",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except (discord.Forbidden, discord.HTTPException):
                # Scoring still works in channels where the bot cannot post.
                pass

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """Forget user participation and remove words contributed by that user."""
        for guild_id in (await self.config.all_guilds()):
            guild_id = int(guild_id)
            async with self._lock(guild_id):
                conf = self.config.guild_from_id(guild_id)
                game = await conf.game()
                if not game:
                    continue
                changed = bool(game.get("players", {}).pop(str(user_id), None))
                for word, meta in list(game.get("words", {}).items()):
                    if meta.get("added_by") == user_id:
                        del game["words"][word]
                        changed = True
                if game.get("host_id") == user_id:
                    game["host_id"] = 0
                    changed = True
                if changed:
                    await conf.game.set(game)
                    if game.get("active"):
                        self._set_pattern(guild_id, game)
