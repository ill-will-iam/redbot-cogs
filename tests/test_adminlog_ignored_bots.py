"""Regression tests for excluding a bot's automatic message cleanup."""

from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, patch

import test_adminlog as BASE


class IgnoreValue:
    def __init__(self, ids):
        self.ids = ids
    def __call__(self):
        return self
    def __await__(self):
        async def read():
            return list(self.ids)
        return read().__await__()
    async def __aenter__(self):
        return self.ids
    async def __aexit__(self, *args):
        pass


class IgnoredBotTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        BASE.AdminLogTests.setUp(self)
        self.ids = [777]
        self.config.guild.return_value.ignored_bot_ids = IgnoreValue(self.ids)

    def message(self, author_id=777):
        return NS(id=100, guild=self.guild, content="cat image", attachments=[], stickers=[],
                  author=NS(id=author_id, bot=True))

    def payload(self, message):
        return NS(guild_id=10, channel_id=30, message_id=100, cached_message=message)

    async def test_cached_catbot_deletion_ignored(self):
        await self.cog.on_raw_message_delete(self.payload(self.message()))
        self.channel.send.assert_not_awaited()

    async def test_uncached_catbot_deletion_ignored_after_observation(self):
        await self.cog.on_message(self.message())
        await self.cog.on_raw_message_delete(self.payload(None))
        self.channel.send.assert_not_awaited()
        self.assertEqual(self.cog._ignored_messages[100], (10, 777))

    async def test_other_bots_and_humans_still_logged(self):
        await self.cog.on_raw_message_delete(self.payload(self.message(778)))
        self.channel.send.assert_awaited_once()
        self.channel.send.reset_mock()
        message = self.message(123)
        message.author.bot = False
        await self.cog.on_raw_message_delete(self.payload(message))
        self.channel.send.assert_awaited_once()

    async def test_edits_ignored(self):
        payload = self.payload(self.message())
        payload.data = {"content": "changed"}
        await self.cog.on_raw_message_edit(payload)
        self.channel.send.assert_not_awaited()

    async def test_mixed_bulk_keeps_other_messages_only(self):
        cat = self.message()
        human = self.message(123)
        human.id, human.content = 101, "human text"
        payload = NS(guild_id=10, channel_id=30, message_ids={100, 101}, cached_messages=[cat, human])
        await self.cog.on_raw_bulk_message_delete(payload)
        embed = self.channel.send.call_args.kwargs["embed"]
        self.assertIn("Deleted messages: 1", embed.description)
        self.assertIn("human text", embed.fields[0].value)
        self.assertNotIn("cat image", embed.fields[0].value)

    async def test_ignore_command_rejects_human_and_accepts_bot(self):
        ctx = NS(guild=self.guild, send=AsyncMock())
        await self.cog.ignore_bot.callback(self.cog, ctx, NS(id=123, bot=False))
        self.assertNotIn(123, self.ids)
        await self.cog.ignore_bot.callback(self.cog, ctx, NS(id=778, bot=True))
        self.assertIn(778, self.ids)

    async def test_unignore_clears_id_markers(self):
        await self.cog.on_message(self.message())
        ctx = NS(guild=self.guild, send=AsyncMock())
        await self.cog.unignore_bot.callback(self.cog, ctx, NS(id=777))
        self.assertNotIn(777, self.ids)
        self.assertFalse(self.cog._ignored_messages)
        await self.cog.on_raw_message_delete(self.payload(self.message()))
        self.channel.send.assert_awaited_once()

    async def test_registry_bounded_and_contains_no_content(self):
        with patch.object(BASE.MODULE, "MAX_IGNORED_MESSAGES", 3):
            for message_id in range(5):
                msg = self.message()
                msg.id = message_id
                await self.cog.on_message(msg)
        self.assertEqual(list(self.cog._ignored_messages), [2, 3, 4])
        self.assertEqual(set(self.cog._ignored_messages.values()), {(10, 777)})

    async def test_unconfigured_server_keeps_no_message_ids(self):
        self.value.return_value = None
        await self.cog.on_message(self.message())
        self.assertFalse(self.cog._ignored_messages)

    async def test_data_removal_clears_bot_setting_and_markers(self):
        await self.cog.on_message(self.message())
        self.config.all_guilds = AsyncMock(return_value={10: {"ignored_bot_ids": [777]}})
        self.config.guild_from_id.return_value = self.config.guild.return_value
        await self.cog.red_delete_data_for_user(requester="discord_deleted_user", user_id=777)
        self.assertFalse(self.ids)
        self.assertFalse(self.cog._ignored_messages)


if __name__ == "__main__":
    unittest.main()
