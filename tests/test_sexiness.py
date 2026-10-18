"""Standard-library tests for Sexiness scoring (no Discord dependency)."""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "sexiness" / "scoring.py"
SPEC = importlib.util.spec_from_file_location("sexiness_scoring_under_test", SOURCE)
scoring = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scoring)


class SexinessScoringTests(unittest.TestCase):
    def test_score_is_inclusive_0_to_100(self):
        with patch.object(scoring.random, "randint", return_value=0) as mocked:
            self.assertEqual(scoring.roll_score(), 0)
            mocked.assert_called_once_with(0, 100)
        with patch.object(scoring.random, "randint", return_value=100):
            self.assertEqual(scoring.roll_score(), 100)

    def test_all_quip_bands(self):
        with patch.object(scoring.random, "choice", side_effect=lambda values: values[0]):
            for value, options in (
                (0, scoring.LOW_QUIPS),
                (33, scoring.LOW_QUIPS),
                (34, scoring.MID_QUIPS),
                (66, scoring.MID_QUIPS),
                (67, scoring.HIGH_QUIPS),
                (99, scoring.HIGH_QUIPS),
                (100, scoring.LEGENDARY_QUIPS),
            ):
                with self.subTest(value=value):
                    self.assertEqual(scoring.choose_quip(value), options[0])

    def test_bar_has_exactly_ten_characters(self):
        for score in range(101):
            with self.subTest(score=score):
                bar = scoring.meter(score)
                self.assertEqual(len(bar), 10)
                self.assertEqual(bar.count("\u25b0"), (score + 5) // 10)
        self.assertEqual(scoring.meter(0), "\u25b1" * 10)
        self.assertEqual(scoring.meter(100), "\u25b0" * 10)

    def test_out_of_range_is_rejected(self):
        for score in (-1, 101):
            with self.subTest(score=score):
                with self.assertRaises(ValueError):
                    scoring.choose_quip(score)
                with self.assertRaises(ValueError):
                    scoring.meter(score)


if __name__ == "__main__":
    unittest.main()
