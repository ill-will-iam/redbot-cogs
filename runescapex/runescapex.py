"""Detailed public RuneScape data for Red-DiscordBot 3.5+."""
import asyncio
import time
from collections import OrderedDict
from datetime import datetime, timezone
from urllib.parse import quote

import aiohttp
import discord
from redbot.core import Config, commands

from .engine import (
    age, boss_entries, clue_entries, format_number, match_items, maxed_count,
    osrs_combat, parse_osrs, parse_rs3, percent_change, validate_name,
    virtual_level, xp_until_next,
)

OSRS_HISCORES = 'https://secure.runescape.com/m=hiscore_oldschool/index_lite.json'
RS3_HISCORES = 'https://secure.runescape.com/m=hiscore/index_lite.ws'
GE_API = 'https://prices.runescape.wiki/api/v1/osrs'
UA = 'Fatboy-RunescapeX/1.0 (+https://github.com/ill-will-iam/redbot-cogs)'


class APIError(Exception):
    pass


class RuneScapeX(commands.Cog):
    """Extended OSRS and RuneScape 3 stats, bosses, clues and Grand Exchange."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9408131294, force_registration=True)
        self.config.register_global(snapshots={})
        self._cache = OrderedDict()
        self._session = None
        self._lock = asyncio.Lock()

    async def cog_load(self):
        self._session = aiohttp.ClientSession(
            headers={'User-Agent': UA, 'Accept': 'application/json, text/plain'},
            timeout=aiohttp.ClientTimeout(total=12),
        )

    def cog_unload(self):
        if self._session is not None and not self._session.closed:
            asyncio.create_task(self._session.close())

    async def _fetch(self, url, params=None, ttl=90, json=True):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={'User-Agent': UA, 'Accept': 'application/json, text/plain'},
                timeout=aiohttp.ClientTimeout(total=12),
            )
        cache_key = (url, tuple(sorted((params or {}).items())))
        now = time.monotonic()
        cached = self._cache.get(cache_key)
        if cached and cached[0] > now:
            self._cache.move_to_end(cache_key)
            return cached[1]
        try:
            async with self._session.get(url, params=params) as response:
                if response.status in (400, 404):
                    raise APIError('No public hiscores record or item data was found.')
                if response.status in (403, 429):
                    raise APIError('The data service is rate-limiting requests. Try again shortly.')
                if response.status >= 400:
                    raise APIError(f'The data service returned HTTP {response.status}.')
                try:
                    value = await (response.json(content_type=None) if json else response.text())
                except (ValueError, UnicodeDecodeError) as exc:
                    raise APIError('The data service returned an unreadable response.') from exc
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise APIError('The RuneScape data service could not be reached.') from exc
        self._cache[cache_key] = (now + ttl, value)
        self._cache.move_to_end(cache_key)
        while len(self._cache) > 180:
            self._cache.popitem(last=False)
        return value

    async def _stats(self, game, player):
        game = game.casefold()
        if game not in ('osrs', 'rs3'):
            raise APIError('Choose `osrs` or `rs3`.')
        if not validate_name(player):
            raise APIError('Player names must have 1–12 characters: letters, numbers, spaces, `_` or `-`.')
        url = OSRS_HISCORES if game == 'osrs' else RS3_HISCORES
        raw = await self._fetch(url, {'player': player.strip()}, json=(game == 'osrs'))
        try:
            return parse_osrs(raw) if game == 'osrs' else parse_rs3(raw)
        except (ValueError, TypeError) as exc:
            raise APIError('The hiscores format changed or the returned record was incomplete.') from exc

    @staticmethod
    def _source(game, player):
        component = 'hiscore_oldschool' if game == 'osrs' else 'hiscore'
        return f'https://secure.runescape.com/m={component}/hiscorepersonal?user1={quote(player)}'

    async def _send(self, ctx, embed):
        if ctx.channel.permissions_for(ctx.me).embed_links:
            await ctx.send(embed=embed)
        else:
            lines = [f'**{embed.title}**', embed.description or '']
            for f in embed.fields:
                lines.append(f'**{f.name}:** {f.value}')
            await ctx.send('\n'.join(lines)[:1950])

    def _embed(self, ctx, title, description=None, url=None):
        emb = discord.Embed(title=title[:256], description=description, url=url,
                            color=discord.Color.dark_green(), timestamp=datetime.now(timezone.utc))
        emb.set_footer(text='Public Jagex hiscores / OSRS Wiki real-time prices • Data can lag')
        return emb

    async def _error(self, ctx, exc):
        await ctx.send(f'RuneScapeX: {exc}')

    @commands.group(name='rsx', invoke_without_command=True)
    @commands.cooldown(4, 20, commands.BucketType.user)
    async def rsx(self, ctx):
        """Detailed RuneScape commands. Use `rsx help` to list them."""
        await ctx.send('Run `$rsx help` for RuneScapeX commands and examples.')

    @rsx.command(name='help')
    async def rsx_help(self, ctx):
        """List available commands."""
        emb = self._embed(ctx, 'RuneScapeX • commands',
            'Use your normal `$` prefix (or whichever prefix your bot uses).')
        commands_text = [
            ('Profiles', '`$rsx osrs <player>` / `$rsx rs3 <player>`'),
            ('All skills', '`$rsx skills <osrs|rs3> <player>`'),
            ('Skill breakdown', '`$rsx skill <osrs|rs3> <skill> <player>`'),
            ('PvM boss KC', '`$rsx bosses <osrs player>`'),
            ('Clue completions', '`$rsx clues <osrs player>`'),
            ('Compare players', '`$rsx compare <osrs|rs3> <player one> | <player two>`'),
            ('Track gains', '`$rsx gains <osrs|rs3> <player>` (first run saves baseline)'),
            ('OSRS item', '`$rsx price <item name>`'),
            ('Find item', '`$rsx items <partial item name>`'),
        ]
        for title, value in commands_text:
            emb.add_field(name=title, value=value, inline=False)
        await self._send(ctx, emb)

    async def _profile(self, ctx, game, player):
        data = await self._stats(game, player)
        skills, activities = data['skills'], data['activities']
        overall = skills['Overall']
        total_skills = len(skills) - 1
        emb = self._embed(ctx, f'{player} • {game.upper()} player profile',
                          url=self._source(game, player))
        emb.add_field(name='Overall rank', value=format_number(overall['rank']))
        emb.add_field(name='Total level', value=format_number(overall['level']))
        emb.add_field(name='Total XP', value=format_number(overall['xp']))
        emb.add_field(name='99s / skills', value=f'{maxed_count(skills)} / {total_skills}')
        if game == 'osrs':
            combat = osrs_combat(skills)
            emb.add_field(name='Combat level (calculated)', value=str(combat) if combat is not None else '—')
            emb.add_field(name='Boss records', value=str(len(boss_entries(activities))))
            emb.add_field(name='Clue records', value=str(len(clue_entries(activities))))
        top = sorted(((name, val) for name, val in skills.items() if name != 'Overall'),
                     key=lambda it: (-it[1]['level'], -it[1]['xp'], it[0]))[:8]
        emb.add_field(name='Highest skills',
            value='\n'.join(f'**{name}** {format_number(v["level"])} • {format_number(v["xp"])} XP' for name,v in top),
            inline=False)
        await self._send(ctx, emb)

    @rsx.command(name='osrs')
    async def rsx_osrs(self, ctx, *, player: str):
        """Show an OSRS profile."""
        try:
            await self._profile(ctx, 'osrs', player)
        except APIError as exc:
            await self._error(ctx, exc)

    @rsx.command(name='rs3')
    async def rsx_rs3(self, ctx, *, player: str):
        """Show a RuneScape 3 profile."""
        try:
            await self._profile(ctx, 'rs3', player)
        except APIError as exc:
            await self._error(ctx, exc)

    @rsx.command(name='skills')
    async def rsx_skills(self, ctx, game: str, *, player: str):
        """All skill levels, ranks and XP, in pages."""
        try:
            data = await self._stats(game, player)
            rows = [(name, item) for name, item in data['skills'].items() if name != 'Overall']
            for start in range(0, len(rows), 12):
                emb = self._embed(ctx, f'{player} • {game.upper()} skills',
                                  f'Page {start//12+1}/{(len(rows)+11)//12}',
                                  self._source(game, player))
                for name, value in rows[start:start+12]:
                    emb.add_field(name=name, value=(f'Lvl **{format_number(value["level"])}** • '
                                      f'{format_number(value["xp"])} XP\nRank {format_number(value["rank"])}'), inline=True)
                await self._send(ctx, emb)
        except APIError as exc:
            await self._error(ctx, exc)

    @rsx.command(name='skill')
    async def rsx_skill(self, ctx, game: str, skill: str, *, player: str):
        """Detailed skill with XP remaining to level up and virtual level."""
        try:
            data = await self._stats(game, player)
            item = next(((n, v) for n,v in data['skills'].items() if n.casefold() == skill.casefold()), None)
            if item is None:
                raise APIError('Unknown skill; run `$rsx skills <game> <player>` for valid names.')
            name, stat = item
            emb = self._embed(ctx, f'{player} • {name} ({game.upper()})', url=self._source(game, player))
            emb.add_field(name='Level', value=format_number(stat['level']))
            emb.add_field(name='Experience', value=format_number(stat['xp']))
            emb.add_field(name='Global rank', value=format_number(stat['rank']))
            if name != 'Overall':
                max_level = 120 if game == 'rs3' else 99
                if name == 'Invention' and game == 'rs3':
                    max_level = 120  # Invention's XP curve differs; no generic XP-to-next.
                else:
                    remaining = xp_until_next(stat['xp'], stat['level'], max_level)
                    if remaining is not None:
                        emb.add_field(name='XP to next level', value=format_number(remaining))
                emb.add_field(name='Virtual level (standard XP curve)',
                    value=str(virtual_level(stat['xp'])) if name != 'Invention' else 'Special curve')
            await self._send(ctx, emb)
        except APIError as exc:
            await self._error(ctx, exc)

    @rsx.command(name='bosses')
    async def rsx_bosses(self, ctx, *, player: str):
        """OSRS boss kill counts returned by public hiscores."""
        try:
            data = await self._stats('osrs', player)
            rows = boss_entries(data['activities'])
            if not rows:
                raise APIError('No ranked boss/activity records were available for that player.')
            for start in range(0, len(rows), 18):
                emb = self._embed(ctx, f'{player} • OSRS PvM records',
                    f'{len(rows)} ranked boss/encounter records • page {start//18+1}/{(len(rows)+17)//18}')
                for name, row in rows[start:start+18]:
                    emb.add_field(name=name, value=f'KC/Score **{format_number(row["score"])}**\nRank {format_number(row["rank"])}')
                await self._send(ctx, emb)
        except APIError as exc:
            await self._error(ctx, exc)

    @rsx.command(name='clues')
    async def rsx_clues(self, ctx, *, player: str):
        """OSRS clue scroll hiscores by category."""
        try:
            rows = clue_entries((await self._stats('osrs', player))['activities'])
            if not rows:
                raise APIError('No ranked clue scroll records were available for that player.')
            emb = self._embed(ctx, f'{player} • OSRS clue scrolls')
            for name,row in rows[:24]:
                emb.add_field(name=name, value=f'{format_number(row["score"])} completed\nRank {format_number(row["rank"])}')
            await self._send(ctx, emb)
        except APIError as exc:
            await self._error(ctx, exc)

    @rsx.command(name='compare')
    async def rsx_compare(self, ctx, game: str, *, players: str):
        """Compare two players: $rsx compare osrs Zezima | Lynx Titan"""
        if '|' not in players:
            await ctx.send('Use `$rsx compare osrs Player One | Player Two` (or `rs3`).')
            return
        first, second = (p.strip() for p in players.split('|', 1))
        try:
            a, b = await asyncio.gather(self._stats(game, first), self._stats(game, second))
            ea, eb = a['skills']['Overall'], b['skills']['Overall']
            emb = self._embed(ctx, f'{first} vs {second} • {game.upper()}')
            emb.add_field(name='Total level', value=f'{first}: **{format_number(ea["level"])}**\n{second}: **{format_number(eb["level"])}**', inline=False)
            emb.add_field(name='Total XP', value=f'{first}: **{format_number(ea["xp"])}**\n{second}: **{format_number(eb["xp"])}**', inline=False)
            emb.add_field(name='Overall rank', value=f'{first}: {format_number(ea["rank"])}\n{second}: {format_number(eb["rank"])}', inline=False)
            shared = [(skill, value, b['skills'][skill]) for skill,value in a['skills'].items()
                      if skill != 'Overall' and skill in b['skills']]
            differences = sorted(shared, key=lambda row: abs(row[1]['xp'] - row[2]['xp']), reverse=True)
            emb.add_field(name='Largest XP gaps',
                value='\n'.join(f'{name}: {first} {format_number(x["level"])} / {second} {format_number(y["level"])}'
                        for name,x,y in differences[:10]), inline=False)
            await self._send(ctx, emb)
        except APIError as exc:
            await self._error(ctx, exc)

    @rsx.command(name='gains')
    async def rsx_gains(self, ctx, game: str, *, player: str):
        """Track hiscores XP/levels and (for OSRS) boss KC since last scan."""
        try:
            data = await self._stats(game, player)
            key = f'{game.casefold()}:{player.casefold().strip()}'
            async with self._lock:
                history = await self.config.snapshots()
                previous = history.get(key)
                new = {'time': int(time.time()), 'skills': data['skills'], 'activities': data['activities']}
                history[key] = new
                if len(history) > 200:
                    oldest = min(history, key=lambda k: history[k].get('time', 0))
                    history.pop(oldest)
                await self.config.snapshots.set(history)
            emb = self._embed(ctx, f'{player} • {game.upper()} gains')
            if previous is None:
                emb.description = 'Baseline saved. Run this again after playing to see XP, level and boss KC gains.'
            else:
                when = datetime.fromtimestamp(previous['time'], tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
                old_skills = previous.get('skills', {})
                xp_now = data['skills']['Overall']['xp']
                xp_before = old_skills.get('Overall', {}).get('xp', -1)
                xp_delta = xp_now - xp_before if xp_now >= 0 and xp_before >= 0 else None
                emb.description = f'Since **{when}** (snapshot updated just now).'
                emb.add_field(name='Total XP gained', value=format_number(xp_delta), inline=False)
                gained = sorted(((n, v['xp'] - old_skills[n]['xp'], v['level'] - old_skills[n]['level'])
                                 for n,v in data['skills'].items() if n != 'Overall' and n in old_skills
                                 and v['xp'] >= 0 and old_skills[n]['xp'] >= 0 and v['xp'] > old_skills[n]['xp']),
                                key=lambda r: -r[1])
                emb.add_field(name='Skill gains', value='\n'.join(
                    f'**{n}:** +{format_number(x)} XP' + (f' (+{lv} lvl)' if lv else '')
                    for n,x,lv in gained[:12]) or 'No new XP recorded', inline=False)
                if game.casefold() == 'osrs':
                    old_bosses = previous.get('activities', {})
                    bosses = [(name, row['score'] - old_bosses[name]['score'])
                              for name,row in boss_entries(data['activities']) if name in old_bosses
                              and old_bosses[name]['score'] >= 0 and row['score'] > old_bosses[name]['score']]
                    emb.add_field(name='Boss KC gains', value='\n'.join(
                        f'{n}: +{format_number(kc)}' for n,kc in sorted(bosses, key=lambda r:-r[1])[:10])
                        or 'No tracked boss kills', inline=False)
            await self._send(ctx, emb)
        except APIError as exc:
            await self._error(ctx, exc)

    async def _matching_items(self, item):
        raw = await self._fetch(f'{GE_API}/mapping', ttl=12*3600)
        if not isinstance(raw, list):
            raise APIError('The Grand Exchange item catalogue format changed.')
        return match_items(raw, item)

    @rsx.command(name='items')
    async def rsx_items(self, ctx, *, item: str):
        """Search the OSRS Grand Exchange item catalogue."""
        try:
            matches = await self._matching_items(item)
            if not matches:
                raise APIError('No matching OSRS Grand Exchange items found.')
            emb = self._embed(ctx, f'OSRS item search • {item}')
            for entry in matches:
                emb.add_field(name=str(entry['name'])[:200], value=f'Item ID: {entry["id"]}', inline=False)
            await self._send(ctx, emb)
        except APIError as exc:
            await self._error(ctx, exc)

    @rsx.command(name='price')
    async def rsx_price(self, ctx, *, item: str):
        """Real-time OSRS GE high/low quotes, 1-hour averages and volumes."""
        try:
            found = await self._matching_items(item)
            if not found:
                raise APIError('No matching OSRS GE item found.')
            entry = found[0]
            item_id = int(entry['id'])
            latest, hour = await asyncio.gather(
                self._fetch(f'{GE_API}/latest', {'id': str(item_id)}, ttl=75),
                self._fetch(f'{GE_API}/1h', {'id': str(item_id)}, ttl=150),
            )
            instant = latest.get('data', {}).get(str(item_id), {})
            hourly = hour.get('data', {}).get(str(item_id), {})
            if not instant and not hourly:
                raise APIError('No recent trading data available for that item.')
            emb = self._embed(ctx, f'{entry["name"]} • OSRS Grand Exchange',
                entry.get('examine') or None,
                f'https://prices.runescape.wiki/osrs/item/{item_id}')
            emb.add_field(name='Latest high quote', value=f'{format_number(instant.get("high"))} gp\n{age(instant.get("highTime"))}')
            emb.add_field(name='Latest low quote', value=f'{format_number(instant.get("low"))} gp\n{age(instant.get("lowTime"))}')
            high = instant.get('high')
            low = instant.get('low')
            if isinstance(high, int) and isinstance(low, int):
                emb.add_field(name='High–low spread (not guaranteed profit)', value=f'{format_number(high-low)} gp')
            emb.add_field(name='1-hour avg high', value=f'{format_number(hourly.get("avgHighPrice"))} gp')
            emb.add_field(name='1-hour avg low', value=f'{format_number(hourly.get("avgLowPrice"))} gp')
            bought = hourly.get('highPriceVolume')
            sold = hourly.get('lowPriceVolume')
            emb.add_field(name='1-hour traded volume', value=(
                f'High: {format_number(bought)} / Low: {format_number(sold)}'), inline=False)
            limit = entry.get('limit')
            if limit is not None:
                emb.add_field(name='GE buy limit', value=format_number(limit))
            emb.add_field(name='Members item', value='Yes' if entry.get('members') else 'No')
            emb.add_field(name='Item ID', value=str(item_id))
            await self._send(ctx, emb)
        except APIError as exc:
            await self._error(ctx, exc)
