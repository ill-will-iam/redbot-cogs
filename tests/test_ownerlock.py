"""OwnerLock's policy helpers and source-level integration checks (stdlib only)."""

import ast
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "ownerlock" / "rules.py"
SPEC = importlib.util.spec_from_file_location("ownerlock_rules_test", SRC)
rules = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rules)


class OwnerLockRuleTests(unittest.TestCase):
    def test_canonical_case_and_spaces(self):
        self.assertEqual(rules.canonical_cog_name("  AutoResponder  "), "autoresponder")
        self.assertEqual(rules.canonical_cog_name("Cool   Cog"), "cool cog")

    def test_owners_can_use_protected_commands(self):
        names = {"purge", "autoresponder"}
        self.assertTrue(rules.command_allowed("Purge", names, True))
        self.assertTrue(rules.command_allowed("AutoResponder", names, True))

    def test_regular_users_cannot_use_protected_commands(self):
        names = {"purge", "autoresponder"}
        self.assertFalse(rules.command_allowed("PURGE", names, False))
        self.assertFalse(rules.command_allowed("autoresponder", names, False))
        self.assertTrue(rules.command_allowed("Birthday", names, False))

    def test_all_management_commands_are_owner_only(self):
        source = (ROOT / "ownerlock" / "ownerlock.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        protected = {"ownerlock", "protect", "unprotect", "protected_list", "inspect", "cogs"}
        seen = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name in protected:
                seen.add(node.name)
                self.assertTrue(
                    any(ast.unparse(d) == "commands.is_owner()" for d in node.decorator_list),
                    node.name,
                )
        self.assertSetEqual(seen, protected)
        self.assertIn("self.bot.add_check(self._command_check_callback)", source)
        self.assertIn("self.bot.remove_check(self._command_check_callback)", source)
        self.assertIn("command.cog.qualified_name", source)
        self.assertIn("self.config.register_global", source)

    def test_automated_replies_cooperate_with_ownerlock(self):
        for path in ["autoresponder/autoresponder.py", "bannedwords/bannedwords.py"]:
            with self.subTest(path=path):
                source = (ROOT / path).read_text(encoding="utf-8")
                self.assertIn('self.bot.get_cog("OwnerLock")', source)
                self.assertIn("await ownerlock.allows_event(self.qualified_name, message.author)", source)


if __name__ == "__main__":
    unittest.main()
