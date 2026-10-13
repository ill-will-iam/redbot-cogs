"""Offline regression tests; run with Red-DiscordBot installed."""

import importlib.util
import json
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch

import discord


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("adminlog_module", ROOT / "adminlog/adminlog.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AdminLogTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.channel = Mock(spec=discord.TextChannel)
        self.channel.id, self.channel.mention = 20, "<#20>"
        self.channel.send = AsyncMock()
        self.permissions = NS(view_channel=True, send_messages=True, embed_links=True, attach_files=True)
        self.channel.permissions_for.return_value = self.permissions
        self.guild = Mock()
        self.guild.id, self.guild.me = 10, Mock()
        self.guild.get_channel.side_effect = lambda channel_id: self.channel if channel_id == 20 else None
        self.channel.guild = self.guild
        self.bot = Mock()
        self.bot.user = NS(id=999)
        self.bot.guilds = [self.guild]
        self.bot.get_cog.return_value = None
        self.bot.get_guild.side_effect = lambda guild_id: self.guild if guild_id == 10 else None
        self.bot.cog_disabled_in_guild = AsyncMock(return_value=False)
        self.value = AsyncMock(return_value=20)
        self.value.set = AsyncMock()
        self.config = Mock()
        self.ignored_bots = AsyncMock(return_value=[])
        self.config.guild.return_value = NS(channel_id=self.value, ignored_bot_ids=self.ignored_bots)
        with patch.object(MODULE.Config, "get_conf", return_value=self.config):
            self.cog = MODULE.AdminLog(self.bot)

    def message(self, text="original", author_id=123):
        author = Mock()
        author.id = author_id
        author.__str__ = Mock(return_value="Will")
        return NS(id=100, author=author, content=text, attachments=[], stickers=[])

    def deletion(self, message=None, channel_id=30):
        return NS(guild_id=10, channel_id=channel_id, message_id=100, cached_message=message)

    async def test_loadable_commands_and_metadata(self):
        self.assertEqual(self.cog.adminlog.name, "adminlog")
        self.assertEqual({c.name for c in self.cog.adminlog.commands},
                         {"channel", "status", "test", "off", "ignorebot", "unignorebot"})
        self.assertTrue(self.cog.adminlog.requires.user_perms.manage_guild)
        self.assertIn("end_user_data_statement", json.loads((ROOT / "adminlog/info.json").read_text()))

    async def test_cached_deleted_content_and_author(self):
        await self.cog.on_raw_message_delete(self.deletion(self.message("deleted exact text")))
        kwargs = self.channel.send.call_args.kwargs
        self.assertIn("Will (ID: 123)", kwargs["embed"].description)
        self.assertEqual(kwargs["embed"].fields[0].value, "deleted exact text")
        self.assertEqual(kwargs["allowed_mentions"].to_dict()["parse"], [])

    async def test_uncached_deletion_still_records_ids(self):
        await self.cog.on_raw_message_delete(self.deletion())
        embed = self.channel.send.call_args.kwargs["embed"]
        self.assertIn("Message ID: 100", embed.description)
        self.assertIn("not cached", embed.fields[0].value)

    async def test_log_channel_and_bot_messages_do_not_recurse(self):
        await self.cog.on_raw_message_delete(self.deletion(self.message(), channel_id=20))
        await self.cog.on_raw_message_delete(self.deletion(self.message(author_id=999)))
        self.channel.send.assert_not_awaited()

    async def test_long_content_preserved_and_embed_within_limits(self):
        text = "*_@everyone" * 500
        captured = []
        async def capture(**kwargs):
            captured.append(kwargs["file"].fp.getvalue().decode("utf-8"))
            embed = kwargs["embed"]
            self.assertLessEqual(len(embed), 6000)
            self.assertTrue(all(len(f.value) <= 1024 for f in embed.fields))
        self.channel.send.side_effect = capture
        await self.cog.on_raw_message_delete(self.deletion(self.message(text)))
        self.assertIn(text, captured[0])

    async def test_missing_attach_permission_marks_truncation(self):
        self.permissions.attach_files = False
        await self.cog.on_raw_message_delete(self.deletion(self.message("x" * 2000)))
        kwargs = self.channel.send.call_args.kwargs
        self.assertNotIn("file", kwargs)
        self.assertEqual(kwargs["embed"].fields[-1].name, "Full record unavailable")

    async def test_bulk_delete_includes_cached_and_uncached_records(self):
        payload = NS(guild_id=10, channel_id=30, message_ids={100, 101}, cached_messages=[self.message()])
        await self.cog.on_raw_bulk_message_delete(payload)
        embed = self.channel.send.call_args.kwargs["embed"]
        self.assertIn("Message ID: 100", embed.fields[0].value)
        self.assertIn("Message ID: 101", embed.fields[0].value)

    async def test_edit_has_before_after_and_ignores_embed_updates(self):
        payload = self.deletion(self.message())
        payload.data = {"content": "edited"}
        await self.cog.on_raw_message_edit(payload)
        value = self.channel.send.call_args.kwargs["embed"].fields[0].value
        self.assertIn("BEFORE:\noriginal", value)
        self.assertIn("AFTER:\nedited", value)
        self.channel.send.reset_mock()
        payload.data = {"embeds": []}
        await self.cog.on_raw_message_edit(payload)
        self.channel.send.assert_not_awaited()

    async def test_disabled_unconfigured_and_permission_failure(self):
        self.value.return_value = None
        self.assertFalse(await self.cog.emit(self.guild, "Test", "test"))
        self.value.return_value = 20
        self.bot.cog_disabled_in_guild.return_value = True
        self.assertFalse(await self.cog.emit(self.guild, "Test", "test"))
        self.bot.cog_disabled_in_guild.return_value = False
        self.permissions.embed_links = False
        self.assertFalse(await self.cog.emit(self.guild, "Test", "test"))
        self.channel.send.assert_not_awaited()

    async def test_member_nickname_role_and_timeout_changes(self):
        role = NS(id=50, name="Moderator")
        before = NS(nick=None, roles=[], timed_out_until=None, guild_avatar=None)
        after = Mock()
        after.id, after.guild, after.nick, after.roles = 123, self.guild, "New nick", [role]
        after.timed_out_until, after.guild_avatar = discord.utils.utcnow(), None
        after.__str__ = Mock(return_value="Will")
        await self.cog.on_member_update(before, after)
        desc = self.channel.send.call_args.kwargs["embed"].description
        self.assertIn("Nickname:", desc)
        self.assertIn("Roles added: Moderator (50)", desc)
        self.assertIn("Timeout:", desc)

    async def test_voice_join_leave_and_move(self):
        member = Mock()
        member.id, member.guild = 123, self.guild
        def state(channel):
            return NS(channel=channel, self_mute=False, self_deaf=False, mute=False,
                      deaf=False, self_stream=False, self_video=False, suppress=False)
        first, second = NS(name="Lobby", id=40), NS(name="Chat", id=41)
        for old, new, word in ((None, first, "Joined"), (first, None, "Left"), (first, second, "Moved")):
            await self.cog.on_voice_state_update(member, state(old), state(new))
            self.assertIn(word, self.channel.send.call_args.kwargs["embed"].description)

    async def test_channel_setup_validates_then_saves(self):
        ctx = NS(guild=self.guild, me=self.guild.me, send=AsyncMock())
        await self.cog.set_channel.callback(self.cog, ctx, self.channel)
        self.value.set.assert_awaited_once_with(20)
        self.value.set.reset_mock()
        self.permissions.attach_files = False
        await self.cog.set_channel.callback(self.cog, ctx, self.channel)
        self.value.set.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
