"""Tests of pure engine helpers, no Red/Discord runtime required."""
from pathlib import Path
import importlib.util

SRC = Path(__file__).resolve().parents[1] / 'runescapex' / 'engine.py'
spec = importlib.util.spec_from_file_location('rsx_engine', SRC)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


def test_xp_curve_and_combat():
    assert engine.xp_for_level(99) == 13034431
    assert engine.xp_for_level(2) == 83
    assert engine.virtual_level(13034431) == 99
    assert engine.virtual_level(0) == 1
    assert engine.xp_until_next(0, 1) == 83
    assert engine.xp_until_next(13034431, 99) is None
    assert engine.osrs_combat({n: {'level':99} for n in ('Attack', 'Strength','Defence','Hitpoints','Prayer','Ranged','Magic')}) == 126


def test_named_osrs_hiscores_and_new_activity():
    skills = [{'name': 'Overall', 'rank': '1', 'level': 2376, 'xp': 4000000000},
              {'name': 'Sailing', 'rank': 42, 'level': 99, 'xp': 13034431}]
    acts = [{'name': 'Zulrah', 'rank': 12, 'score': 500},
            {'name': 'Clue Scrolls (easy)', 'rank': -1, 'score': -1},
            {'name': 'Mystery Activity', 'rank': 1, 'score': 1000}]
    data = engine.parse_osrs({'skills': skills, 'activities': acts})
    assert data['skills']['Sailing']['level'] == 99
    assert engine.boss_entries(data['activities'])[0][0] == 'Zulrah'
    assert engine.clue_entries(data['activities']) == []


def test_rs3_lite_csv():
    csv = '\n'.join(f'{i},99,13034431' for i in range(len(engine.RS3_SKILL_ORDER)))
    data = engine.parse_rs3(csv)
    assert data['skills']['Necromancy']['level'] == 99
    assert data['skills']['Overall']['rank'] == 0


def test_names_items_gaps():
    assert engine.validate_name('Lynx Titan')
    assert not engine.validate_name('x'*13)
    assert engine.percent_change(12, 10) == 20
    rows = [{'name':'Dragon claws','id':1}, {'name':'Dragon bones','id':2}, {'name':'Abyssal whip','id':3}]
    assert engine.match_items(rows, 'dragon bones')[0]['id'] == 2
    assert len(engine.match_items(rows,'dragon')) == 2


def test_unranked_skill_and_errors():
    assert engine.format_number(-1) == '—'
    assert engine.format_number(None) == '—'
    try:
        engine.parse_osrs({'skills': []})
    except ValueError:
        pass
    else:
        raise AssertionError('Malformed hiscores accepted')
