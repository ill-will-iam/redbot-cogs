"""Pure OSRS hiscores/GE helpers. Kept free of Discord imports for testing."""
import math
import re
from datetime import datetime, timezone

OSRS_SKILL_ORDER = (
    'Overall', 'Attack', 'Defence', 'Strength', 'Hitpoints', 'Ranged',
    'Prayer', 'Magic', 'Cooking', 'Woodcutting', 'Fletching', 'Fishing',
    'Firemaking', 'Crafting', 'Smithing', 'Mining', 'Herblore', 'Agility',
    'Thieving', 'Slayer', 'Farming', 'Runecraft', 'Hunter', 'Construction',
    'Sailing',
)
# Explicit list prevents minigame scores from being mislabelled as boss kills.
BOSS_NAMES = frozenset('''
Abyssal Sire|Alchemical Hydra|Amoxliatl|Araxxor|Artio|Barrows Chests|Bryophyta|
Callisto|Calvar'ion|Cerberus|Chambers of Xeric|Chambers of Xeric: Challenge Mode|
Chaos Elemental|Chaos Fanatic|Commander Zilyana|Corporeal Beast|Crazy Archaeologist|
Dagannoth Prime|Dagannoth Rex|Dagannoth Supreme|Deranged Archaeologist|
Duke Sucellus|General Graardor|Giant Mole|Grotesque Guardians|Hespori|
Kalphite Queen|King Black Dragon|Kraken|Kree'Arra|K'ril Tsutsaroth|
Lunar Chests|Mimic|Nex|Nightmare|Phosani's Nightmare|Obor|Phantom Muspah|
Sarachnis|Scorpia|Scurrius|Skotizo|Sol Heredit|Spindel|Tempoross|
The Corrupted Gauntlet|The Gauntlet|The Hueycoatl|The Leviathan|
The Royal Titans|The Whisperer|Theatre of Blood|Theatre of Blood: Hard Mode|
Thermonuclear Smoke Devil|Tombs of Amascut|Tombs of Amascut: Expert Mode|
TzKal-Zuk|TzTok-Jad|Vardorvis|Venenatis|Vet'ion|Vorkath|Wintertodt|Yama|Zalcano|Zulrah
'''.replace('\n','').split('|'))

NAME_PATTERN = re.compile(r'^[A-Za-z0-9 _-]{1,12}$')


def validate_name(name):
    return bool(NAME_PATTERN.fullmatch(name.strip()))


def format_number(n):
    return f'{n:,}' if isinstance(n, int) and n >= 0 else '—'


def parse_osrs(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('skills'), list):
        raise ValueError('Unexpected OSRS hiscores response')
    skills = {}
    for row in payload['skills']:
        if not isinstance(row, dict):
            continue
        name = str(row.get('name', '')).strip()
        if name:
            skills[name] = {'rank': to_int(row.get('rank')), 'level': to_int(row.get('level')), 'xp': to_int(row.get('xp'))}
    activities = {}
    for row in payload.get('activities', []):
        if not isinstance(row, dict):
            continue
        name = str(row.get('name', '')).strip()
        if name:
            activities[name] = {'rank': to_int(row.get('rank')), 'score': to_int(row.get('score'))}
    if not skills or 'Overall' not in skills:
        raise ValueError('Missing OSRS skill data')
    return {'skills': skills, 'activities': activities}


def to_int(n):
    try:
        if n is None:
            return -1
        return int(float(n))
    except (ValueError, TypeError, OverflowError):
        return -1


def xp_for_level(level):
    if not 1 <= level <= 126:
        raise ValueError('Level must be between 1 and 126')
    points = sum(math.floor(i + 300 * (2 ** (i / 7))) for i in range(1, level))
    return points // 4


def virtual_level(xp):
    if xp < 0:
        return None
    for level in range(126, 1, -1):
        if xp >= xp_for_level(level):
            return level
    return 1


def xp_until_next(xp, current_level, limit=99):
    if xp < 0 or current_level < 1 or current_level >= limit:
        return None
    return max(0, xp_for_level(current_level + 1) - xp)


def osrs_combat(skills):
    try:
        level = lambda n: max(1, int(skills[n]['level']))
        base = (level('Defence') + level('Hitpoints') + (level('Prayer') // 2)) / 4
        style = max(level('Attack') + level('Strength'),
                    math.floor(level('Ranged') * 1.5),
                    math.floor(level('Magic') * 1.5))
        return math.floor(base + style * 0.325)
    except (KeyError, TypeError, ValueError):
        return None


def maxed_count(skills, level=99):
    return sum(1 for name, row in skills.items() if name != 'Overall' and row['level'] >= level)


def boss_entries(activities):
    return sorted(((name, row) for name, row in activities.items()
                   if name in BOSS_NAMES and row['score'] >= 0),
                  key=lambda item: (-item[1]['score'], item[0].lower()))


def clue_entries(activities):
    return sorted(((name, row) for name, row in activities.items()
                   if name.lower().startswith('clue scrolls') and row['score'] >= 0),
                  key=lambda item: item[0].lower())


def match_items(mapping, needle, max_results=8):
    target = needle.casefold().strip()
    if not target:
        return []
    exact = [m for m in mapping if str(m.get('name','')).casefold() == target]
    prefix = [m for m in mapping if str(m.get('name','')).casefold().startswith(target) and m not in exact]
    other = [m for m in mapping if target in str(m.get('name','')).casefold() and m not in exact and m not in prefix]
    return (exact + prefix + other)[:max_results]


def age(ts):
    if not ts:
        return 'Unknown'
    try:
        secs = max(0, int((datetime.now(timezone.utc) - datetime.fromtimestamp(int(ts), tz=timezone.utc)).total_seconds()))
        return f'{secs//86400}d ago' if secs >= 86400 else (f'{secs//3600}h ago' if secs >= 3600 else f'{secs//60}m ago')
    except (ValueError, TypeError, OverflowError, OSError):
        return 'Unknown'
