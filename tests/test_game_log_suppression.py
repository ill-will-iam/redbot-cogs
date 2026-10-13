"""Integration checks for AcroGame/AdminLog message suppression."""

import importlib.util
import sys
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch

import discord

import test_adminlog as ADMIN_TEST


SPEC = importlib.util.spec_from_file_location("acro_test_module", ADMIN_TEST.ROOT / "acrogame/acrogame.py")
ACRO = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ACRO
SPEC.loader.exec_module(ACRO)


class GameLogSuppressionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        ADMIN_TEST.AdminLogTests.setUp(self)
        with patch.object(ACRO.Config, "get_conf", return_value=Mock()):
            self.game = ACRO.AcroGame(self.bot)
        self.bot.get_cog.return_value = self.game

    def payload(self, message_id=100, channel_id=30, content="ordinary message"):
        author = Mock()
        author.id = 123
        author.__str__ = Mock(return_value="Will")
        message = NS(id=message_id, content=content, author=author, attachments=[], stickers=[])
        return NS(guild_id=10, channel_id=channel_id, message_id=message_id, cached_message=message)

    def start_round(self):
        self.game.rounds[10] = ACRO.Round(10, 30, "ABC", ("$",))

    async def test_active_game_suppresses_delete_edit_and_bulk(self):
        self.start_round()
        payload = self.payload()
        await self.cog.on_raw_message_delete(payload)
        payload.data = {"content": "changed"}
        await self.cog.on_raw_message_edit(payload)
        payload.message_ids, payload.cached_messages = {100}, [payload.cached_message]
        await self.cog.on_raw_bulk_message_delete(payload)
        self.channel.send.assert_not_awaited()

    async def test_other_channels_and_member_events_continue(self):
        self.start_round()
        await self.cog.on_raw_message_delete(self.payload(channel_id=31))
        member = Mock()
        member.guild, member.id, member.created_at = self.guild, 123, discord.utils.utcnow()
        await self.cog.on_member_join(member)
        self.assertEqual(self.channel.send.await_count, 2)

    async def test_normal_general_logging_resumes_after_round(self):
        self.start_round()
        self.game.rounds.pop(10)
        await self.cog.on_raw_message_delete(self.payload())
        self.channel.send.assert_awaited_once()

    async def test_submissions_stay_hidden_even_when_delete_event_is_delayed(self):
        self.start_round()
        payload = self.payload(content="Apple Banana Cherry")
        message = payload.cached_message
        message.guild, message.channel = self.guild, NS(id=30)
        message.author.bot, message.webhook_id = False, None
        message.delete = AsyncMock()
        await self.game.on_message(message)
        message.delete.assert_awaited_once()
        self.assertEqual(self.game.rounds[10].submissions[123], "Apple Banana Cherry")
        self.game.rounds.pop(10)
        await self.cog.on_raw_message_delete(payload)
        self.channel.send.assert_not_awaited()

    async def test_marker_exists_before_delete_request(self):
        payload = self.payload()
        message = payload.cached_message
        async def check_during_delete():
            self.assertTrue(self.game.suppresses_message_log(10, 30, message.id))
            await self.cog.on_raw_message_delete(payload)
        message.delete = AsyncMock(side_effect=check_during_delete)
        await self.game._delete_game_message(message)
        self.channel.send.assert_not_awaited()

    async def test_bulk_after_round_filters_only_game_messages(self):
        hidden, normal = self.payload(content="secret answer"), self.payload(101, content="ordinary")
        hidden.cached_message.delete = AsyncMock()
        await self.game._delete_game_message(hidden.cached_message)
        bulk = NS(guild_id=10, channel_id=30, message_ids={100, 101},
                  cached_messages=[hidden.cached_message, normal.cached_message])
        await self.cog.on_raw_bulk_message_delete(bulk)
        embed = self.channel.send.call_args.kwargs["embed"]
        self.assertIn("Deleted messages: 1", embed.description)
        self.assertIn("ordinary", embed.fields[0].value)
        self.assertNotIn("secret answer", embed.fields[0].value)
        self.assertNotIn("Message ID: 100", embed.fields[0].value)

    async def test_failed_delete_does_not_hide_future_normal_deletion(self):
        message = self.payload().cached_message
        error = discord.HTTPException(NS(status=403, reason="Forbidden"), "failed")
        message.delete = AsyncMock(side_effect=error)
        with self.assertRaises(discord.HTTPException):
            await self.game._delete_game_message(message)
        self.assertFalse(self.game.suppresses_message_log(10, 30, message.id))

    async def test_suppression_registry_is_bounded(self):
        with patch.object(ACRO, "MAX_LOG_SUPPRESSIONS", 3):
            for message_id in range(5):
                message = NS(id=message_id, delete=AsyncMock())
                await self.game._delete_game_message(message)
        self.assertEqual(list(self.game.log_suppressed_messages), [2, 3, 4])

    async def test_older_game_cog_also_pauses_current_round(self):
        self.start_round()
        self.bot.get_cog.return_value = NS(rounds=self.game.rounds)
        await self.cog.on_raw_message_delete(self.payload())
        self.channel.send.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
