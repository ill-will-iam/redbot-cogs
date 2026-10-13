"""A chat-first acronym game for Red-DiscordBot 3.5+ / discord.py 2.x.

No modals or DMs: during the 30-second submission phase, ordinary messages
in the game channel are deleted before being validated and recorded.

NOTE: Discord message deletion is not instantaneous or a secrecy guarantee.
"""

import asyncio
import random
import re
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import discord
from redbot.core import Config, bank, commands, errors


SUBMISSION_SECONDS = 30
MAX_ANSWER_LENGTH = 150
MAX_LOG_SUPPRESSIONS = 10000
def random_acronym() -> str:
    """Generate 3–5 independent random uppercase letters for each new round."""
    return "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=random.randint(3, 5)))



@dataclass
class Round:
    guild_id: int
    channel_id: int
    acronym: str
    prefixes: Tuple[str, ...]
    phase: str = "submissions"
    # user ID -> original answer; inserting a replacement retains initial order.
    submissions: Dict[int, str] = field(default_factory=dict)
    # ballot number maps to (user ID, answer)
    entries: List[Tuple[int, str]] = field(default_factory=list)
    # voter user ID -> ballot number (1-based)
    votes: Dict[int, int] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    task: Optional[asyncio.Task] = None
    warned_about_deletion: bool = False


def answer_matches(answer: str, acronym: str) -> bool:
    """Match one word per letter (allow punctuation around/in words)."""
    words = re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)*", answer)
    return len(words) == len(acronym) and all(
        word[0].upper() == letter for word, letter in zip(words, acronym)
    )


def pretty(text: str) -> str:
    """Escape markdown and mentions to display player-supplied text safely."""
    return discord.utils.escape_mentions(discord.utils.escape_markdown(text))


class AcroGame(commands.Cog):
    """Timed acronym expansions. Type directly in chat; the bot deletes answers."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=839102457126, force_registration=True)
        self.config.register_guild(
            scores={}, winner_points=10, winner_credits=0, voting_seconds=30
        )
        # Ongoing entries and votes are NOT persisted across bot restarts.
        self.rounds: Dict[int, Round] = {}
        # IDs only: suppress delayed raw deletion events after a round finishes.
        # Bound memory usage; no message text is stored here.
        self.log_suppressed_messages = OrderedDict()

    async def cog_check(self, ctx):
        """All AcroGame commands operate in servers, not private messages."""
        return ctx.guild is not None

    def cog_unload(self):
        for game in list(self.rounds.values()):
            if game.task and not game.task.done():
                game.task.cancel()
        self.rounds.clear()

    def suppresses_message_log(self, guild_id: int, channel_id: int, message_id=None) -> bool:
        """AdminLog pauses message records in an active game channel."""
        game = self.rounds.get(guild_id)
        if game and game.channel_id == channel_id:
            return True
        return message_id in self.log_suppressed_messages

    async def _delete_game_message(self, message: discord.Message):
        """Mark before requesting deletion so even fast events are suppressed."""
        self.log_suppressed_messages[message.id] = None
        self.log_suppressed_messages.move_to_end(message.id)
        while len(self.log_suppressed_messages) > MAX_LOG_SUPPRESSIONS:
            self.log_suppressed_messages.popitem(last=False)
        try:
            await message.delete()
        except discord.NotFound:
            # Already deleted; a raw deletion event may still be in flight.
            raise
        except discord.HTTPException:
            self.log_suppressed_messages.pop(message.id, None)
            raise

    async def _delete_quietly(self, message: discord.Message):
        try:
            await self._delete_game_message(message)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            pass

    async def _short_message(self, channel, content: str, seconds: int = 6):
        try:
            await channel.send(
                content,
                delete_after=seconds,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            pass

    async def _send_multiline(self, channel, heading: str, lines: List[str]):
        """Safely fit arbitrarily many answers into Discord's message limit."""
        chunk = heading
        for line in lines:
            if len(chunk) + len(line) + 1 > 1900:
                await channel.send(chunk, allowed_mentions=discord.AllowedMentions.none())
                chunk = "**More entries:**"
            chunk += "\n" + line
        await channel.send(chunk, allowed_mentions=discord.AllowedMentions.none())

    @commands.group(name="acro", invoke_without_command=True)
    @commands.guild_only()
    async def acro(self, ctx):
        """Play the acronym game. See `[p]help acro` for subcommands."""
        await ctx.send(
            "**Acronym game** — `acro start [LETTERS]`, then type your answer "
            "and vote by sending an entry number in chat. "
            "`acro score [member]`, `acro top`, `acro status`. "
            "Admins: `acro stop`, `acro setpoints`, `acro setcoins`, `acro setvotetime`."
        )

    @acro.command(name="start")
    @commands.cooldown(1, 15, commands.BucketType.guild)
    async def acro_start(self, ctx, acronym: Optional[str] = None):
        """Start a round here. Optionally supply a 3–5-letter acronym."""
        if ctx.guild.id in self.rounds:
            await ctx.send("A round is already running in this server. Use `acro status`.")
            return

        if not self.bot.intents.message_content:
            await ctx.send(
                "I need the **Message Content** intent enabled to read chat submissions."
            )
            return

        perms = ctx.channel.permissions_for(ctx.me)
        if not (perms.view_channel and perms.send_messages and perms.manage_messages
                and perms.read_message_history):
            await ctx.send(
                "I need View Channel, Send Messages, Manage Messages, and "
                "Read Message History in this channel to run a round."
            )
            return

        if acronym is None:
            acronym = random_acronym()
        else:
            acronym = acronym.upper().strip()
            if not re.fullmatch(r"[A-Z]{3,5}", acronym):
                await ctx.send("Use 3 to 5 letters (A–Z), such as KZP.")
                return

        prefixes = tuple(await self.bot.get_valid_prefixes(ctx.guild))
        if self.bot.user:
            prefixes += (f"<@{self.bot.user.id}>", f"<@!{self.bot.user.id}>")
        game = Round(ctx.guild.id, ctx.channel.id, acronym, prefixes)
        self.rounds[ctx.guild.id] = game

        try:
            await ctx.send(
                f"**ACRONYM ROUND**\n\n"
                f"# {' · '.join(acronym)}\n\n"
                f"⏱️ **{SUBMISSION_SECONDS} seconds to answer**\n"
                f"Create a **{len(acronym)}-word phrase**, using the letters in order.\n\n"
                "**Type your answer below!**"
            )
        except discord.HTTPException:
            self.rounds.pop(ctx.guild.id, None)
            raise
        game.task = asyncio.create_task(self._round_timer(game))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Capture chat answers or bare-number votes and delete their messages."""
        if not message.guild or message.author.bot or message.webhook_id:
            return
        game = self.rounds.get(message.guild.id)
        if not game or game.channel_id != message.channel.id:
            return
        # Leave Red commands alone (including commands from other cogs).
        if not message.content or message.content.startswith(game.prefixes):
            return
        # Leave attachments/files alone, rather than destroying users' uploads.
        if message.attachments or message.stickers:
            return

        if game.phase == "voting":
            # Only bare numbers are votes; other chat is left untouched.
            vote_text = message.content.strip()
            if not re.fullmatch(r"[0-9]+", vote_text):
                return
            async with game.lock:
                if game.phase != "voting":
                    return
                # Do not reveal which entry a player selected. Record only when
                # the vote message has actually been deleted.
                try:
                    await self._delete_game_message(message)
                except discord.NotFound:
                    return
                except (discord.Forbidden, discord.HTTPException):
                    await self._short_message(
                        message.channel,
                        "I couldn't delete that vote; it wasn't recorded. "
                        "Please check my Manage Messages permission.",
                    )
                    return
                reply = self._record_vote(game, message.author.id, int(vote_text))
            await self._short_message(message.channel, reply, 4)
            return

        if game.phase != "submissions":
            return

        async with game.lock:
            if game.phase != "submissions":
                return
            # Capture before deleting so the answer survives deletion, but keep it
            # in memory only if deletion succeeds.
            answer = " ".join(message.content.split())
            try:
                await self._delete_game_message(message)
            except discord.NotFound:
                return
            except (discord.Forbidden, discord.HTTPException):
                if not game.warned_about_deletion:
                    game.warned_about_deletion = True
                    await self._short_message(
                        message.channel,
                        "I couldn't delete an entry. Please check my Manage Messages "
                        "permission; that entry was **not recorded**.",
                        seconds=15,
                    )
                return
            if not answer or len(answer) > MAX_ANSWER_LENGTH:
                await self._short_message(
                    message.channel,
                    f"Entry not saved. Keep it under {MAX_ANSWER_LENGTH} characters."
                )
                return
            if not answer_matches(answer, game.acronym):
                await self._short_message(
                    message.channel,
                    f"Entry not saved. Use **{' · '.join(game.acronym)}**: "
                    f"exactly {len(game.acronym)} words beginning with those letters."
                )
                return
            game.submissions[message.author.id] = answer

    async def _round_timer(self, game: Round):
        """Lifecycle: collect 30 seconds, display entries, vote, award."""
        try:
            await asyncio.sleep(SUBMISSION_SECONDS)
            channel = self.bot.get_channel(game.channel_id)
            guild = self.bot.get_guild(game.guild_id)
            if not channel or not guild:
                return

            async with game.lock:
                if game.phase != "submissions":
                    return
                game.phase = "preparing_vote"
                game.entries = list(game.submissions.items())
                random.shuffle(game.entries)  # order doesn't hint at submitter
                count = len(game.entries)

            if count < 2:
                await channel.send(
                    "**Round cancelled:** At least two different players must "
                    "submit valid answers. No points awarded."
                )
                return

            lines = [f"**{idx}.** {pretty(answer)}" for idx, (_, answer)
                     in enumerate(game.entries, start=1)]
            await self._send_multiline(
                channel,
                f"**Time!** Here are the anonymous answers for "
                f"**{' · '.join(game.acronym)}** ({count} entries):",
                lines,
            )
            vote_seconds = await self.config.guild(guild).voting_seconds()
            async with game.lock:
                if game.phase != "preparing_vote":
                    return
                game.phase = "voting"
            await channel.send(
                f"**VOTING — {vote_seconds} seconds**\n\n"
                "**Type the number of the submission to vote.** "
                "For example: `1`, `2`, `3`.\n"
                "**You cannot vote for yourself.**"
            )
            await asyncio.sleep(vote_seconds)
            async with game.lock:
                if game.phase != "voting":
                    return
                game.phase = "tallying"
                entries = list(game.entries)
                votes = dict(game.votes)
            await self._finish_round(guild, channel, entries, votes)

        except asyncio.CancelledError:
            return
        except discord.HTTPException:
            # If the game can't post the ballot, don't leave it stuck.
            pass
        finally:
            if self.rounds.get(game.guild_id) is game:
                self.rounds.pop(game.guild_id, None)

    async def _finish_round(self, guild, channel, entries, votes):
        counts = Counter(votes.values())
        if not counts:
            await channel.send("**Round over:** Nobody voted. No points awarded.")
            return
        max_votes = max(counts.values())
        leaders = [n for n in range(1, len(entries) + 1)
                   if counts[n] == max_votes]
        if len(leaders) != 1:
            numbers = ", ".join(str(i) for i in leaders)
            await channel.send(
                f"**Tie!** Entries {numbers} each received {max_votes} vote(s). "
                "No points or coins awarded."
            )
            return

        winning_number = leaders[0]
        winner_id, answer = entries[winning_number - 1]
        member = guild.get_member(winner_id)
        points = await self.config.guild(guild).winner_points()
        credits = await self.config.guild(guild).winner_credits()

        async with self.config.guild(guild).scores() as scores:
            key = str(winner_id)
            record = scores.setdefault(key, {"wins": 0, "points": 0})
            record["wins"] += 1
            record["points"] += points

        credit_note = ""
        if credits and member:
            try:
                credit_name = await bank.get_currency_name(guild)
                await bank.deposit_credits(member, credits)
                credit_note = f" and **{credits} {pretty(credit_name)}**"
            except (ValueError, TypeError, RuntimeError, errors.BalanceTooHigh):
                credit_note = " (bank credit payout could not be completed)"
        elif credits and not member:
            credit_note = " (winner left; bank credit payout skipped)"

        display_name = pretty(member.display_name) if member else f"User {winner_id}"
        await channel.send(
            f"**Winner: {display_name}!**\n"
            f"Entry **#{winning_number}**: {pretty(answer)}\n"
            f"**{max_votes} vote(s)** · **+{points} leaderboard points**"
            f"{credit_note}\n"
            f"Total votes: **{len(votes)}**. Play again with `acro start`."
        )

    @staticmethod
    def _record_vote(game: Round, voter_id: int, number: int) -> str:
        """Validate and record one vote. Call only with the game's lock held."""
        if number < 1 or number > len(game.entries):
            return "That entry number doesn't exist."
        author_id, _ = game.entries[number - 1]
        if voter_id == author_id:
            return "You can't vote for your own entry."
        game.votes[voter_id] = number
        return "Vote recorded (you can change it)."

    @acro.command(name="vote")
    async def acro_vote(self, ctx, number: int):
        """Legacy alternative to voting by typing the number in chat."""
        await self._delete_quietly(ctx.message)
        game = self.rounds.get(ctx.guild.id)
        if not game or game.channel_id != ctx.channel.id or game.phase != "voting":
            await self._short_message(ctx.channel, "No vote is open in this channel.")
            return
        async with game.lock:
            reply = (
                self._record_vote(game, ctx.author.id, number)
                if game.phase == "voting"
                else "Voting has already closed."
            )
        await self._short_message(ctx.channel, reply, 4)

    @acro.command(name="status")
    async def acro_status(self, ctx):
        """Check whether a round is collecting answers or votes."""
        game = self.rounds.get(ctx.guild.id)
        if not game:
            await ctx.send("No round is running. Start one with `acro start`.")
            return
        if game.phase == "submissions":
            await ctx.send(
                f"**{' · '.join(game.acronym)}**: accepting chat answers in "
                f"<#{game.channel_id}>. Valid participants: {len(game.submissions)}."
            )
        elif game.phase == "voting":
            await ctx.send(
                f"Voting in <#{game.channel_id}>. "
                f"Entries: {len(game.entries)}; votes cast: {len(game.votes)}."
            )
        else:
            await ctx.send("The round is transitioning or calculating results.")

    @acro.command(name="stop")
    @commands.admin_or_permissions(manage_guild=True)
    async def acro_stop(self, ctx):
        """Cancel the active round without awarding points (moderators)."""
        game = self.rounds.get(ctx.guild.id)
        if not game:
            await ctx.send("There is no active round to stop.")
            return
        async with game.lock:
            if game.phase == "tallying":
                await ctx.send("Results are already being finalized.")
                return
            game.phase = "stopped"
            self.rounds.pop(ctx.guild.id, None)
            if game.task:
                game.task.cancel()
        await ctx.send("Acronym round cancelled. No points awarded.")

    @acro.command(name="score")
    async def acro_score(self, ctx, member: Optional[discord.Member] = None):
        """Show leaderboard points and wins for a player."""
        member = member or ctx.author
        scores = await self.config.guild(ctx.guild).scores()
        record = scores.get(str(member.id), {})
        await ctx.send(
            f"**{pretty(member.display_name)}**: "
            f"{record.get('points', 0)} points, {record.get('wins', 0)} wins."
        )

    @acro.command(name="top", aliases=["leaderboard"])
    async def acro_top(self, ctx):
        """Show the top 10 players by earned game points."""
        scores = await self.config.guild(ctx.guild).scores()
        ranked = sorted(
            scores.items(),
            key=lambda kv: (kv[1].get("points", 0), kv[1].get("wins", 0)),
            reverse=True,
        )[:10]
        if not ranked:
            await ctx.send("No winners yet!")
            return
        lines = []
        for idx, (user_id, record) in enumerate(ranked, 1):
            member = ctx.guild.get_member(int(user_id))
            name = pretty(member.display_name) if member else f"User {user_id}"
            lines.append(
                f"**{idx}.** {name} — {record.get('points', 0)} pts "
                f"({record.get('wins', 0)} wins)"
            )
        await ctx.send("**Acronym Game Leaderboard**\n" + "\n".join(lines))

    @acro.command(name="setpoints")
    @commands.admin_or_permissions(manage_guild=True)
    async def acro_setpoints(self, ctx, amount: int):
        """Set leaderboard points given to a unique round winner (0–10000)."""
        if not 0 <= amount <= 10000:
            await ctx.send("Choose a number from 0 to 10000.")
            return
        await self.config.guild(ctx.guild).winner_points.set(amount)
        await ctx.send(f"Future round winners will earn {amount} leaderboard points.")

    @acro.command(name="setcoins")
    @commands.admin_or_permissions(manage_guild=True)
    async def acro_setcoins(self, ctx, amount: int):
        """Set optional Red bank credits given to each unique winner (0 = off)."""
        if not 0 <= amount <= 100000:
            await ctx.send("Choose a number from 0 to 100000.")
            return
        await self.config.guild(ctx.guild).winner_credits.set(amount)
        await ctx.send(
            f"Bank prize set to {amount} credits per winner "
            f"({'disabled' if amount == 0 else 'enabled'})."
        )

    @acro.command(name="setvotetime")
    @commands.admin_or_permissions(manage_guild=True)
    async def acro_setvotetime(self, ctx, seconds: int):
        """Set voting time in seconds (15–300). Entries are always 30 seconds."""
        if not 15 <= seconds <= 300:
            await ctx.send("Voting time must be 15–300 seconds.")
            return
        await self.config.guild(ctx.guild).voting_seconds.set(seconds)
        await ctx.send(f"Voting will stay open for {seconds} seconds per round.")

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """Remove saved leaderboard records if Red processes a data deletion."""
        for guild_id, record in (await self.config.all_guilds()).items():
            if str(user_id) in record.get("scores", {}):
                async with self.config.guild_from_id(guild_id).scores() as scores:
                    scores.pop(str(user_id), None)
        for game in self.rounds.values():
            async with game.lock:
                game.submissions.pop(user_id, None)
                game.votes.pop(user_id, None)
