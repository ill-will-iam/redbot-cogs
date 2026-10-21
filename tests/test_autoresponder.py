"""Standard-library tests for AutoResponder matching and input validation."""
import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "autoresponder" / "matching.py"
SPEC = importlib.util.spec_from_file_location("autoresponder_matching_under_test", SOURCE)
matching = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(matching)


class AutoResponderMatchingTests(unittest.TestCase):
    def test_whole_words_and_casefold(self):
        rules = matching.compile_rules({"cat": "mew", "hello": "hi"})
        self.assertEqual(matching.find_response("HELLO everyone!", rules), "hello")
        self.assertEqual(matching.find_response("a CaT!", rules), "cat")
        self.assertIsNone(matching.find_response("scatter and cattery", rules))

    def test_one_letter_words(self):
        rules = matching.compile_rules({"i": "hi"})
        self.assertEqual(matching.find_response("I am here", rules), "i")
        self.assertIsNone(matching.find_response("pineapple", rules))

    def test_phrase_whitespace(self):
        rules = matching.compile_rules({"good morning": "hi", "good": "ok"})
        self.assertEqual(matching.find_response("GOOD     MORNING!", rules), "good morning")
        self.assertEqual(matching.find_response("Good day", rules), "good")

    def test_longest_trigger_wins(self):
        rules = matching.compile_rules({"hello": "a", "hello everyone": "b"})
        self.assertEqual(matching.find_response("Hello everyone!", rules), "hello everyone")

    def test_extra_pipe_preserved(self):
        self.assertEqual(matching.parse_rule_input("  HELLO  |  Hi | howdy "), ("hello", "Hi | howdy"))

    def test_input_validation(self):
        for sample in ("no delimiter", " | empty", "hello |", "@everyone | beep", "word | " + "a"*1001):
            with self.subTest(sample=sample[:30]):
                with self.assertRaises(ValueError):
                    matching.parse_rule_input(sample)

    def test_global_rule_migration_preserves_existing_and_resolves_conflicts(self):
        legacy = {
            20: {"rules": {"hello": "twenty", "cat": "mew"}},
            10: {"rules": {" HELLO ": "ten", "hi": "greetings"}},
        }
        merged = matching.merge_legacy_rules({"hi": "already global"}, legacy)
        self.assertEqual(merged["hi"], "already global")
        self.assertEqual(merged["hello"], "ten")
        self.assertEqual(merged["cat"], "mew")
        self.assertEqual(legacy[20]["rules"]["hello"], "twenty")

    def test_global_migration_rejects_invalid_or_oversized_rules(self):
        legacy = {1: {"rules": {
            "@everyone": "unsafe trigger",
            "good": "",
            "long": "X" * 1001,
            "acceptable": "okay",
        }}}
        merged = matching.merge_legacy_rules({}, legacy)
        self.assertEqual(merged, {"acceptable": "okay"})

    def test_global_management_commands_require_bot_owner(self):
        import ast
        cog = Path(__file__).resolve().parents[1] / "autoresponder" / "autoresponder.py"
        source = cog.read_text(encoding="utf-8")
        tree = ast.parse(source)
        self.assertIn("self.config.register_global(", source)
        self.assertNotIn("self.config.guild(", source)
        protected = {"ar_add", "ar_edit", "ar_remove",
                     "ar_enable", "ar_disable", "ar_cooldown"}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in protected:
                decorator_names = {ast.unparse(dec) for dec in node.decorator_list}
                self.assertIn("commands.is_owner()", decorator_names, node.name)

    def test_apostrophes_and_unicode(self):
        self.assertEqual(matching.find_response("It's here!", matching.compile_rules({"it's": "yes"})), "it's")
        self.assertTrue(matching.valid_trigger("café"))
        self.assertTrue(matching.valid_trigger("a"))
        self.assertFalse(matching.valid_trigger("a_b"))


if __name__ == "__main__":
    unittest.main()
