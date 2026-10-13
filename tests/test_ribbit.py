"""Basic static tests for The Royal Ribbit Reserve (without a running Redbot)."""
import ast
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RIBBIT = ROOT / "ribbit"


class TestRibbit(unittest.TestCase):
    def test_all_python_files_parse(self):
        for f in RIBBIT.glob("*.py"):
            with self.subTest(file=f.name):
                ast.parse(f.read_text(encoding="utf-8"), filename=str(f))

    def test_catches_and_market(self):
        spec = importlib.util.spec_from_file_location("ribbit_item_test", RIBBIT / "items.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(sum(item["weight"] for item in module.CATCHES.values()), 100)
        hazards = {k for k, item in module.CATCHES.items() if "penalty" in item}
        self.assertEqual(hazards, {"bee", "wasp", "fell_in_hole", "hit_by_car"})
        self.assertEqual(sum(item["weight"] for item in module.CATCHES.values() if "penalty" not in item), 85)
        self.assertEqual(sum(item["weight"] for item in module.CATCHES.values() if "penalty" in item), 15)
        for name, item in module.CATCHES.items():
            self.assertGreater(item["weight"], 0, name)
            if "penalty" in item:
                self.assertEqual(item["value"], 0)
                self.assertGreater(item["penalty"][0], 0)
                self.assertGreaterEqual(item["penalty"][1], item["penalty"][0])
                self.assertTrue(item["incident"])
            else:
                self.assertGreater(item["value"], 0)
        for item in module.SHOP.values():
            self.assertGreater(item["price"], 0)
        for _ in range(100):
            self.assertIn(module.catch_random(), module.CATCHES)


if __name__ == "__main__":
    unittest.main()
