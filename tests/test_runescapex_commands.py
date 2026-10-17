"""Static command-contract checks without requiring a running Red instance."""
import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / 'runescapex' / 'runescapex.py'
TREE = ast.parse(SOURCE.read_text(encoding='utf-8'))
COG = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'RuneScapeX')
METHODS = {n.name: n for n in COG.body if isinstance(n, ast.AsyncFunctionDef)}


def test_osrs_only_has_no_game_selector_or_rs3_commands():
    src = SOURCE.read_text(encoding='utf-8')
    assert 'RS3_HISCORES' not in src
    assert 'parse_rs3' not in src
    for name in ('rsx_skills', 'rsx_skill', 'rsx_compare', 'rsx_gains'):
        args = [a.arg for a in METHODS[name].args.args]
        assert 'game' not in args
        assert 'game' not in [a.arg for a in METHODS[name].args.kwonlyargs]
    assert 'rsx_rs3' not in METHODS
    assert 'rsx_osrs' not in METHODS


def test_simple_profile_entry_and_help_routing():
    top = METHODS['rsx']
    assert [a.arg for a in top.args.kwonlyargs] == ['player']
    assert isinstance(top.args.kw_defaults[0], ast.Constant)
    assert top.args.kw_defaults[0].value is None
    assert 'self._profile(ctx, player)' in ast.unparse(top)
    assert 'self._show_help(ctx)' in ast.unparse(top)
    assert 'self._show_help(ctx)' in ast.unparse(METHODS['rsx_help'])


def test_osrs_snapshot_namespace_is_preserved():
    gains = ast.unparse(METHODS['rsx_gains'])
    assert 'osrs:' in gains
    assert "self._stats(player)" in gains


def test_all_feature_commands_are_present():
    assert {'rsx_profile', 'rsx_skills', 'rsx_skill', 'rsx_bosses',
            'rsx_clues', 'rsx_compare', 'rsx_gains', 'rsx_price',
            'rsx_items', 'rsx_help'} <= set(METHODS)
