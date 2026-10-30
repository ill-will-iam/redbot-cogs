"""Mock Red's Config and bank to test Dig command state transitions."""
import asyncio
import copy
import importlib
import sys
import time
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def passthrough(*args, **kwargs):
    def decorate(fn):
        fn.command = passthrough
        fn.group = passthrough
        return fn
    return decorate


class FakeValue:
    def __init__(self, container, name):
        self.container = container
        self.name = name

    async def __call__(self):
        return copy.deepcopy(self.container[self.name])

    async def set(self, value):
        self.container[self.name] = copy.deepcopy(value)


class FakeConfigGroup:
    def __init__(self, data):
        self.data = data

    def __getattr__(self, name):
        return FakeValue(self.data, name)

    async def clear(self):
        self.data.clear()


class FakeConfig:
    def __init__(self):
        self.member_defaults = {}
        self.guild_defaults = {}
        self.members = {}
        self.guilds = {}

    @staticmethod
    def get_conf(cog, identifier, force_registration):
        return FakeConfig()

    def register_member(self, **kwargs):
        self.member_defaults = kwargs

    def register_guild(self, **kwargs):
        self.guild_defaults = kwargs

    def member(self, member):
        return self.member_from_ids(member.guild.id, member.id)

    def member_from_ids(self, guild_id, user_id):
        key = (guild_id, user_id)
        return FakeConfigGroup(self.members.setdefault(key, copy.deepcopy(self.member_defaults)))

    def guild(self, guild):
        return FakeConfigGroup(self.guilds.setdefault(guild.id, copy.deepcopy(self.guild_defaults)))

    async def all_members(self):
        result = {}
        for (guild_id, user_id), data in self.members.items():
            result.setdefault(guild_id, {})[user_id] = copy.deepcopy(data)
        return result


class FakeGuild:
    def __init__(self, id):
        self.id = id


class FakeMember:
    def __init__(self, guild, id):
        self.id = id
        self.guild = guild
        self.bot = False
        self.display_name = "Frog"


class FakeContext:
    def __init__(self, member):
        self.guild = member.guild
        self.author = member
        self.messages = []

    async def send(self, text, **kwargs):
        self.messages.append(text)


class FakeReserve:
    def __init__(self):
        self.config = FakeConfig()
        self.config.register_guild(enabled=True)
        self.lock = asyncio.Lock()
        self.logs = []

    def _lock(self, guild):
        return self.lock

    async def _log(self, guild, reason, user_id, value):
        self.logs.append((guild.id, reason, user_id, value))


class FakeBank:
    BalanceTooHigh = type("BalanceTooHigh", (Exception,), {})

    def __init__(self):
        self.balance = {}
        self.limit = 1000000

    async def is_global(self):
        return False

    async def get_balance(self, member):
        return self.balance.get((member.guild.id, member.id), 0)

    async def get_max_balance(self, guild):
        return self.limit

    async def deposit_credits(self, member, value):
        key = (member.guild.id, member.id)
        next_balance = self.balance.get(key, 0) + value
        if next_balance > self.limit:
            raise self.BalanceTooHigh()
        self.balance[key] = next_balance

    async def withdraw_credits(self, member, value):
        key = (member.guild.id, member.id)
        self.balance[key] = self.balance.get(key, 0) - value


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank = FakeBank()
        discord = types.ModuleType("discord")
        discord.Member = FakeMember
        discord.AllowedMentions = type("AllowedMentions", (), {"none": staticmethod(lambda: None)})
        discord.utils = types.SimpleNamespace(escape_markdown=lambda value: value)
        core = types.ModuleType("redbot.core")
        core.Config = FakeConfig
        core.bank = cls.bank
        core.commands = types.SimpleNamespace(Cog=object, group=passthrough,
                                               guild_only=passthrough,
                                               admin_or_permissions=passthrough)
        errors = types.ModuleType("redbot.core.errors")
        errors.BalanceTooHigh = cls.bank.BalanceTooHigh
        redbot = types.ModuleType("redbot")
        redbot.core = core
        cls._patch_modules = mock.patch.dict(sys.modules, {
            "discord": discord, "redbot": redbot, "redbot.core": core,
            "redbot.core.errors": errors
        })
        cls._patch_modules.start()
        sys.path.insert(0, str(ROOT))
        cls.implementation = importlib.import_module("dig.dig")

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop("dig.dig", None)
        sys.modules.pop("dig.loot", None)
        sys.modules.pop("dig", None)
        sys.path.remove(str(ROOT))
        cls._patch_modules.stop()

    async def asyncSetUp(self):
        self.guild = FakeGuild(25)
        self.member = FakeMember(self.guild, 10)
        self.ctx = FakeContext(self.member)
        self.reserve = FakeReserve()
        self.bot = types.SimpleNamespace(get_cog=lambda name: self.reserve if name == "Ribbit" else None)
        self.cog = self.implementation.Dig(self.bot)
        self.bank.balance.clear()
        self.bank.limit = 1000000

    async def test_exact_three_digs_and_persistent_cooldown(self):
        for _ in range(3):
            await self.cog.dig(self.ctx)
        state = await self.cog.config.member(self.member).state()
        self.assertEqual(state["total_digs"], 3)
        self.assertEqual(state["uses"], 3)
        self.assertGreater(state["cooldown_until"], time.time() + 590)
        await self.cog.dig(self.ctx)
        self.assertEqual((await self.cog.config.member(self.member).state())["total_digs"], 3)
        state["cooldown_until"] = time.time() - 1
        await self.cog.config.member(self.member).state.set(state)
        await self.cog.dig(self.ctx)
        state = await self.cog.config.member(self.member).state()
        self.assertEqual(state["uses"], 1)
        self.assertEqual(state["total_digs"], 4)

    async def test_rapid_parallel_digs_cannot_bypass_limit(self):
        await asyncio.gather(*(self.cog.dig(self.ctx) for _ in range(12)))
        state = await self.cog.config.member(self.member).state()
        self.assertEqual(state["total_digs"], 3)

    async def test_sell_credits_ribbit_and_keeps_bait(self):
        state = await self.cog.config.member(self.member).state()
        state["inventory"] = {"gold_ore": 2, "diamond": 1, "earthworm": 7, "golden_worm": 1}
        await self.cog.config.member(self.member).state.set(state)
        await self.cog.sell(self.ctx, "all")
        state = await self.cog.config.member(self.member).state()
        self.assertEqual(state["inventory"], {"earthworm": 7, "golden_worm": 1})
        self.assertEqual(await self.bank.get_balance(self.member), 270)
        self.assertEqual(state["ribbucks_earned"], 270)
        self.assertEqual(len(self.reserve.logs), 1)

    async def test_full_bank_does_not_consume_loot(self):
        state = await self.cog.config.member(self.member).state()
        state["inventory"]["diamond"] = 1
        await self.cog.config.member(self.member).state.set(state)
        self.bank.limit = 100
        await self.cog.sell(self.ctx, "diamond")
        state = await self.cog.config.member(self.member).state()
        self.assertEqual(state["inventory"], {"diamond": 1})
        self.assertEqual(await self.bank.get_balance(self.member), 0)

    async def test_consume_bait_atomic(self):
        state = await self.cog.config.member(self.member).state()
        state["inventory"]["golden_worm"] = 2
        await self.cog.config.member(self.member).state.set(state)
        results = await asyncio.gather(*(self.cog.consume_bait(self.member, "golden_worm") for _ in range(10)))
        self.assertEqual(sum(results), 2)
        self.assertEqual(await self.cog.get_bait_count(self.member, "golden_worm"), 0)

    async def test_privacy_deletion(self):
        await self.cog.dig(self.ctx)
        await self.cog.red_delete_data_for_user(requester="discord_deleted_user", user_id=self.member.id)
        state_group = self.cog.config.member(self.member)
        self.assertEqual(state_group.data, {})


if __name__ == "__main__":
    unittest.main()
