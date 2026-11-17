"""Static and logic checks for elevated-role approvals and exclusive tag tiers."""
from __future__ import annotations

import ast
import asyncio
import importlib.util
import pathlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

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



class TestServerBinding(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        source = ast.parse(SOURCE)
        cog_class = next(node for node in source.body if isinstance(node, ast.ClassDef))
        method_names = {
            "_in_bound_server", "_check_bound_context", "cog_check", "tagrole", "tagrole_bind"
        }
        methods = [node for node in cog_class.body if getattr(node, "name", None) in method_names]
        for method in methods:
            method.decorator_list = []
        cog_class.bases = []
        cog_class.body = methods
        namespace = {"discord": SimpleNamespace(AllowedMentions=SimpleNamespace(none=lambda: None))}
        tree = ast.Module(body=[cog_class], type_ignores=[])
        exec(compile(tree, "<servertag binding checks>", "exec"), namespace)
        self.cog = namespace["ServerTag"]()
        self.server_id = AsyncMock(return_value=None)
        self.server_id.set = AsyncMock()
        self.cog._binding_lock = asyncio.Lock()
        self.cog.config = SimpleNamespace(server_id=self.server_id)
        self.cog.bot = SimpleNamespace(is_owner=AsyncMock(return_value=True))
        self.bind_callback = self.cog.tagrole_bind
        self.cog.tagrole_bind = object()
        self.group_callback = self.cog.tagrole
        self.cog.tagrole = object()
        self.ctx = SimpleNamespace(
            guild=SimpleNamespace(id=42, name="Target"), author=object(), command=self.cog.tagrole,
            clean_prefix="~", send=AsyncMock(), send_help=AsyncMock(),
        )

    async def test_bind_passes_reds_group_and_subcommand_checks_before_binding(self):
        # Red checks the parent with ctx.command set to the group first.
        self.assertTrue(await self.cog.cog_check(self.ctx))
        self.ctx.command = self.cog.tagrole_bind
        self.assertTrue(await self.cog.cog_check(self.ctx))
        self.ctx.send.assert_not_awaited()
        await self.bind_callback(self.ctx)
        self.server_id.set.assert_awaited_once_with(42)
        self.ctx.send.assert_awaited_once_with("ServerTag is bound to Target.", allowed_mentions=None)

    async def test_reward_commands_require_the_bound_server(self):
        self.ctx.command = object()
        self.assertFalse(await self.cog.cog_check(self.ctx))
        self.server_id.return_value = 77
        self.assertFalse(await self.cog.cog_check(self.ctx))
        self.server_id.return_value = 42
        self.assertTrue(await self.cog.cog_check(self.ctx))

    async def test_bare_group_displays_bind_hint_until_bound(self):
        await self.group_callback(self.ctx)
        self.ctx.send.assert_awaited_once()
        self.ctx.send_help.assert_not_awaited()
        self.server_id.return_value = 42
        await self.group_callback(self.ctx)
        self.ctx.send_help.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
