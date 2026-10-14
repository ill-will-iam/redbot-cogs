"""Rule, turn, and regression checks without Redbot / Discord installed."""
import ast
import importlib.util
from pathlib import Path
import random
import unittest

ROOT = Path(__file__).resolve().parents[1]
FROGCRIB = ROOT / 'frogcrib'
spec = importlib.util.spec_from_file_location('crib_engine_tests', FROGCRIB / 'engine.py')
engine = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = engine
spec.loader.exec_module(engine)


class CribbageEngineTests(unittest.TestCase):
    def test_syntax(self):
        for path in FROGCRIB.glob('*.py'):
            ast.parse(path.read_text(encoding='utf-8'), filename=str(path))

    def test_29_point_hand(self):
        score, parts = engine.hand_score(['5C', '5D', '5H', 'JS'], '5S')
        self.assertEqual(score, 29)
        self.assertEqual(parts['fifteens'], 16)
        self.assertEqual(parts['pairs'], 12)
        self.assertEqual(parts['nobs'], 1)

    def test_runs_multiplicity(self):
        score, parts = engine.hand_score(['3C', '3D', '4H', '5S'], '6C')
        self.assertEqual(parts['runs'], 8)  # two four-card runs, not smaller ones
        self.assertEqual(parts['pairs'], 2)

    def test_flush_and_nobs(self):
        four, _ = engine.hand_score(['AC', '4C', '7C', 'JC'], 'KH')
        crib, _ = engine.hand_score(['AC', '4C', '7C', 'JC'], 'KH', crib=True)
        self.assertEqual(four - crib, 4)
        five, parts = engine.hand_score(['AC', '4C', '7C', 'JC'], 'KC', crib=True)
        self.assertEqual(parts['flush'], 5)
        self.assertEqual(parts['nobs'], 1)

    def test_pegging_pairs_runs_fifteens(self):
        self.assertEqual(engine.peg_score(['7H', '8C']), 2)
        self.assertEqual(engine.peg_score(['2C', '2D']), 2)
        self.assertEqual(engine.peg_score(['2C', '2D', '2H']), 6)
        self.assertEqual(engine.peg_score(['2C', '2D', '2H', '2S']), 12)
        self.assertEqual(engine.peg_score(['9H', '6C', '8C', '7D']), 4)
        self.assertEqual(engine.peg_score(['8H', '7C', '7D', '6S']), 0)

    def test_go_requires_no_playable_cards(self):
        game = engine.CribbageGame((111, 222), dealer=0)
        game.begin()
        game.discard(0, 1, 2)
        game.discard(1, 1, 2)
        with self.assertRaises(ValueError):
            game.go(game.turn)

    def test_no_early_last_card_bonus_on_31(self):
        game = engine.CribbageGame((111, 222), dealer=0)
        game.begin()
        game.discard(0, 1, 2)
        game.discard(1, 1, 2)
        # Isolate the pegging transition from shuffled cards.
        game.hands = [['AC'], ['TC']]
        game.kept = [['AC', '2C', '3C', '4C'], ['TC', '2H', '3H', '4H']]
        game.starter = '5S'
        game.turn = 1
        game.count = 21
        game.segment = ['KH', 'TS', 'AS']  # deliberately artificial count
        game.play(1, 1)
        self.assertEqual(game.scores[1], 2)  # exactly 31, no extra 'go'

    def test_scoring_order_and_immediate_winner(self):
        game = engine.CribbageGame((111, 222), dealer=0, scores=[120, 119])
        game.begin()
        game.discard(0, 1, 2)
        game.discard(1, 1, 2)
        # Winner from the first show (non-dealer) must not give the dealer crib points.
        game.scores = [120, 119]
        game.kept = [['AC', '2C', '3C', '4C'], ['5C', '5D', '5H', 'JS']]
        game.crib = ['7C', '8D', '9H', 'TS']
        game.starter = '5S'
        game.phase = 'pegging'
        events = []
        game._show(events)
        self.assertEqual(game.winner, 1)
        self.assertEqual(game.phase, 'finished')
        self.assertFalse(any('**crib**' in e for e in events))

    def test_simulated_matches_finish_and_cards_legal(self):
        rng = random.Random(1234)
        for _ in range(25):
            game = engine.CribbageGame((111, 222), dealer=rng.randrange(2))
            game.begin()
            for turn in range(2000):
                if game.phase == 'finished':
                    break
                if game.phase == 'discard':
                    for idx in (0, 1):
                        if not game.kept[idx]:
                            game.discard(idx, 1, 2)
                elif game.phase == 'pegging':
                    idx = game.turn
                    legal = [i for i, card in enumerate(game.hands[idx], 1)
                             if engine.value(card) + game.count <= 31]
                    if legal:
                        game.play(idx, rng.choice(legal))
                    else:
                        game.go(idx)
                else:
                    self.fail(f'Unexpected phase: {game.phase}')
                self.assertLessEqual(game.count, 31)
                self.assertTrue(all(len(cards) <= 6 for cards in game.hands))
            else:
                self.fail('Game stalled')
            self.assertGreaterEqual(game.scores[game.winner], 121)
            self.assertNotEqual(game.winner, -1)


if __name__ == '__main__':
    unittest.main()
