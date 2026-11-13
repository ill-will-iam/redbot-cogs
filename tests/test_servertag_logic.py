import importlib.util
import pathlib
import unittest

path = pathlib.Path(__file__).resolve().parents[1] / "servertag" / "_logic.py"
spec = importlib.util.spec_from_file_location("taglogic", path)
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)


class TestServerTagMatching(unittest.TestCase):
    def test_equipped_own_guild(self):
        self.assertTrue(logic.wearing_guild_tag({"identity_enabled": True, "identity_guild_id": "123", "tag": "COOL"}, 123))

    def test_same_visible_tag_different_guild(self):
        self.assertFalse(logic.wearing_guild_tag({"identity_enabled": True, "identity_guild_id": "999", "tag": "COOL"}, 123))

    def test_hidden_same_guild(self):
        self.assertFalse(logic.wearing_guild_tag({"identity_enabled": False, "identity_guild_id": "123"}, 123))

    def test_disabled_or_removed(self):
        self.assertFalse(logic.wearing_guild_tag(None, 123))
        self.assertFalse(logic.wearing_guild_tag({"identity_enabled": None, "identity_guild_id": "123"}, 123))

    def test_uninterpretable_id(self):
        self.assertIsNone(logic.wearing_guild_tag({"identity_enabled": True, "identity_guild_id": "invalid"}, 123))


if __name__ == "__main__":
    unittest.main()
