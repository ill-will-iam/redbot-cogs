"""Offline tests for FATBOY profile formatting and reversible Core info alias."""

import datetime
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock


class FakeCommand:
    def __init__(self, callback=None, name="command", cog_name=None):
        self.callback = callback
        self.name = name
        self.cog_name = cog_name


def command_decorator(*args, **kwargs):
    def make_command(fn):
        return FakeCommand(fn, kwargs.get("name", fn.__name__))
    return make_command


def group_decorator(*args, **kwargs):
    def decorate(fn):
        fn.command = command_decorator
        return fn
    return decorate


class FakeField:
    def __init__(self, config, key):
        self.config = config
        self.key = key

    async def __call__(self):
        return self.config.data[self.key]

    async def set(self, value):
        self.config.data[self.key] = value


class FakeConfig:
    def __init__(self):
        self.data = {}

    @classmethod
    def get_conf(cls, *args, **kwargs):
        return cls()

    def register_global(self, **kwargs):
        self.data.update(kwargs)

    def __getattr__(self, name):
        return FakeField(self, name)


class FakeBot:
    def __init__(self, existing=None):
        self.registered = {"info": existing} if existing else {}
        self.user = types.SimpleNamespace(display_name="Fatboy", id=123)
        self.guilds = []
        self.cogs = {"Core": object(), "Dig": object(), "FatboyInfo": object()}
        self.latency = 0.045
        self.uptime = datetime.datetime(2026, 11, 6, tzinfo=datetime.timezone.utc)

    def get_command(self, name):
        return self.registered.get(name)

    def remove_command(self, name):
        return self.registered.pop(name, None)

    def add_command(self, cmd):
        if cmd.name in self.registered:
            raise ValueError("Command already registered")
        self.registered[cmd.name] = cmd


def load_module():
    discord = types.ModuleType("discord")
    discord.utils = types.SimpleNamespace(
        escape_markdown=lambda value: value,
        escape_mentions=lambda value: value,
        format_dt=lambda value, style: "a short time ago",
    )
    discord.__version__ = "2.x"
    discord.AllowedMentions = types.SimpleNamespace(none=lambda: "no-pings")
    core = types.ModuleType("redbot.core")
    core.Config = FakeConfig
    core.__version__ = "3.x"
    core.commands = types.SimpleNamespace(
        Cog=type("Cog", (), {}),
        command=command_decorator,
        group=group_decorator,
        is_owner=lambda: (lambda fn: fn),
    )
    redbot = types.ModuleType("redbot")
    old = {name: sys.modules.get(name) for name in ("discord", "redbot", "redbot.core")}
    sys.modules.update({"discord": discord, "redbot": redbot, "redbot.core": core})
    try:
        file_path = Path(__file__).resolve().parents[1] / "fatboyinfo" / "fatboyinfo.py"
        spec = importlib.util.spec_from_file_location("_test_fatboyinfo", file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, prior in old.items():
            if prior is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior


module = load_module()
FatboyInfo = module.FatboyInfo


class FatboyInfoTests(unittest.IsolatedAsyncioTestCase):
    async def test_core_info_is_replaced_and_restored(self):
        core_info = FakeCommand(name="info", cog_name="Core")
        bot = FakeBot(core_info)
        cog = FatboyInfo(bot)
        self.assertTrue(await cog.activate_info_alias())
        self.assertIsNot(bot.get_command("info"), core_info)
        self.assertEqual(bot.get_command("info").name, "info")
        self.assertTrue(await cog.activate_info_alias())
        cog.cog_unload()
        self.assertIs(bot.get_command("info"), core_info)

    async def test_never_overwrites_third_party_info(self):
        third_party = FakeCommand(name="info", cog_name="AnotherCog")
        bot = FakeBot(third_party)
        cog = FatboyInfo(bot)
        self.assertFalse(await cog.activate_info_alias())
        self.assertIs(bot.get_command("info"), third_party)
        cog.cog_unload()
        self.assertIs(bot.get_command("info"), third_party)

    async def test_disabled_alias_keeps_core_info(self):
        core_info = FakeCommand(name="info", cog_name="Core")
        bot = FakeBot(core_info)
        cog = FatboyInfo(bot)
        await cog.config.use_info_alias.set(False)
        self.assertFalse(await cog.activate_info_alias())
        self.assertIs(bot.get_command("info"), core_info)

    async def test_text_fallback(self):
        bot = FakeBot()
        cog = FatboyInfo(bot)
        ctx = types.SimpleNamespace(
            embed_requested=AsyncMock(return_value=False),
            send=AsyncMock(),
            clean_prefix="~",
        )
        await cog._send_profile(ctx)
        output = ctx.send.call_args.args[0]
        self.assertIn("Fatboy", output)
        self.assertIn("Will", output)
        self.assertIn("Loaded cogs:", output)
        self.assertIn("Red 3.x", output)

    def test_cog_pages_stay_within_discord_limits(self):
        names = ["CustomCog" + str(i).zfill(3) for i in range(500)]
        pages = module.cog_field_pages(names)
        self.assertLessEqual(len(pages), 4)
        self.assertTrue(all(len(page) <= 1000 for page in pages))
        self.assertIn("more", pages[-1])


if __name__ == "__main__":
    unittest.main()
