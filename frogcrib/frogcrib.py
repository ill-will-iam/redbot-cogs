"""Frog-themed Discord cribbage, connected to Ribbit's Ribbucks economy."""
import asyncio
import logging
import random
from datetime import datetime, timezone
from dataclasses import dataclass, field
import time

import discord
from redbot.core import Config, commands

from .engine import CribbageGame, display

LOG = logging.getLogger('red.will.frogcrib')
INVITE_SECONDS = 300
DEFAULT_TIMEOUT = 1200


@dataclass
class Table:
    channel_id: int
    guild_id: int
    game: CribbageGame
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class FrogCrib(commands.Cog):
    """121-point cribbage with private hands and Royal Ribbit Reserve rewards."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=202610132201, force_registration=True)
        self.config.register_guild(win_reward=100, loss_reward=25, daily_reward_cap=3,
                                   turn_timeout=DEFAULT_TIMEOUT)
        self.config.register_member(wins=0, losses=0, games=0, ribbucks_earned=0,
                                    reward_day='', reward_count=0)
        self.tables = {}                 # (guild_id, channel_id) -> Table
        self.busy = {}                   # (guild_id, user_id) -> (guild_id, channel_id)
        self._lock = asyncio.Lock()
        self._stats_lock = asyncio.Lock()
        self._watch_task = None

    async def cog_load(self):
        self._watch_task = asyncio.create_task(self._watch())

    def cog_unload(self):
        if self._watch_task is not None:
            self._watch_task.cancel()
        self.tables.clear()
        self.busy.clear()

    async def red_delete_data_for_user(self, *, requester, user_id):
        for guild_id in await self.config.all_guilds():
            await self.config.member_from_ids(int(guild_id), int(user_id)).clear()
        async with self._lock:
            for table in list(self.tables.values()):
                if user_id in table.game.players:
                    self._remove(table)

    @staticmethod
    def _key(ctx):
        return (ctx.guild.id, ctx.channel.id)

    def _remove(self, table):
        key = (table.guild_id, table.channel_id)
        if self.tables.get(key) is table:
            del self.tables[key]
        for member_id in table.game.players:
            if self.busy.get((table.guild_id, member_id)) == key:
                self.busy.pop((table.guild_id, member_id), None)

    async def _watch(self):
        try:
            while True:
                await asyncio.sleep(30)
                now = time.monotonic()
                for table in list(self.tables.values()):
                    timeout = (INVITE_SECONDS if table.game.phase == 'invited'
                               else await self.config.guild_from_id(table.guild_id).turn_timeout())
                    if now - table.game.updated_at < timeout:
                        continue
                    async with table.lock:
                        if self.tables.get((table.guild_id, table.channel_id)) is not table:
                            continue
                        if time.monotonic() - table.game.updated_at < timeout:
                            continue
                        async with self._lock:
                            self._remove(table)
                        channel = self.bot.get_channel(table.channel_id)
                        if channel:
                            try:
                                await channel.send('**Frog Cribbage:** table closed after inactivity. '
                                                   'No Ribbucks were awarded.')
                            except (discord.Forbidden, discord.HTTPException):
                                pass
        except asyncio.CancelledError:
            return
        except Exception:
            LOG.exception('Cribbage table timeout watcher stopped unexpectedly')

    async def _get_table(self, ctx):
        table = self.tables.get(self._key(ctx))
        if table is None:
            await ctx.send('No cribbage table here. Start one with `$crib challenge @member`.')
            return None
        if ctx.author.id not in table.game.players:
            await ctx.send('You are not playing at this table.')
            return None
        return table

    @staticmethod
    def _index(table, member):
        return table.game.players.index(member.id)

    async def _send_hand(self, table, player):
        game = table.game
        member = self.bot.get_guild(table.guild_id).get_member(game.players[player])
        if member is None:
            return
        cards = game.hands[player]
        listing = ' '.join(f'`{idx}` {display(card)}' for idx, card in enumerate(cards, 1))
        if game.phase == 'discard':
            instruction = ('Your crib cards are locked. Waiting for your opponent to discard.'
                           if game.kept[player] else
                           'Choose 2 to place in the crib: `$crib discard 1 4` **in the game channel**.')
        elif game.phase == 'pegging':
            instruction = ('Your turn: `$crib play <number>` in the game channel.'
                           if game.turn == player else 'Your opponent is playing.')
        else:
            instruction = ''
        await member.send(f'**Frog Cribbage — Deal {game.round_number}**\n'
                          f'Your cards: {listing or "(none remaining)"}\n'
                          f'{instruction}\nGame channel: <#{table.channel_id}>')

    async def _broadcast_hands(self, table, players=None):
        if table.game.phase not in ('discard', 'pegging'):
            return
        for idx in ((0, 1) if players is None else players):
            # Cards are sent only to their owners. Do not reveal private hands publicly.
            try:
                await self._send_hand(table, idx)
            except (discord.Forbidden, discord.HTTPException):
                channel = self.bot.get_channel(table.channel_id)
                if channel:
                    await channel.send(f'<@{table.game.players[idx]}>: your DMs are blocked. '
                                       'Enable DMs to see your hand (the game may be forfeited on timeout).')

    async def _settle(self, guild, game):
        """Update stats once, then request optional capped bank payouts through Ribbit."""
        winner = game.winner
        if winner not in (0, 1):
            return []
        other = 1 - winner
        rewards = await self.config.guild(guild).all()
        ribbit = self.bot.get_cog('Ribbit')
        today = datetime.now(timezone.utc).date().isoformat()
        lines = []
        async with self._stats_lock:
            for idx in (winner, other):
                member = guild.get_member(game.players[idx])
                if member is None:
                    continue
                conf = self.config.member(member)
                data = await conf.all()
                data['games'] += 1
                data['wins' if idx == winner else 'losses'] += 1
                award = rewards['win_reward'] if idx == winner else rewards['loss_reward']
                if data['reward_day'] != today:
                    data['reward_day'] = today
                    data['reward_count'] = 0
                eligible = (award > 0 and data['reward_count'] < rewards['daily_reward_cap'])
                deposited = False
                if eligible and ribbit is not None:
                    try:
                        deposited = await ribbit.award_for_game(member, award, 'cribbage')
                    except Exception:
                        LOG.exception('Ribbit payout failed for cribbage match')
                if deposited:
                    data['reward_count'] += 1
                    data['ribbucks_earned'] += award
                    lines.append(f'<@{member.id}> earned **{award} Ribbucks**!')
                elif eligible:
                    lines.append(f'<@{member.id}>: no payout (Reserve closed, wallet full, or bank unavailable).')
                else:
                    lines.append(f'<@{member.id}>: daily cribbage rewards exhausted or disabled.')
                await conf.set(data)
        return lines

    async def _apply(self, ctx, table, action, *args):
        async with table.lock:
            if self.tables.get(self._key(ctx)) is not table:
                await ctx.send('That table is no longer active.')
                return
            idx = self._index(table, ctx.author)
            try:
                events = getattr(table.game, action)(idx, *args)
            except ValueError as error:
                await ctx.send(str(error))
                return
            finished = table.game.phase == 'finished'
            for event in events:
                await ctx.send(event, allowed_mentions=discord.AllowedMentions.none())
            await ctx.send(table.game.board(), allowed_mentions=discord.AllowedMentions.none())
            if finished:
                lines = await self._settle(ctx.guild, table.game)
                if lines:
                    await ctx.send('\n'.join(lines), allowed_mentions=discord.AllowedMentions.none())
                async with self._lock:
                    self._remove(table)
            else:
                if table.game.phase == 'pegging':
                    recipients = (0, 1) if action == 'discard' else (table.game.turn,)
                elif action == 'discard' and table.game.kept[idx]:
                    recipients = (idx,)
                else:
                    recipients = (0, 1)
                await self._broadcast_hands(table, recipients)

    @commands.guild_only()
    @commands.group(name='crib', aliases=['cribbage'], invoke_without_command=True)
    async def crib(self, ctx):
        """Play two-player cribbage for Ribbucks in the Frogonomics pond."""
        await ctx.send('**Frog Cribbage — first to 121!**\n'
                       '`$crib challenge @member` / `$crib accept` / `$crib decline`\n'
                       '`$crib hand` (DM), `$crib discard 1 4`, `$crib play 2`, `$crib go`\n'
                       '`$crib board`, `$crib quit`, `$crib stats [@member]`, `$crib top`\n'
                       '`$crib rules` | Admin: `$crib config`\n'
                       'No entry fees or betting. Paid games are capped daily.')

    @crib.command(name='rules')
    async def rules(self, ctx):
        await ctx.send('**Cribbage, the frog way:** Two players race to **121**. Dealer gets the '
                       'crib and alternates each deal. Each frog gets 6 cards, secretly discards '
                       '2 to the dealer crib, then the starter is cut. A starter Jack awards '
                       'dealer 2. Non-dealer pegs first: play cards without exceeding **31**. '
                       '**15 = 2**, **31 = 2**, consecutive pairs = **2/6/12**, runs = their '
                       'length, last/go = **1**. After all 8 cards are pegged, score the '
                       'non-dealer hand, dealer hand, then dealer crib for fifteens, pairs, '
                       'runs, flushes and nobs; first to 121 wins immediately. '
                       'Four-card hand flush = 4, 5 with starter; crib flush requires all 5. '
                       'Card numbers are in your DMs. No wagers; configurable Ribbuck prizes.')

    @crib.command(name='challenge', aliases=['start'])
    async def challenge(self, ctx, opponent: discord.Member):
        if opponent.bot or opponent.id == ctx.author.id:
            await ctx.send('Challenge another real frog, not yourself or a bot.')
            return
        key = self._key(ctx)
        async with self._lock:
            if key in self.tables:
                await ctx.send('This channel already has a cribbage table.')
                return
            if any((ctx.guild.id, uid) in self.busy for uid in (ctx.author.id, opponent.id)):
                await ctx.send('One of those frogs is already in a cribbage game or invitation.')
                return
            game = CribbageGame(players=(ctx.author.id, opponent.id), dealer=random.SystemRandom().randrange(2))
            table = Table(ctx.channel.id, ctx.guild.id, game)
            self.tables[key] = table
            self.busy[(ctx.guild.id, ctx.author.id)] = key
            self.busy[(ctx.guild.id, opponent.id)] = key
        await ctx.send(f'<@{opponent.id}>, <@{ctx.author.id}> challenges you to '
                       '**Frog Cribbage!** Reply `$crib accept` within 5 minutes or '
                       '`$crib decline`. Enable DMs for private card hands.',
                       allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))

    @crib.command(name='accept')
    async def accept(self, ctx):
        table = await self._get_table(ctx)
        if not table:
            return
        async with table.lock:
            game = table.game
            if game.phase != 'invited' or ctx.author.id != game.players[1]:
                await ctx.send('Only the challenged frog can accept this invitation.')
                return
            # Fail closed if either player cannot receive private cards.
            try:
                for uid in game.players:
                    member = ctx.guild.get_member(uid)
                    if member is None:
                        raise RuntimeError('Player left')
                    await member.send('**Frog Cribbage:** Your private card channel is ready.')
            except (discord.Forbidden, discord.HTTPException, RuntimeError):
                async with self._lock:
                    self._remove(table)
                await ctx.send('Both players must enable DMs from the server to play. '
                               'Invitation cancelled; no Ribbucks were charged.')
                return
            events = game.begin()
            for event in events:
                await ctx.send(event, allowed_mentions=discord.AllowedMentions.none())
            await self._broadcast_hands(table)

    @crib.command(name='decline')
    async def decline(self, ctx):
        table = await self._get_table(ctx)
        if not table:
            return
        async with table.lock:
            if table.game.phase != 'invited':
                await ctx.send('The game has started. Use `$crib quit` to abandon it.')
                return
            async with self._lock:
                self._remove(table)
            await ctx.send('The invitation was declined/cancelled.')

    @crib.command(name='hand', aliases=['cards'])
    async def hand(self, ctx):
        table = await self._get_table(ctx)
        if not table:
            return
        async with table.lock:
            if table.game.phase not in ('discard', 'pegging'):
                await ctx.send('No dealt cards yet.')
                return
            try:
                await self._send_hand(table, self._index(table, ctx.author))
                await ctx.send('Your cards were sent privately.')
            except (discord.Forbidden, discord.HTTPException):
                await ctx.send('I cannot DM you. Enable server DMs and try `$crib hand` again.')

    @crib.command(name='discard')
    async def discard(self, ctx, first: int, second: int):
        table = await self._get_table(ctx)
        if table:
            await self._apply(ctx, table, 'discard', first, second)

    @crib.command(name='play')
    async def play(self, ctx, number: int):
        table = await self._get_table(ctx)
        if table:
            await self._apply(ctx, table, 'play', number)

    @crib.command(name='go')
    async def go(self, ctx):
        table = await self._get_table(ctx)
        if table:
            await self._apply(ctx, table, 'go')

    @crib.command(name='board', aliases=['score'])
    async def board(self, ctx):
        table = await self._get_table(ctx)
        if table:
            await ctx.send(table.game.board(), allowed_mentions=discord.AllowedMentions.none())

    @crib.command(name='quit', aliases=['resign', 'forfeit'])
    async def quit(self, ctx):
        table = await self._get_table(ctx)
        if table:
            async with table.lock:
                async with self._lock:
                    self._remove(table)
                await ctx.send(f'<@{ctx.author.id}> left the table. '
                               'Game cancelled; no wins, wagers, or Ribbucks awarded.',
                               allowed_mentions=discord.AllowedMentions.none())

    @crib.command(name='stats')
    async def stats(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        data = await self.config.member(member).all()
        await ctx.send(f'**Frog Cribbage — {discord.utils.escape_markdown(member.display_name)}**\n'
                       f'Games: **{data["games"]}** | Wins: **{data["wins"]}** | '
                       f'Losses: **{data["losses"]}** | Earned: '
                       f'**{data["ribbucks_earned"]:,} Ribbucks**')

    @crib.command(name='top', aliases=['leaderboard'])
    async def top(self, ctx):
        data = await self.config.all_members(ctx.guild)
        entries = sorted(((uid, raw['wins']) for uid, raw in data.items()
                          if raw.get('wins', 0) and ctx.guild.get_member(int(uid))),
                         key=lambda x: (-x[1], x[0]))[:10]
        if not entries:
            await ctx.send('No victories on the lily-pad board yet.')
            return
        lines = [f'{pos}. {discord.utils.escape_markdown(ctx.guild.get_member(int(uid)).display_name)} — '
                 f'{wins} win(s)' for pos, (uid, wins) in enumerate(entries, 1)]
        await ctx.send('**Frog Cribbage Leaders**\n' + '\n'.join(lines))

    @crib.group(name='config', invoke_without_command=True)
    @commands.admin_or_permissions(administrator=True)
    async def config_group(self, ctx):
        data = await self.config.guild(ctx.guild).all()
        await ctx.send('**Frog Cribbage settings**\n'
                       f'Winner: **{data["win_reward"]} Ribbucks** | '
                       f'Other player: **{data["loss_reward"]} Ribbucks**\n'
                       f'Paid games per player per UTC day: **{data["daily_reward_cap"]}**\n'
                       f'Game inactivity timeout: **{data["turn_timeout"] // 60} minutes**\n'
                       'Admin: `$crib config rewards <winner> <other>`, '
                       '`$crib config cap <count>`, `$crib config timeout <minutes>`.')

    @config_group.command(name='rewards')
    async def config_rewards(self, ctx, winner: int, other: int):
        if not (0 <= other <= winner <= 1000):
            await ctx.send('Rewards must satisfy 0 ≤ other ≤ winner ≤ 1,000 Ribbucks.')
            return
        await self.config.guild(ctx.guild).win_reward.set(winner)
        await self.config.guild(ctx.guild).loss_reward.set(other)
        await ctx.send(f'Cribbage payouts set to **{winner} / {other} Ribbucks**.')

    @config_group.command(name='cap')
    async def config_cap(self, ctx, count: int):
        if not 0 <= count <= 20:
            await ctx.send('Choose 0–20 paid matches per player per UTC day.')
            return
        await self.config.guild(ctx.guild).daily_reward_cap.set(count)
        await ctx.send(f'Daily cribbage reward cap set to **{count}**.')

    @config_group.command(name='timeout')
    async def config_timeout(self, ctx, minutes: int):
        if not 5 <= minutes <= 120:
            await ctx.send('Timeout must be between 5 and 120 minutes.')
            return
        await self.config.guild(ctx.guild).turn_timeout.set(minutes * 60)
        await ctx.send(f'Cribbage inactivity timeout set to **{minutes} minutes**.')
