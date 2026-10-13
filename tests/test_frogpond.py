"""Gameplay and lifecycle tests using real Red commands and fake Discord I/O."""

import asyncio
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from redbot.core import Config
from frogpond.frogpond import FrogPond, PondGame, scramble, vowel_hint
from frogpond.words import WORDS


class Scores:
    def __init__(self, config, guild_id):
        self.config, self.guild_id = config, guild_id

    def __call__(self):
        return self

    def __await__(self):
        async def read():
            return deepcopy(self.config.records[self.guild_id]["scores"])
        return read().__await__()

    async def __aenter__(self):
        self.value = deepcopy(self.config.records[self.guild_id]["scores"])
        return self.value

    async def __aexit__(self, *args):
        if self.config.commit_gate is not None:
            self.config.commit_started.set()
            await self.config.commit_gate.wait()
        if args[0] is None:
            self.config.records[self.guild_id]["scores"] = deepcopy(self.value)


class FakeConfig:
    def __init__(self):
        self.records = {10: {"scores": {}}, 11: {"scores": {}}}
        self.commit_gate = None
        self.commit_started = asyncio.Event()

    def guild(self, guild):
        return self.guild_from_id(guild.id)

    def guild_from_id(self, guild_id):
        return NS(scores=Scores(self, guild_id), seconds=AsyncMock(return_value=25))

    async def all_guilds(self):
        return deepcopy(self.records)


class WordTests(unittest.TestCase):
    def test_all_words_have_valid_nontrivial_scrambles(self):
        self.assertEqual(len(WORDS), 100)
        self.assertEqual(len({word for word, _ in WORDS}), 100)
        for word, clue in WORDS:
            self.assertTrue(word.isascii() and word.isalpha() and word.islower())
            self.assertTrue(clue.strip())
            for _ in range(10):
                scrambled = scramble(word).lower()
                self.assertNotEqual(word, scrambled)
                self.assertEqual(sorted(word), sorted(scrambled))

    def test_bad_random_shuffle_has_bounded_fallback(self):
        with patch("frogpond.frogpond.random.shuffle", return_value=None):
            self.assertEqual(sorted(scramble("frog").lower()), sorted("frog"))
            self.assertNotEqual(scramble("frog").lower(), "frog")

    def test_vowel_hint(self):
        self.assertEqual(vowel_hint("tadpole"), "_ A _ _ O _ E")


class GameTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.guild = NS(id=10)
        self.channel = NS(id=30, guild=self.guild, send=AsyncMock())
        self.author = NS(id=123, bot=False, guild_permissions=NS(manage_guild=False))
        self.bot = Mock()
        self.bot.get_cog.return_value = None
        self.bot.intents = NS(message_content=True)
        self.bot.cog_disabled_in_guild = AsyncMock(return_value=False)
        self.bot.ignored_channel_or_guild = AsyncMock(return_value=True)
        self.bot.allowed_by_whitelist_blacklist = AsyncMock(return_value=True)
        self.bot.is_mod = AsyncMock(return_value=False)
        self.bot.is_owner = AsyncMock(return_value=False)
        with patch.object(Config, "get_conf", return_value=Mock()):
            self.cog = FrogPond(self.bot)
        self.cog.config = FakeConfig()
        self.game = PondGame(self.channel, 456, [("frog", "clue")], 25, golden_round=1)
        self.cog.games[10] = self.game
        self.game.answer = "frog"
        self.game.accepting = True
        self.game.deadline = asyncio.get_running_loop().time() + 25
        self.ctx = NS(guild=self.guild, channel=self.channel, author=self.author,
                      send=AsyncMock(), clean_prefix="$")

    async def asyncTearDown(self):
        tasks = []
        for game in list(self.cog.games.values()):
            tasks.extend(self.cog._cancel(game))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def message(self, content="frog", **overrides):
        values = dict(guild=self.guild, channel=self.channel, author=self.author,
                      content=content, delete=AsyncMock())
        values.update(overrides)
        return NS(**values)

    async def test_exact_guess_scores_without_deleting(self):
        message = self.message("  FrOg  ")
        await self.cog.on_message(message)
        self.assertTrue(await self.cog._award(self.game))
        self.assertEqual(self.cog.config.records[10]["scores"]["123"], {"points": 3, "solved": 1})
        message.delete.assert_not_awaited()

    async def test_only_first_concurrent_correct_guess_wins(self):
        second = self.message(author=NS(id=789, bot=False))
        await asyncio.gather(self.cog.on_message(self.message()), self.cog.on_message(second))
        await self.cog._award(self.game)
        self.assertEqual(len(self.cog.config.records[10]["scores"]), 1)
        self.assertEqual(self.game.hops, 1)

    async def test_unrelated_chat_partial_word_bot_dm_and_wrong_channel_are_ignored(self):
        messages = [self.message("I like frogs"), self.message("frog!"), self.message("fro"),
                    self.message(author=NS(id=789, bot=True)), self.message(guild=None),
                    self.message(channel=NS(id=99))]
        for message in messages:
            await self.cog.on_message(message)
            message.delete.assert_not_awaited()
        self.assertIsNone(self.game.winner_id)

    async def test_hint_stages_and_golden_fly_score(self):
        for elapsed, golden, expected in [(1, False, 3), (14, False, 2), (22, False, 1),
                                         (1, True, 6), (14, True, 4), (22, True, 2)]:
            self.game.winner_id = None
            self.game.accepting = True
            self.game.golden_round = 0 if golden else 1
            self.game.deadline = asyncio.get_running_loop().time() + 25 - elapsed
            await self.cog.on_message(self.message())
            self.assertEqual(self.game.award, expected)

    async def test_expired_guess_cannot_score(self):
        self.game.deadline = asyncio.get_running_loop().time() - 1
        await self.cog.on_message(self.message())
        self.assertIsNone(self.game.winner_id)

    async def test_ignored_channel_and_blocked_player_cannot_score(self):
        self.bot.ignored_channel_or_guild.return_value = False
        await self.cog.on_message(self.message())
        self.assertIsNone(self.game.winner_id)
        self.bot.ignored_channel_or_guild.return_value = True
        self.bot.allowed_by_whitelist_blacklist.return_value = False
        await self.cog.on_message(self.message())
        self.assertIsNone(self.game.winner_id)

    async def test_disabled_cog_cancels_listener_and_quiet_watcher(self):
        self.bot.cog_disabled_in_guild.return_value = True
        await self.cog.on_message(self.message())
        self.assertFalse(self.cog.games)
        self.assertFalse(await self.cog._award(self.game))
        self.game.cancelled = False
        self.cog.games[10] = self.game
        await self.cog._watch(self.game)
        self.assertFalse(self.cog.games)

    async def test_queued_guess_does_not_leak_into_next_round(self):
        started, release = asyncio.Event(), asyncio.Event()
        async def blocked_check(_):
            started.set()
            await release.wait()
            return True
        self.bot.ignored_channel_or_guild.side_effect = blocked_check
        task = asyncio.create_task(self.cog.on_message(self.message()))
        await started.wait()
        self.game.round_index += 1
        release.set()
        await task
        self.assertIsNone(self.game.winner_id)

    async def test_start_rejects_missing_intent_bad_bounds_and_duplicate(self):
        await self.cog._start(self.ctx, 20)
        self.assertIn("3 and 10", self.ctx.send.call_args.args[0])
        self.bot.intents.message_content = False
        await self.cog._start(self.ctx, 5)
        self.assertIn("Message Content", self.ctx.send.call_args.args[0])
        self.bot.intents.message_content = True
        await self.cog._start(self.ctx, 5)
        self.assertIn("already crossing", self.ctx.send.call_args.args[0])

    async def test_start_has_unique_puzzles_and_one_golden_round(self):
        self.cog._cancel(self.game)
        with patch.object(self.cog, "_run", new=AsyncMock()), patch.object(self.cog, "_watch", new=AsyncMock()):
            await self.cog._start(self.ctx, 10)
            game = self.cog.games[10]
            self.assertEqual(len({word for word, _ in game.puzzles}), 10)
            self.assertIn(game.golden_round, range(10))
            self.assertEqual(game.seconds, 25)
            await asyncio.gather(game.task, game.watcher)

    async def test_acro_blocks_start_and_cancels_running_game(self):
        self.bot.get_cog.return_value = NS(rounds={10: NS(channel_id=30)})
        await self.cog._start(self.ctx, 5)
        self.assertIn("AcroGame", self.ctx.send.call_args.args[0])
        await self.cog.on_message(self.message())
        self.assertFalse(self.cog.games)
        self.assertIsNone(self.game.winner_id)

    async def test_stop_requires_starter_or_staff(self):
        await FrogPond.frog_stop.callback(self.cog, self.ctx)
        self.assertTrue(self.cog.games)
        self.ctx.author.id = 456
        await FrogPond.frog_stop.callback(self.cog, self.ctx)
        self.assertFalse(self.cog.games)

    async def test_unload_cancels_both_tasks(self):
        self.game.task = asyncio.create_task(asyncio.Event().wait())
        self.game.watcher = asyncio.create_task(asyncio.Event().wait())
        self.cog.cog_unload()
        await asyncio.gather(self.game.task, self.game.watcher, return_exceptions=True)
        self.assertTrue(self.game.task.cancelled() and self.game.watcher.cancelled())
        self.assertFalse(self.cog.games)

    async def test_data_deletion_cancels_pending_winner_and_removes_all_guild_scores(self):
        await self.cog.on_message(self.message())
        for record in self.cog.config.records.values():
            record["scores"] = {"123": {"points": 9, "solved": 3}, "789": {"points": 2, "solved": 1}}
        await self.cog.red_delete_data_for_user(requester="user", user_id=123)
        self.assertFalse(await self.cog._award(self.game))
        self.assertFalse(self.cog.games)
        for record in self.cog.config.records.values():
            self.assertNotIn("123", record["scores"])
            self.assertIn("789", record["scores"])

    async def test_privacy_request_during_score_write_cannot_recreate_data(self):
        await self.cog.on_message(self.message())
        gate = asyncio.Event()
        self.cog.config.commit_gate = gate
        award = asyncio.create_task(self.cog._award(self.game))
        await self.cog.config.commit_started.wait()
        deletion = asyncio.create_task(self.cog.red_delete_data_for_user(requester="user", user_id=123))
        await asyncio.sleep(0)
        self.assertFalse(deletion.done())
        gate.set()
        await asyncio.gather(award, deletion)
        self.assertNotIn("123", self.cog.config.records[10]["scores"])
        self.assertFalse(self.cog.games)

    async def test_unrelated_privacy_request_keeps_game(self):
        await self.cog.red_delete_data_for_user(requester="owner", user_id=9999)
        self.assertIs(self.cog.games[10], self.game)

    async def test_timeouts_reveal_answers_and_clean_up(self):
        self.game.puzzles = list(WORDS[:3])
        self.game.accepting = False
        with patch.object(self.cog, "_wait_until", new=AsyncMock()), patch("frogpond.frogpond.asyncio.sleep", new=AsyncMock()):
            await self.cog._run(self.game)
        contents = [call.kwargs.get("content", "") for call in self.channel.send.call_args_list]
        self.assertEqual(sum("Splash!" in content for content in contents), 3)
        self.assertEqual(sum("Hint:" in content for content in contents), 6)
        self.assertFalse(self.cog.games)
        self.assertFalse(self.cog.config.records[10]["scores"])

    async def test_successful_crossing_persists_points_and_suppresses_pings(self):
        self.game.puzzles = list(WORDS[:3])
        self.game.golden_round = 1
        async def solve(*_):
            await self.cog.on_message(self.message(self.game.answer))
        with patch.object(self.cog, "_wait_until", side_effect=solve), patch("frogpond.frogpond.asyncio.sleep", new=AsyncMock()):
            await self.cog._run(self.game)
        self.assertEqual(self.cog.config.records[10]["scores"]["123"], {"points": 12, "solved": 3})
        final_embed = self.channel.send.call_args.kwargs["embed"]
        self.assertIn("frog home", final_embed.description)
        for call in self.channel.send.call_args_list:
            self.assertFalse(call.kwargs["allowed_mentions"].users)
        self.assertFalse(self.cog.games)


if __name__ == "__main__":
    unittest.main()
