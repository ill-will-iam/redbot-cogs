"""Offline reset orchestration tests; real discord.py types, no Discord requests."""

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, patch

import discord
from discord.ext import commands

ROOT = Path(__file__).resolve().parent.parent


def load_modules():
    package = types.ModuleType("haven_test")
    package.__path__ = [str(ROOT / "haven")]
    core = types.ModuleType("redbot.core")
    core.Config, core.commands = object, commands
    manager = types.ModuleType("redbot.core.data_manager")
    manager.cog_data_path = lambda cog: cog.directory
    with patch.dict(sys.modules, {"haven_test": package, "redbot": types.ModuleType("redbot"),
                                 "redbot.core": core, "redbot.core.data_manager": manager}):
        modules = []
        for name in ("reset", "haven"):
            spec = importlib.util.spec_from_file_location(f"haven_test.{name}", ROOT / "haven" / f"{name}.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            modules.append(module)
        return modules


reset, haven = load_modules()
NS = types.SimpleNamespace


class Role:
    def __init__(self, id, position, managed=False, **permissions):
        self.id, self.position, self.managed = id, position, managed
        self.permissions = discord.Permissions(**permissions)
        self.edit = AsyncMock(side_effect=self._edit)

    def is_default(self):
        return self.id == 1

    def __ge__(self, other):
        return self.position >= other.position

    def __gt__(self, other):
        return self.position > other.position

    async def _edit(self, permissions, **kwargs):
        self.permissions = permissions


class Member:
    def __init__(self, id, roles):
        self.id, self.roles = id, roles
        self.send = AsyncMock()
        self.remove_roles = AsyncMock(side_effect=self._remove)

    async def _remove(self, *roles, **kwargs):
        self.roles = [r for r in self.roles if r not in roles]


class ResetTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        everyone = Role(1, 0, view_channel=True, send_messages=True)
        bot_role, user_role = Role(2, 10, True, administrator=True), Role(3, 2, administrator=True)
        self.roles = [everyone, bot_role, user_role]
        self.owner, self.me, self.user = Member(10, [everyone]), Member(20, [everyone, bot_role]), Member(30, [everyone, user_role])
        self.members = [self.owner, self.me, self.user]
        self.channels = []
        for id in (100, 101):
            channel = NS(id=id, name=str(id), type=NS(value=0))
            async def delete(channel=channel, **kwargs):
                self.channels.remove(channel)
            channel.delete = AsyncMock(side_effect=delete)
            self.channels.append(channel)
        self.original = list(self.channels)
        self.guild = NS(id=1, owner_id=10, features=[], default_role=everyone)
        async def members(**kwargs):
            for member in self.members:
                yield member
        async def edit(**kwargs):
            self.guild.features.append("INVITES_DISABLED")
        self.room = NS(id=999, send=AsyncMock())
        async def create(*args, **kwargs):
            self.channels.append(self.room)
            return self.room
        self.guild.fetch_members = members
        self.guild.fetch_roles = AsyncMock(side_effect=lambda: self.roles)
        self.guild.fetch_member = AsyncMock(side_effect=lambda id: next(m for m in self.members if m.id == id))
        self.guild.fetch_channels = AsyncMock(side_effect=lambda: list(self.channels))
        self.guild.edit = AsyncMock(side_effect=edit)
        self.guild.create_text_channel = AsyncMock(side_effect=create)
        self.bot = NS(user=self.me, intents=NS(members=True), is_owner=AsyncMock(return_value=True),
                      fetch_guild=AsyncMock(return_value=self.guild), wait_for=AsyncMock())
        self.store = NS(snapshot=AsyncMock(return_value=None), reset_last=NS(set=AsyncMock()))
        self.cog = NS(bot=self.bot, directory=Path(self.temp.name), config=NS(guild=lambda guild: self.store))
        self.ctx = NS(author=self.owner, guild=self.guild, channel=NS(id=100), send=AsyncMock())
        self.engine = reset.ServerReset(self.cog, self.ctx)

    async def test_success_preserves_owner_bot_and_role_definitions(self):
        plan = await self.engine.plan()
        await self.engine.execute(plan)
        self.assertEqual(self.channels, [self.room])
        self.assertEqual([r.id for r in self.user.roles], [1])
        self.assertEqual(len(self.roles), 3)
        self.owner.remove_roles.assert_not_called()
        self.me.remove_roles.assert_not_called()
        self.assertEqual(self.store.reset_last.set.call_args.args[0]["state"], "complete")
        events = [json.loads(line) for line in self.engine.path.read_text().splitlines()]
        self.assertEqual(events[0]["event"], "snapshot")
        self.assertEqual(events[-1]["event"], "complete")
        overwrites = self.guild.create_text_channel.call_args.kwargs["overwrites"]
        self.assertFalse(overwrites[self.guild.default_role].view_channel)
        self.assertTrue(overwrites[self.owner].view_channel)

    async def test_refused_pause_never_removes_roles_or_channels(self):
        plan = await self.engine.plan()
        self.guild.edit.side_effect = reset.ResetBlocked("unsupported")
        with self.assertRaises(reset.ResetBlocked):
            await self.engine.execute(plan)
        self.user.remove_roles.assert_not_called()
        self.assertEqual(self.channels, self.original)
        self.assertEqual(self.store.reset_last.set.call_args.args[0]["state"], "incomplete")

    async def test_unconfirmed_pause_stops(self):
        plan = await self.engine.plan()
        self.guild.edit.side_effect = None
        with self.assertRaises(reset.ResetBlocked):
            await self.engine.execute(plan)
        self.user.remove_roles.assert_not_called()

    async def test_privileged_managed_role_blocks_preview(self):
        self.roles[2].managed = True
        with self.assertRaises(reset.ResetBlocked):
            await self.engine.plan()
        self.guild.edit.assert_not_called()

    async def test_hierarchy_blocks_preview(self):
        self.roles[2].position = 10
        with self.assertRaises(reset.ResetBlocked):
            await self.engine.plan()

    async def test_owner_and_bot_owner_both_required(self):
        self.bot.is_owner.return_value = False
        with self.assertRaises(reset.ResetBlocked):
            await self.engine.plan()
        self.bot.is_owner.return_value = True
        self.guild.owner_id = 777
        with self.assertRaises(reset.ResetBlocked):
            await self.engine.plan()

    async def test_new_member_role_before_delete_stops(self):
        plan = await self.engine.plan()
        self.members.append(Member(40, [self.roles[0], self.roles[2]]))
        with self.assertRaises(reset.ResetBlocked):
            await self.engine.execute(plan)
        self.assertEqual(self.channels, self.original)

    async def test_delete_failure_stops_remaining_deletions(self):
        self.original[0].delete.side_effect = reset.ResetBlocked("failed")
        with self.assertRaises(reset.ResetBlocked):
            await self.engine.execute(await self.engine.plan())
        self.original[1].delete.assert_not_called()
        self.assertEqual(self.store.reset_last.set.call_args.args[0]["state"], "incomplete")

    async def test_snapshot_and_community_block(self):
        self.store.snapshot.return_value = {"old": "seal"}
        with self.assertRaises(reset.ResetBlocked):
            await self.engine.plan()
        self.store.snapshot.return_value = None
        self.guild.features = ["COMMUNITY"]
        with self.assertRaises(reset.ResetBlocked):
            await self.engine.plan()

    async def test_preview_is_read_only(self):
        self.cog._lock = lambda id: asyncio.Lock()
        await haven.Haven.haven_nuke.callback(self.cog, self.ctx, "preview")
        self.guild.edit.assert_not_called()
        self.user.remove_roles.assert_not_called()
        self.assertEqual(self.channels, self.original)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    async def test_timeout_is_read_only(self):
        self.cog._lock = lambda id: asyncio.Lock()
        self.bot.wait_for.side_effect = asyncio.TimeoutError()
        await haven.Haven.haven_nuke.callback(self.cog, self.ctx)
        self.guild.edit.assert_not_called()

    async def test_confirmation_scope(self):
        self.cog._lock = lambda id: asyncio.Lock()
        self.bot.wait_for.side_effect = asyncio.TimeoutError()
        await haven.Haven.haven_nuke.callback(self.cog, self.ctx)
        check = self.bot.wait_for.call_args.kwargs["check"]
        phrase = self.ctx.send.call_args_list[1].args[0].split("`")[1]
        good = NS(author=self.owner, channel=self.ctx.channel, guild=self.guild, content=phrase)
        self.assertTrue(check(good))
        good.author = self.user
        self.assertFalse(check(good))
        good.author, good.channel = self.owner, NS(id=101)
        self.assertFalse(check(good))

    async def test_role_removal_failure_prevents_channel_deletion(self):
        self.user.remove_roles.side_effect = reset.ResetBlocked("role update refused")
        with self.assertRaises(reset.ResetBlocked):
            await self.engine.execute(await self.engine.plan())
        for channel in self.original:
            channel.delete.assert_not_called()

    async def test_audit_failure_prevents_mutation(self):
        with patch.object(self.engine, "audit", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                await self.engine.execute(await self.engine.plan())
        self.guild.edit.assert_not_called()

    async def test_changed_plan_requires_new_confirmation(self):
        self.cog._lock = lambda id: asyncio.Lock()
        async def confirm(*args, **kwargs):
            self.roles[2].permissions.send_messages = True
        self.bot.wait_for.side_effect = confirm
        await haven.Haven.haven_nuke.callback(self.cog, self.ctx)
        self.guild.edit.assert_not_called()
        self.assertIn("state changed", self.ctx.send.call_args.args[0])

    async def test_cancellation_records_incomplete(self):
        self.guild.edit.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.engine.execute(await self.engine.plan())
        self.assertEqual(self.store.reset_last.set.call_args.args[0]["state"], "incomplete")
        for channel in self.original:
            channel.delete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
