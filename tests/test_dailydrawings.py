"""Schedule, submission, voting and recovery tests with real Red JSON storage."""

import asyncio
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import discord
from redbot.core import Config
from redbot.core._drivers.json import JsonDriver
from dailydrawings import dailydrawings as D
from dailydrawings.topics import TOPICS

FIXED = datetime(2026, 10, 14, 0, 0, tzinfo=D.UTC)  # 8 PM Eastern, Oct 13.


class ScheduleTests(unittest.TestCase):
    def settings(self, **kwargs):
        return dict(deepcopy(D.DEFAULTS), enabled=True, channel_id=30, **kwargs)

    def test_default_is_eight_pm_eastern(self):
        self.assertEqual(D.scheduled_at(date(2026, 10, 13), self.settings()), FIXED)

    def test_schedule_tracks_daylight_saving(self):
        settings = self.settings()
        self.assertEqual(D.scheduled_at(date(2026, 1, 15), settings).hour, 1)
        self.assertEqual(D.scheduled_at(date(2026, 7, 15), settings).hour, 0)

    def test_one_hour_catchup_window(self):
        settings = self.settings()
        self.assertFalse(D.is_due(settings, FIXED - timedelta(seconds=1)))
        self.assertTrue(D.is_due(settings, FIXED))
        self.assertTrue(D.is_due(settings, FIXED + timedelta(seconds=3599)))
        self.assertFalse(D.is_due(settings, FIXED + timedelta(hours=1)))

    def test_already_run_local_date_blocks_duplicate(self):
        settings = self.settings(last_run_date="2026-10-13")
        self.assertFalse(D.is_due(settings, FIXED))
        self.assertTrue(D.is_due(settings, FIXED + timedelta(days=1)))

    def test_active_or_paused_schedule_cannot_start(self):
        settings = self.settings(active={"phase": "drawing"})
        self.assertFalse(D.is_due(settings, FIXED))
        settings = self.settings()
        settings["enabled"] = False
        self.assertFalse(D.is_due(settings, FIXED))

    def test_next_run_uses_next_local_day_after_manual_start(self):
        settings = self.settings(last_run_date="2026-10-13")
        self.assertEqual(D.next_start(settings, FIXED - timedelta(hours=3)), FIXED + timedelta(days=1))

    def test_next_run_during_catchup_is_now(self):
        now = FIXED + timedelta(minutes=20)
        self.assertEqual(D.next_start(self.settings(), now), now)

    def test_topic_deck_has_six_genres_and_no_repeats(self):
        self.assertEqual(len(TOPICS), 120)
        self.assertEqual({category for category, _ in TOPICS},
                         {"fantasy", "reality", "funny", "serious", "scary", "nature"})
        settings = deepcopy(D.DEFAULTS)
        drawn = [D.pick_topic(settings)[1] for _ in range(120)]
        self.assertEqual(len(set(drawn)), 120)
        self.assertFalse(settings["remaining_topics"])
        self.assertNotEqual(D.pick_topic(settings)[1], drawn[-1])

    def test_image_file_policy(self):
        for filename, content_type in [("drawing.JPG", "image/jpeg"), ("drawing.png", "image/png"),
                                       ("drawing.webp", "image/webp"), ("drawing.jpeg", None)]:
            attachment = NS(filename=filename, content_type=content_type)
            self.assertIs(D.image_attachment([attachment]), attachment)
        self.assertIsNone(D.image_attachment([]))
        self.assertIsNone(D.image_attachment([NS(filename="drawing.gif", content_type="image/gif")]))
        self.assertIsNone(D.image_attachment([NS(filename="drawing.png", content_type="text/plain")]))
        self.assertIsNone(D.image_attachment([NS(), NS()]))


class DrawingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = TemporaryDirectory()
        self.storage_name = "DailyDrawingsTest" + uuid4().hex
        driver = JsonDriver(self.storage_name, "1", data_path_override=Path(self.directory.name))
        self.config = Config(self.storage_name, "1", driver, force_registration=True)
        self.guild = NS(id=10, me=NS(id=999))
        self.permissions = NS(view_channel=True, send_messages=True, embed_links=True, read_message_history=True)
        self.next_id = 1000
        async def send(**kwargs):
            self.next_id += 1
            return NS(id=self.next_id)
        self.channel = NS(id=30, guild=self.guild, mention="<#30>",
                          permissions_for=Mock(return_value=self.permissions),
                          send=AsyncMock(side_effect=send),
                          get_partial_message=Mock(return_value=NS(edit=AsyncMock())))
        self.bot = Mock()
        self.bot.get_channel.side_effect = lambda channel_id: self.channel if channel_id == 30 else None
        self.bot.get_guild.side_effect = lambda guild_id: self.guild if guild_id == 10 else None
        self.bot.intents = NS(message_content=True)
        self.bot.cog_disabled_in_guild = AsyncMock(return_value=False)
        self.bot.ignored_channel_or_guild = AsyncMock(return_value=True)
        self.bot.allowed_by_whitelist_blacklist = AsyncMock(return_value=True)
        self.bot.wait_until_red_ready = AsyncMock()
        with patch.object(Config, "get_conf", return_value=self.config):
            self.cog = D.DailyDrawings(self.bot)
        self.cog._launch = Mock()
        self.clock = patch.object(D, "now_utc", return_value=FIXED)
        self.clock.start()
        await self.config.guild(self.guild).channel_id.set(30)
        await self.config.guild(self.guild).enabled.set(True)
        self.ctx = NS(guild=self.guild, channel=self.channel, clean_prefix="$", send=AsyncMock())

    async def asyncTearDown(self):
        tasks = []
        for game in list(self.cog.rounds.values()):
            tasks.extend(self.cog._detach(game))
        self.cog.cog_unload()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.clock.stop()
        self.directory.cleanup()

    def attachment(self, attachment_id=55):
        return NS(id=attachment_id, filename="paper.jpg", content_type="image/jpeg",
                  url=f"https://cdn.discordapp.com/attachments/test/{attachment_id}/paper.jpg")

    def message(self, user_id=123, message_id=100, attachments=None):
        return NS(id=message_id, guild=self.guild, channel=self.channel,
                  author=NS(id=user_id, bot=False),
                  attachments=[self.attachment()] if attachments is None else attachments,
                  reply=AsyncMock(), delete=AsyncMock())

    def interaction(self, user_id=900):
        interaction = Mock(spec=discord.Interaction)
        interaction.guild = self.guild
        interaction.channel_id = self.channel.id
        interaction.user = NS(id=user_id, bot=False)
        interaction.response = NS(defer=AsyncMock())
        interaction.followup = NS(send=AsyncMock())
        return interaction

    async def game(self, artists=3):
        game = D.DrawingRound(10, 30, uuid4().hex, "fantasy", "A frog knight",
                              FIXED.timestamp() + D.DRAW_SECONDS, phase="drawing")
        for user_id in range(1, artists + 1):
            game.entries[user_id] = dict(message_id=100 + user_id, attachment_id=50 + user_id,
                                        image_url=self.attachment(50 + user_id).url)
        self.cog.rounds[10] = game
        await self.config.guild(self.guild).active.set(game.data())
        return game

    async def test_start_announces_rules_and_fifteen_minute_deadline(self):
        self.assertIsNone(await self.cog._start_round(self.guild))
        game = self.cog.rounds[10]
        self.assertEqual(game.draw_deadline - FIXED.timestamp(), 900)
        self.assertEqual(game.phase, "drawing")
        description = self.channel.send.call_args.kwargs["embed"].description
        self.assertIn("No digital drawing, AI", description)
        self.assertIn("3 or more artists", description)
        self.assertEqual((await self.config.guild(self.guild).all())["last_run_date"], "2026-10-13")

    async def test_duplicate_start_blocked_even_after_round_ends(self):
        await self.cog._start_round(self.guild)
        game = self.cog.rounds[10]
        self.assertIn("already running", await self.cog._start_round(self.guild))
        await self.cog._end(game)
        self.assertIn("already been announced", await self.cog._start_round(self.guild))
        self.assertEqual(self.channel.send.await_count, 1)

    async def test_missing_permission_or_intent_prevents_start(self):
        self.permissions.embed_links = False
        self.assertIn("embed_links", await self.cog._start_round(self.guild))
        self.permissions.embed_links = True
        self.bot.intents.message_content = False
        self.assertIn("Message Content Intent", await self.cog._start_round(self.guild))
        self.assertFalse(self.cog.rounds)
        self.channel.send.assert_not_awaited()

    async def test_photo_submissions_replace_and_do_not_delete_originals(self):
        game = await self.game(0)
        original, replacement = self.message(), self.message(message_id=101)
        await self.cog.on_message(original)
        await self.cog.on_message(replacement)
        self.assertEqual(len(game.entries), 1)
        self.assertEqual(game.entries[123]["message_id"], 101)
        self.assertIn("replaced", replacement.reply.call_args.args[0])
        original.delete.assert_not_awaited()
        self.assertEqual(len((await self.config.guild(self.guild).active())["entries"]), 1)

    async def test_invalid_images_get_feedback_and_late_images_do_not_enter(self):
        game = await self.game(0)
        bad = self.message(attachments=[NS(filename="test.gif", content_type="image/gif")])
        await self.cog.on_message(bad)
        self.assertIn("PNG, JPG or WebP", bad.reply.call_args.args[0])
        game.draw_deadline = FIXED.timestamp()
        await self.cog.on_message(self.message())
        self.assertFalse(game.entries)

    async def test_bot_or_ignored_channel_cannot_submit(self):
        game = await self.game(0)
        message = self.message()
        message.author.bot = True
        await self.cog.on_message(message)
        self.bot.ignored_channel_or_guild.return_value = False
        await self.cog.on_message(self.message())
        self.assertFalse(game.entries)

    async def test_less_than_three_distinct_artists_skips_vote(self):
        game = await self.game(2)
        await self.cog._open_voting(game)
        self.assertFalse(self.cog.rounds)
        self.assertFalse(await self.config.guild(self.guild).active())
        self.assertIn("at least 3", self.channel.send.call_args.kwargs["content"])

    async def test_three_artists_get_persistent_buttons_and_five_minutes(self):
        game = await self.game()
        await self.cog._open_voting(game)
        self.assertEqual(game.phase, "voting")
        self.assertEqual(len(game.ballots), 3)
        self.assertEqual(game.vote_deadline - FIXED.timestamp(), 300)
        for view in game.views.values():
            self.assertTrue(view.is_persistent())
        self.assertEqual((await self.config.guild(self.guild).active())["phase"], "voting")

    async def test_vote_changes_replace_instead_of_accumulating(self):
        game = await self.game()
        await self.cog._open_voting(game)
        interaction = self.interaction()
        self.assertIn("recorded", await self.cog.cast_vote(interaction, game.token, 1))
        self.assertIn("changed", await self.cog.cast_vote(interaction, game.token, 2))
        self.assertEqual(game.votes, {900: 2})
        self.assertEqual((await self.config.guild(self.guild).active())["votes"], {"900": 2})

    async def test_self_late_stale_and_blocked_votes_rejected(self):
        game = await self.game()
        await self.cog._open_voting(game)
        self.assertIn("own drawing", await self.cog.cast_vote(self.interaction(1), game.token, 1))
        self.assertIn("ended", await self.cog.cast_vote(self.interaction(), "old-token", 1))
        self.bot.allowed_by_whitelist_blacklist.return_value = False
        self.assertIn("cannot vote", await self.cog.cast_vote(self.interaction(), game.token, 1))
        self.bot.allowed_by_whitelist_blacklist.return_value = True
        game.vote_deadline = FIXED.timestamp()
        self.assertIn("closed", await self.cog.cast_vote(self.interaction(), game.token, 1))
        self.assertFalse(game.votes)

    async def test_vote_button_gives_private_feedback(self):
        game = await self.game()
        await self.cog._open_voting(game)
        interaction = self.interaction()
        await next(iter(game.views.values())).vote(interaction)
        interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
        self.assertTrue(interaction.followup.send.call_args.kwargs["ephemeral"])

    async def test_most_votes_wins_and_round_state_is_cleared(self):
        game = await self.game()
        await self.cog._open_voting(game)
        game.votes = {900: 1, 901: 1, 902: 2}
        await self.cog._finish_voting(game)
        embed = self.channel.send.call_args.kwargs["embed"]
        self.assertIn("<@1>", embed.description)
        self.assertNotIn("<@2>", embed.description)
        self.assertIn("2 votes", embed.description)
        self.assertFalse(self.cog.rounds)
        self.assertFalse(await self.config.guild(self.guild).active())
        self.assertTrue(all(view.is_finished() for view in game.views.values()))

    async def test_ties_share_cheers_and_no_votes_choose_no_winner(self):
        game = await self.game()
        await self.cog._open_voting(game)
        game.votes = {900: 1, 901: 2}
        await self.cog._finish_voting(game)
        embed = self.channel.send.call_args.kwargs["embed"]
        self.assertIn("joint winners", embed.title)
        self.assertIn("<@1>", embed.description)
        self.assertIn("<@2>", embed.description)
        game = await self.game()
        await self.cog._open_voting(game)
        await self.cog._finish_voting(game)
        self.assertIn("No votes", self.channel.send.call_args.kwargs["content"])

    async def test_removed_entry_clears_its_votes_and_can_cancel_small_ballot(self):
        game = await self.game(4)
        await self.cog._open_voting(game)
        game.votes = {900: 1, 901: 2}
        await self.cog._remove_entry(game, 1)
        self.assertEqual(game.votes, {901: 2})
        self.assertEqual(len(game.entries), 3)
        await self.cog._remove_entry(game, 2)
        self.assertFalse(self.cog.rounds)

    async def test_deleted_or_edited_away_source_image_is_removed(self):
        game = await self.game()
        await self.cog.on_raw_message_delete(NS(guild_id=10, channel_id=30, message_id=101))
        self.assertNotIn(1, game.entries)
        await self.cog.on_raw_message_edit(NS(guild_id=10, channel_id=30, message_id=102,
                                              data={"attachments": []}))
        self.assertNotIn(2, game.entries)

    async def test_bulk_delete_removes_entries_and_gallery_delete_cancels(self):
        game = await self.game()
        await self.cog.on_raw_bulk_message_delete(NS(guild_id=10, channel_id=30, message_ids={101, 102}))
        self.assertEqual(set(game.entries), {3})
        game = await self.game()
        await self.cog._open_voting(game)
        await self.cog.on_raw_message_delete(NS(guild_id=10, channel_id=30,
                                                message_id=game.ballots[0]["message_id"]))
        self.assertFalse(self.cog.rounds)

    async def test_saved_voting_round_restores_votes_and_buttons(self):
        game = await self.game()
        await self.cog._open_voting(game)
        await self.cog.cast_vote(self.interaction(), game.token, 1)
        self.cog.cog_unload()
        with patch.object(Config, "get_conf", return_value=self.config):
            restored = D.DailyDrawings(self.bot)
        restored._launch = Mock()
        await restored._restore()
        self.assertEqual(restored.rounds[10].votes, {900: 1})
        self.assertEqual(self.bot.add_view.call_count, 3)
        restored.cog_unload()

    async def test_drawing_deadline_survives_storage_and_reload(self):
        game = await self.game()
        self.cog._detach(game)
        await self.cog._restore()
        self.assertEqual(self.cog.rounds[10].draw_deadline, FIXED.timestamp() + 900)
        self.assertEqual(len(self.cog.rounds[10].entries), 3)

    async def test_restore_does_not_recreate_state_deleted_after_initial_inventory(self):
        game = await self.game()
        self.cog._detach(game)
        original_inventory = self.config.all_guilds
        async def inventory_then_delete():
            snapshot = await original_inventory()
            await self.config.guild(self.guild).active.set({})
            return snapshot
        with patch.object(self.config, "all_guilds", side_effect=inventory_then_delete):
            await self.cog._restore()
        self.assertFalse(self.cog.rounds)

    async def test_recovery_loads_active_round_from_actual_disk(self):
        game = await self.game()
        await self.cog._open_voting(game)
        await self.cog.cast_vote(self.interaction(), game.token, 1)
        self.cog._detach(game)
        restored_name = self.storage_name + "Restart"
        driver = JsonDriver(restored_name, "1", data_path_override=Path(self.directory.name))
        config = Config(restored_name, "1", driver, force_registration=True)
        with patch.object(Config, "get_conf", return_value=config):
            restored = D.DailyDrawings(self.bot)
        restored._launch = Mock()
        await restored._restore()
        loaded = restored.rounds[10]
        self.assertEqual(loaded.token, game.token)
        self.assertEqual(loaded.votes, {900: 1})
        self.assertEqual(len(loaded.entries), 3)
        restored.cog_unload()

    async def test_drawing_expired_overnight_does_not_open_morning_vote(self):
        game = await self.game()
        game.draw_deadline = FIXED.timestamp() - 3600
        await self.cog._save(game)
        self.cog._detach(game)
        await self.cog._restore()
        self.assertFalse(self.cog.rounds)
        self.assertIn("expired", self.channel.send.call_args.kwargs["content"])

    async def test_disabled_cog_cancels_quiet_round_and_saved_state(self):
        game = await self.game()
        self.bot.cog_disabled_in_guild.return_value = True
        await self.cog._watch(game)
        self.assertFalse(self.cog.rounds)
        self.assertFalse(await self.config.guild(self.guild).active())

    async def test_user_data_deletion_cancels_entrant_and_voter_rounds(self):
        game = await self.game()
        await self.cog._open_voting(game)
        await self.cog.cast_vote(self.interaction(), game.token, 1)
        await self.cog.red_delete_data_for_user(requester="user", user_id=900)
        self.assertFalse(self.cog.rounds)
        self.assertFalse(await self.config.guild(self.guild).active())
        game = await self.game()
        await self.cog.red_delete_data_for_user(requester="user", user_id=1)
        self.assertFalse(self.cog.rounds)

    async def test_user_deletion_clears_rounds_not_yet_restored(self):
        game = await self.game()
        self.cog._detach(game)
        await self.config.guild_from_id(11).active.set(game.data())
        await self.cog.red_delete_data_for_user(requester="user", user_id=1)
        self.assertFalse(await self.config.guild_from_id(10).active())
        self.assertFalse(await self.config.guild_from_id(11).active())

    async def test_data_deletion_during_vote_write_cannot_restore_user_ids(self):
        game = await self.game()
        await self.cog._open_voting(game)
        started, release = asyncio.Event(), asyncio.Event()
        original_save = self.cog._save
        async def blocked_save(round_state):
            started.set()
            await release.wait()
            await original_save(round_state)
        with patch.object(self.cog, "_save", side_effect=blocked_save):
            vote = asyncio.create_task(self.cog.cast_vote(self.interaction(), game.token, 1))
            await started.wait()
            deletion = asyncio.create_task(self.cog.red_delete_data_for_user(requester="user", user_id=900))
            await asyncio.sleep(0)
            self.assertFalse(deletion.done())
            release.set()
            await asyncio.gather(vote, deletion)
        self.assertFalse(await self.config.guild(self.guild).active())
        self.assertFalse(self.cog.rounds)

    async def test_daily_time_changes_without_resetting_daily_marker(self):
        await self.config.guild(self.guild).last_run_date.set("2026-10-13")
        await D.DailyDrawings.draw_time.callback(self.cog, self.ctx, "21:00", "America/New_York")
        settings = await self.config.guild(self.guild).all()
        self.assertEqual(settings["time"], "21:00")
        self.assertEqual(settings["last_run_date"], "2026-10-13")
        await D.DailyDrawings.draw_time.callback(self.cog, self.ctx, "25:00")
        self.assertEqual(await self.config.guild(self.guild).time(), "21:00")

    async def test_scheduler_rechecks_time_changed_after_initial_due_check(self):
        self.assertTrue(D.is_due(await self.config.guild(self.guild).all(), FIXED))
        await D.DailyDrawings.draw_time.callback(self.cog, self.ctx, "21:00")
        self.assertIn("not due", await self.cog._start_round(self.guild, scheduled=True))
        self.channel.send.assert_not_awaited()
        self.assertFalse(self.cog.rounds)

    async def test_draw_default_command_shows_status(self):
        await D.DailyDrawings.draw.callback(self.cog, self.ctx)
        self.assertIn("20:00 America/New_York", self.ctx.send.call_args.args[0])

    async def test_scheduler_announces_once_and_exits_cleanly_on_unload(self):
        with patch.object(D.asyncio, "sleep", side_effect=asyncio.CancelledError):
            await self.cog._scheduler()
        self.assertEqual(self.channel.send.await_count, 1)
        self.assertEqual((await self.config.guild(self.guild).all())["last_run_date"], "2026-10-13")

    async def test_end_to_end_drawing_then_vote_then_results(self):
        game = await self.game()
        current = [FIXED]
        async def advance(seconds):
            current[0] += timedelta(seconds=seconds)
        original_send = self.channel.send.side_effect
        async def vote_when_open(**kwargs):
            message = await original_send(**kwargs)
            if "Voting is open" in kwargs.get("content", ""):
                await self.cog.cast_vote(self.interaction(), game.token, 1)
            return message
        self.channel.send.side_effect = vote_when_open
        with patch.object(D, "now_utc", side_effect=lambda: current[0]), patch.object(D.asyncio, "sleep", side_effect=advance):
            await self.cog._run(game)
        self.assertEqual((current[0] - FIXED).total_seconds(), 20 * 60)
        self.assertFalse(self.cog.rounds)
        self.assertIn("<@1>", self.channel.send.call_args.kwargs["embed"].description)

    async def test_many_tied_winners_fit_in_discord_embeds(self):
        game = await self.game(101)
        game.phase = "voting"
        game.votes = {1000 + user_id: user_id for user_id in game.entries}
        await self.cog._finish_voting(game)
        self.assertEqual(self.channel.send.await_count, 2)
        for call in self.channel.send.call_args_list:
            self.assertLessEqual(len(call.kwargs["embed"].description), 4096)


if __name__ == "__main__":
    unittest.main()
