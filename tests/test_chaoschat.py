"""Offline smoke tests with lightweight fake Discord/Redbot objects."""
import importlib
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# This repository doesn't need Redbot installed to run its basic logic tests.
discord = types.ModuleType("discord")

class Message:
    pass

class Thread:
    pass

class TextChannel:
    pass

class AllowedMentions:
    @staticmethod
    def none():
        return "no-pings"

class Forbidden(Exception):
    pass

class HTTPException(Exception):
    pass

discord.Message = Message
discord.Thread = Thread
discord.TextChannel = TextChannel
discord.AllowedMentions = AllowedMentions
discord.Forbidden = Forbidden
discord.HTTPException = HTTPException
sys.modules["discord"] = discord

redbot = types.ModuleType("redbot")
core = types.ModuleType("redbot.core")

class Cog:
    @classmethod
    def listener(cls, *args, **kwargs):
        return lambda func: func

class Context:
    pass


def decorator(*args, **kwargs):
    return lambda fn: fn


def group(*args, **kwargs):
    def wrap(fn):
        fn.command = decorator
        fn.group = group
        return fn
    return wrap

commands = types.SimpleNamespace(
    Cog=Cog, Context=Context, group=group, guild_only=decorator,
    admin_or_permissions=decorator,
)

class Field:
    def __init__(self, store, name):
        self.store = store
        self.name = name

    async def __call__(self):
        return self.store[self.name]

    async def set(self, value):
        self.store[self.name] = value

class GuildConfig:
    def __init__(self, store):
        self.store = store

    async def all(self):
        return dict(self.store)

    def __getattr__(self, name):
        return Field(self.store, name)

class FakeConfig:
    def __init__(self):
        self.defaults = {}
        self.guild_data = {}

    @classmethod
    def get_conf(cls, *args, **kwargs):
        return cls()

    def register_guild(self, **defaults):
        self.defaults = defaults

    def guild(self, guild):
        store = self.guild_data.setdefault(guild.id, dict(self.defaults))
        return GuildConfig(store)

core.Config = FakeConfig
core.commands = commands
redbot.core = core
sys.modules["redbot"] = redbot
sys.modules["redbot.core"] = core

from chaoschat.chaoschat import ChaosChat
from chaoschat.responses import generate_response, TAME, WILD, FERAL, QUESTIONS, SLAVIC, LANGUAGE_ALIASES


class FakeGuild:
    def __init__(self, gid=1):
        self.id = gid
        self.name = "Test Guild"
        self.me = types.SimpleNamespace(id=99)

class FakeChannel:
    def __init__(self, cid=10):
        self.id = cid

    def permissions_for(self, member):
        return types.SimpleNamespace(view_channel=True, send_messages=True,
                                     send_messages_in_threads=True)

class FakeMessage(Message):
    def __init__(self, content, uid=3, guild=None, channel=None, mentions=None, ref=None):
        self.content = content
        self.guild = guild or FakeGuild()
        self.channel = channel or FakeChannel()
        self.author = types.SimpleNamespace(id=uid, bot=False)
        self.webhook_id = None
        self.mentions = mentions or []
        self.reference = ref
        self.reply = AsyncMock()

class FakeBot:
    def __init__(self):
        self.user = types.SimpleNamespace(id=99)

    async def cog_disabled_in_guild(self, cog, guild):
        return False

    async def get_context(self, message):
        is_command = message.content.startswith("~")
        is_mention = message.content.startswith("<@99>")
        return types.SimpleNamespace(valid=is_command and message.content.startswith("~ping"),
                                     prefix="~" if is_command else ("<@99>" if is_mention else None))


@pytest.mark.asyncio
async def test_disabled_by_default():
    cog = ChaosChat(FakeBot())
    message = FakeMessage("I saw a duck in the basement")
    await cog.on_message(message)
    message.reply.assert_not_called()


@pytest.mark.asyncio
async def test_spontaneous_one_reply_with_rate_limits():
    cog = ChaosChat(FakeBot())
    guild = FakeGuild()
    await cog.config.guild(guild).enabled.set(True)
    await cog.config.guild(guild).chance.set(100)
    m1 = FakeMessage("The moon has been acting strange", guild=guild)
    m2 = FakeMessage("The sandwich is acting strange too", uid=4, guild=guild)
    await cog.on_message(m1)
    await cog.on_message(m2)
    m1.reply.assert_awaited_once()
    m2.reply.assert_not_called()
    assert await cog.config.guild(guild).reply_count() == 1
    assert m1.reply.await_args.kwargs["mention_author"] is False
    assert m1.reply.await_args.kwargs["allowed_mentions"] == "no-pings"


@pytest.mark.asyncio
async def test_bot_mentions_bypass_random_chance_but_commands_do_not():
    cog = ChaosChat(FakeBot())
    guild = FakeGuild()
    await cog.config.guild(guild).enabled.set(True)
    await cog.config.guild(guild).chance.set(0)
    m1 = FakeMessage("<@99> WHY IS THE FRIDGE CRYING", guild=guild,
                     mentions=[cog.bot.user])
    await cog.on_message(m1)
    m1.reply.assert_awaited_once()
    m2 = FakeMessage("~ping", guild=guild)
    await cog.on_message(m2)
    m2.reply.assert_not_called()
    m3 = FakeMessage("~unknown-command", guild=guild)
    await cog.on_message(m3)
    m3.reply.assert_not_called()


@pytest.mark.asyncio
async def test_channel_blocklist():
    cog = ChaosChat(FakeBot())
    guild = FakeGuild()
    await cog.config.guild(guild).enabled.set(True)
    await cog.config.guild(guild).chance.set(100)
    await cog.config.guild(guild).blocked_channels.set([10])
    m = FakeMessage("I support the vegetable kingdom", guild=guild)
    await cog.on_message(m)
    m.reply.assert_not_called()


@pytest.mark.asyncio
async def test_direct_reply_to_bot():
    cog = ChaosChat(FakeBot())
    guild = FakeGuild()
    await cog.config.guild(guild).enabled.set(True)
    await cog.config.guild(guild).chance.set(0)
    previous = FakeMessage("hello", guild=guild, uid=99)
    m = FakeMessage("Why do you hate Tuesday?", guild=guild,
                    ref=types.SimpleNamespace(resolved=previous))
    await cog.on_message(m)
    m.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_followup_is_max_one(monkeypatch):
    cog = ChaosChat(FakeBot())
    guild = FakeGuild()
    await cog.config.guild(guild).enabled.set(True)
    await cog.config.guild(guild).chance.set(100)
    t = [1000.0]
    monkeypatch.setattr("chaoschat.chaoschat.time.monotonic", lambda: t[0])
    monkeypatch.setattr("chaoschat.chaoschat.random.random", lambda: 0.1)
    first = FakeMessage("Do geese have legal rights?", guild=guild)
    await cog.on_message(first)
    t[0] += 4
    second = FakeMessage("Yes, they do", guild=guild)
    await cog.on_message(second)
    assert second.reply.await_count == 1
    t[0] += 4
    third = FakeMessage("Absolutely", guild=guild)
    await cog.on_message(third)
    third.reply.assert_not_called()
    assert await cog.config.guild(guild).reply_count() == 2


def test_large_offline_line_pool():
    assert len(TAME) >= 25
    assert len(WILD) >= 35
    assert len(FERAL) >= 35
    assert len(QUESTIONS) >= 25
    for mode in ["tame", "wild", "feral"]:
        for prompt in ["why?", "how?", "who?", "When?", "Hello", "no", "abc"]:
            result = generate_response(prompt, mode=mode)
            assert isinstance(result, str)
            assert len(result) < 500
            assert "@everyone" not in result


def test_slavic_languages_and_probability_controls():
    for language, pool in SLAVIC.items():
        assert len(pool) >= 10
        assert generate_response("why?", slavic_chance=100, slavic_language=language) in pool
        assert generate_response("yes", followup=True, slavic_chance=100,
                                 slavic_language=language) in pool
    assert len(SLAVIC) == 5
    for alias, name in LANGUAGE_ALIASES.items():
        assert name == "random" or name in SLAVIC
    for _ in range(150):
        assert generate_response("why?", slavic_chance=0) not in sum(SLAVIC.values(), [])


def test_feral_mode_has_genuinely_adult_lines():
    assert sum(any(swear in line.lower() for swear in ("fuck", "shit", "bastard", "ass"))
               for line in FERAL) >= 15
    assert len(FERAL) >= 50
    assert len(QUESTIONS) >= 30


@pytest.mark.asyncio
async def test_slavic_chance_and_language_commands():
    cog = ChaosChat(FakeBot())
    guild = FakeGuild()
    ctx = types.SimpleNamespace(guild=guild, send=AsyncMock())
    await cog.chaos_slavic(ctx, 100)
    await cog.chaos_language(ctx, "pl")
    settings = await cog.config.guild(guild).all()
    assert settings["slavic_chance"] == 100
    assert settings["slavic_language"] == "polish"
    await cog.chaos_slavic(ctx, -1)
    assert await cog.config.guild(guild).slavic_chance() == 100
    await cog.chaos_language(ctx, "invalid")
    assert await cog.config.guild(guild).slavic_language() == "polish"


@pytest.mark.asyncio
async def test_messages_use_server_slavic_settings():
    cog = ChaosChat(FakeBot())
    guild = FakeGuild()
    await cog.config.guild(guild).enabled.set(True)
    await cog.config.guild(guild).chance.set(100)
    await cog.config.guild(guild).slavic_chance.set(100)
    await cog.config.guild(guild).slavic_language.set("russian")
    msg = FakeMessage("I have seen this suspicious man", guild=guild)
    await cog.on_message(msg)
    msg.reply.assert_awaited_once()
    assert msg.reply.await_args.args[0] in SLAVIC["russian"]
