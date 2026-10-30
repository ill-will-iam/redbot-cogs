"""Pure-engine tests without requiring an installed Redbot instance."""
import importlib.util
from pathlib import Path
import random
import unittest

path = Path(__file__).resolve().parents[1] / "dig" / "loot.py"
spec = importlib.util.spec_from_file_location("dig_loot_under_test", path)
module = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class DeterministicRng:
    def __init__(self, chest_roll, golden_roll, valuable="diamond", pieces=4, worms=2):
        self.rolls = iter((chest_roll, golden_roll))
        self.valuable = valuable
        self.pieces = pieces
        self.worms = worms
        self.randint_calls = 0

    def randrange(self, count):
        return next(self.rolls)

    def choices(self, choices, weights, k):
        return [self.valuable]

    def randint(self, lo, hi):
        self.randint_calls += 1
        return self.pieces if self.randint_calls == 1 else self.worms


class DigLootTests(unittest.TestCase):
    def test_chest_golden_worm(self):
        result = module.roll_dig(400, rng=DeterministicRng(0, 24))
        self.assertEqual(result.kind, "chest")
        self.assertEqual(result.loot, {"diamond": 4, "earthworm": 2, "golden_worm": 1})

    def test_chest_without_golden_worm(self):
        result = module.roll_dig(200, rng=DeterministicRng(0, 25, valuable="gold_ore", pieces=2, worms=1))
        self.assertEqual(result.loot, {"gold_ore": 2, "earthworm": 1})

    def test_probability_rejects_invalid_range(self):
        for bp in (0, 199, 501, 10000):
            with self.assertRaises(ValueError):
                module.roll_dig(bp)

    def test_sale_only_marketables(self):
        bag = {"gold_ore": 2, "diamond": 1, "drug_stash": 3,
               "earthworm": 20, "golden_worm": 2}
        sale, total = module.inventory_sale(bag, "all", 1)
        self.assertEqual(sale, {"gold_ore": 2, "diamond": 1, "drug_stash": 3})
        self.assertEqual(total, 2 * 55 + 160 + 3 * 95)
        self.assertEqual(module.inventory_sale(bag, "diamond", 2), ({}, 0))

    def test_weights_sum_to_100(self):
        self.assertEqual(sum(module.WEIGHTS.values()), 100)

    def test_golden_worm_can_only_drop_inside_chest(self):
        rng = random.Random(527)
        for _ in range(10000):
            result = module.roll_dig(400, rng=rng)
            if "golden_worm" in result.loot:
                self.assertEqual(result.kind, "chest")

    def test_statistical_roll_chest_and_golden(self):
        rng = random.Random(841)
        rolls = [module.roll_dig(500, rng=rng) for _ in range(100000)]
        chests = [o for o in rolls if o.kind == "chest"]
        golden_chests = [o for o in chests if "golden_worm" in o.loot]
        self.assertTrue(4700 <= len(chests) <= 5300, len(chests))
        self.assertTrue(80 <= len(golden_chests) <= 180, len(golden_chests))


if __name__ == "__main__":
    unittest.main()
