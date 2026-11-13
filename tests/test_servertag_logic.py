import importlib.util
import pathlib
import unittest

module_path = pathlib.Path(__file__).resolve().parents[1] / "servertag" / "_logic.py"
spec = importlib.util.spec_from_file_location("servertag_logic", module_path)
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)


class ServerTagRuleTests(unittest.TestCase):
    def test_normal_member_with_own_tag(self):
        self.assertEqual(
            logic.wanted_roles(True, False, True, 10, 20, 30),
            {30: False, 20: False, 10: True},
        )

    def test_booster_with_tag_replaces_basic_tag(self):
        self.assertEqual(
            logic.wanted_roles(True, True, True, 10, 20, 30),
            {30: True, 20: True, 10: False},
        )

    def test_booster_no_tag(self):
        self.assertEqual(
            logic.wanted_roles(False, True, True, 10, 20, 30),
            {30: True, 20: False, 10: False},
        )

    def test_no_basic_role(self):
        self.assertEqual(
            logic.wanted_roles(True, False, False, 10, 20, 30),
            {30: False, 20: False, 10: False},
        )

    def test_unknown_tag_does_not_strip_tag_roles(self):
        self.assertEqual(logic.wanted_roles(None, True, True, 10, 20, 30), {30: True})

    def test_booster_without_special_tag_role(self):
        self.assertEqual(logic.wanted_roles(True, True, True, 10, None, 30), {30: True, 10: True})

    def test_boost_status_by_premium_since(self):
        self.assertTrue(logic.booster_state({"premium_since": "2026-11-12T00:00:00Z", "roles": []}, None))
        self.assertFalse(logic.booster_state({"premium_since": None, "roles": ["900"]}, 900))

    def test_boost_status_fallback(self):
        self.assertTrue(logic.booster_state({"roles": ["5", "900"]}, 900))
        self.assertIsNone(logic.booster_state({"roles": ["5"]}, None))

    def test_diff_permissions_and_overwrites(self):
        a = {"roles": {"1": {"name": "Member", "permissions": 1, "overwrites": {}}}}
        b = {"roles": {"1": {"name": "Member", "permissions": 2, "overwrites": {"42": {"allow": 1, "deny": 0}}}}}
        self.assertEqual(len(logic.changed_roles(a, b)), 2)

    def test_tag_matching(self):
        self.assertTrue(logic.wearing_guild_tag({"identity_enabled": True, "identity_guild_id": "123"}, 123))
        self.assertFalse(logic.wearing_guild_tag({"identity_enabled": True, "identity_guild_id": "234"}, 123))
        self.assertFalse(logic.wearing_guild_tag({"identity_enabled": False, "identity_guild_id": "123"}, 123))
        self.assertIsNone(logic.wearing_guild_tag("unexpected", 123))


if __name__ == "__main__":
    unittest.main()
