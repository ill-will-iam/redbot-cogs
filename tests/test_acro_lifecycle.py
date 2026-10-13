"""Regression tests for disabled rounds and user-data deletion races."""

import asyncio
from copy import deepcopy
import importlib.util
import sys
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch

import discord
from redbot.core import Config
import test_adminlog as ADMIN_TEST


SPEC = importlib.util.spec_from_file_location("acro_lifecycle_module", ADMIN_TEST.ROOT / "acrogame/acrogame.py")
ACRO = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ACRO
SPEC.loader.exec_module(ACRO)


class ScoreContext:
    def __init__(self, config, guild_id):
        self.config, self.guild_id = config, guild_id

    async def __aenter__(self):
        self.value = deepcopy(self.config.records[self.guild_id]["scores"])
        return self.value

    async def __aexit__(self, *args):
        if self.config.pause_commit and not self.config.pause_commit.is_set():
            pause = self.config.pause_commit
            self.config.pause_commit = None
            self.config.commit_started.set()
            try:
                await pause.wait()
            finally:
                # Exercise even a write that commits while cancellation unwinds.
                self.config.records[self.guild_id]["scores"] = deepcopy(self.value)
        else:
            self.config.records[self.guild_id]["scores"] = deepcopy(self.value)


class ScoreConfig:
    def __init__(self):
        self.records = {10: {"scores": {"123": {"wins": 1, "points": 10}, "456": {"wins": 2, "points": 20}}}}
        self.pause_commit = None
        self.commit_started = asyncio.Event()
        self.points = AsyncMock(return_value=10)

    def guild(self, guild):
        return self.guild_from_id(guild.id)

    def guild_from_id(self, guild_id):
        return NS(scores=lambda: ScoreContext(self, guild_id), winner_points=self.points,
                  winner_credits=AsyncMock(return_value=0))

    async def all_guilds(self):
        return deepcopy(self.records)


class AcroLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.guild = Mock()
        self.guild.id = 10
        self.member = NS(id=123, display_name="Will")
        self.guild.get_member.return_value = self.member
        self.channel = NS(id=30, send=AsyncMock())
        self.bot = Mock()
        self.bot.user = NS(id=999)
        self.bot.get_guild.return_value = self.guild
        self.bot.get_channel.return_value = self.channel
        self.bot.cog_disabled_in_guild = AsyncMock(return_value=False)
        with patch.object(Config, "get_conf", return_value=Mock()):
            self.cog = ACRO.AcroGame(self.bot)
        self.config = ScoreConfig()
        self.cog.config = self.config
        self.game = ACRO.Round(10, 30, "ABC", ("$",))
        self.cog.rounds[10] = self.game

    def message(self, content="Apple Banana Cherry"):
        return NS(id=100, guild=self.guild, channel=self.channel, content=content,
                  author=NS(id=123, bot=False), webhook_id=None,
                  attachments=[], stickers=[], delete=AsyncMock())

    def ballot(self):
        self.game.phase = "voting"
        self.game.entries = [(123, "Apple Banana Cherry"), (456, "Another Big Cat")]
        self.game.votes = {789: 1}

    async def test_disabled_submission_is_not_deleted(self):
        self.bot.cog_disabled_in_guild.return_value = True
        message = self.message()
        await self.cog.on_message(message)
        message.delete.assert_not_awaited()
        self.assertNotIn(10, self.cog.rounds)
        self.assertEqual(self.game.phase, "cancelled")

    async def test_disabled_vote_is_not_deleted_or_recorded(self):
        self.ballot()
        self.bot.cog_disabled_in_guild.return_value = True
        message = self.message("1")
        await self.cog.on_message(message)
        message.delete.assert_not_awaited()
        self.assertFalse(self.game.votes)

    async def test_disable_while_message_waits_for_round_lock(self):
        await self.game.lock.acquire()
        message = self.message()
        task = asyncio.create_task(self.cog.on_message(message))
        try:
            await asyncio.sleep(0)
            self.bot.cog_disabled_in_guild.return_value = True
        finally:
            self.game.lock.release()
        await task
        message.delete.assert_not_awaited()
        self.assertNotIn(10, self.cog.rounds)

    async def test_watcher_cancels_quiet_round(self):
        self.game.task = asyncio.create_task(asyncio.Event().wait())
        self.bot.cog_disabled_in_guild.return_value = True
        self.game.watcher = asyncio.create_task(self.cog._watch_enabled(self.game))
        await self.game.watcher
        await asyncio.gather(self.game.task, return_exceptions=True)
        self.assertTrue(self.game.task.cancelled())
        self.assertNotIn(10, self.cog.rounds)

    async def test_disabled_timer_cannot_reveal_entries(self):
        self.game.submissions = {123: "Apple Banana Cherry", 456: "Another Big Cat"}
        self.bot.cog_disabled_in_guild.return_value = True
        with patch.object(ACRO.asyncio, "sleep", new=AsyncMock()):
            await self.cog._round_timer(self.game)
        self.channel.send.assert_not_awaited()
        self.assertNotIn(10, self.cog.rounds)

    async def test_delete_author_cancels_ballot_and_removes_scores(self):
        self.ballot()
        await self.cog.red_delete_data_for_user(requester="user_strict", user_id=123)
        self.assertNotIn(10, self.cog.rounds)
        self.assertFalse(self.game.entries)
        self.assertFalse(self.game.votes)
        self.assertNotIn("123", self.config.records[10]["scores"])
        self.assertIn("456", self.config.records[10]["scores"])

    async def test_delete_voter_cancels_affected_round(self):
        self.ballot()
        await self.cog.red_delete_data_for_user(requester="user", user_id=789)
        self.assertNotIn(10, self.cog.rounds)
        self.assertFalse(self.game.votes)

    async def test_unrelated_data_deletion_preserves_round(self):
        self.ballot()
        await self.cog.red_delete_data_for_user(requester="owner", user_id=9999)
        self.assertIs(self.cog.rounds[10], self.game)
        self.assertEqual(len(self.game.entries), 2)

    async def test_scores_removed_from_every_guild(self):
        self.config.records[11] = {"scores": {"123": {"wins": 3, "points": 30}}}
        await self.cog.red_delete_data_for_user(requester="discord_deleted_user", user_id=123)
        self.assertTrue(all("123" not in v["scores"] for v in self.config.records.values()))

    async def test_deletion_during_tally_cannot_recreate_score(self):
        self.ballot()
        self.game.phase = "tallying"
        started, release = asyncio.Event(), asyncio.Event()
        async def points():
            started.set()
            await release.wait()
            return 10
        self.config.points.side_effect = points
        self.game.task = asyncio.create_task(self.cog._finish_round(
            self.guild, self.channel, list(self.game.entries), dict(self.game.votes), self.game
        ))
        await started.wait()
        await self.cog.red_delete_data_for_user(requester="user_strict", user_id=123)
        release.set()
        self.assertTrue(self.game.task.cancelled())
        self.assertNotIn("123", self.config.records[10]["scores"])

    async def test_deletion_during_score_commit_still_finishes_with_no_score(self):
        self.ballot()
        self.game.phase = "tallying"
        self.config.pause_commit = asyncio.Event()
        self.game.task = asyncio.create_task(self.cog._finish_round(
            self.guild, self.channel, list(self.game.entries), dict(self.game.votes), self.game
        ))
        await self.config.commit_started.wait()
        await self.cog.red_delete_data_for_user(requester="user_strict", user_id=123)
        self.assertNotIn("123", self.config.records[10]["scores"])

    async def test_normal_winner_still_receives_points(self):
        self.ballot()
        self.game.phase = "tallying"
        await self.cog._finish_round(self.guild, self.channel, self.game.entries, self.game.votes, self.game)
        self.assertEqual(self.config.records[10]["scores"]["123"], {"wins": 2, "points": 20})
        self.assertIn("Winner:", self.channel.send.call_args.args[0])

    async def test_unload_cancels_timer_and_watcher(self):
        self.game.task = asyncio.create_task(asyncio.Event().wait())
        self.game.watcher = asyncio.create_task(asyncio.Event().wait())
        self.cog.cog_unload()
        await asyncio.gather(self.game.task, self.game.watcher, return_exceptions=True)
        self.assertTrue(self.game.task.cancelled())
        self.assertTrue(self.game.watcher.cancelled())
        self.assertFalse(self.cog.rounds)


if __name__ == "__main__":
    unittest.main()
