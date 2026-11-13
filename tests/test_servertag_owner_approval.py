"""Static and logic checks for elevated-role approvals and exclusive tag tiers."""
import ast
import importlib.util
import pathlib
import unittest

BASE = pathlib.Path(__file__).resolve().parents[1]
SOURCE = (BASE / "servertag" / "servertag.py").read_text()
module_path = BASE / "servertag" / "_logic.py"
spec = importlib.util.spec_from_file_location("taglogic_local", module_path)
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)

class TestTagAndBoosterTiers(unittest.TestCase):
    def test_source_compiles(self):
        ast.parse(SOURCE)

    def test_owner_approval_and_exact_permission_matching_present(self):
        self.assertIn('ctx.author.id != ctx.guild.owner_id', SOURCE)
        self.assertIn('approvals.get(str(role.id)) != role.permissions.value', SOURCE)
        self.assertIn('confirmation != "I_ACCEPT_PRIVILEGES"', SOURCE)

    def test_boost_only_never_rewards_radiants(self):
        result = logic.wanted_roles(False, True, True, 101, 202, None)
        self.assertFalse(result[202])
        self.assertFalse(result[101])

    def test_tag_only_rewards_luminaries(self):
        result = logic.wanted_roles(True, False, True, 101, 202, None)
        self.assertTrue(result[101])
        self.assertFalse(result[202])

    def test_tag_and_boost_only_rewards_radiants(self):
        result = logic.wanted_roles(True, True, True, 101, 202, None)
        self.assertFalse(result[101])
        self.assertTrue(result[202])

    def test_untag_downgrades_to_no_custom_roles(self):
        for boosting in (False, True):
            result = logic.wanted_roles(False, boosting, True, 101, 202, None)
            self.assertFalse(result[101])
            self.assertFalse(result[202])


if __name__ == "__main__":
    unittest.main()
