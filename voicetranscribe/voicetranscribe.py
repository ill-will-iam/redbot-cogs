"""Auto-transcribe *native* Discord voice notes using local faster-whisper."""

import asyncio
import io
import logging
import tempfile
from pathlib import Path

import discord
from redbot.core import Config, commands

from .utils import (
    CHUNK_SIZE,
    MAX_CHUNKS,
    MAX_PENDING,
    transcript_chunks,
    voice_note_attachment,
)

LOG = logging.getLogger("red.voicetranscribe")


class VoiceTranscribe(commands.Cog):
    """Reply with written text when someone sends a Discord voice message."""

    def __init__(self, bot):
        self.bot = bot
        # New identifier: do not inherit settings from the discarded first version.
        self.config = Config.get_conf(self, identifier=948127611, force_registration=True)
        self.config.register_guild(enabled=False, excluded_channels=[])
        self._jobs = set()
        self._work = asyncio.Semaphore(1)  # Limit CPU load on a shared VPS.
        self._model_lock = asyncio.Lock()
        self._model = None
        self._closing = False

    def cog_unload(self):
        self._closing = True
        for task in tuple(self._jobs):
            task.cancel()

    async def red_delete_data_for_user(self, *, requester, user_id):
        """The cog stores no user-specific configuration or historical audio."""
        return

    async def _get_model(self):
        if self._model is None:
            async with self._model_lock:
                if self._model is None:
                    from faster_whisper import WhisperModel

                    # First use downloads model weights to faster-whisper's local cache.
                    self._model = await asyncio.to_thread(
                        WhisperModel, "base", device="cpu", compute_type="int8", cpu_threads=2, num_workers=1
                    )
        return self._model

    @staticmethod
    def _recognize(model, filename):
        # Consume the generator *inside* the worker thread; transcribe is lazy.
        segments, _ = model.transcribe(
            filename,
            beam_size=3,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    @staticmethod
    def _can_reply(message, member):
        perms = message.channel.permissions_for(member)
        if not (perms.view_channel and perms.read_message_history):
            return False
        if isinstance(message.channel, discord.Thread):
            return perms.send_messages_in_threads
        return perms.send_messages

    @commands.Cog.listener()
    async def on_message(self, message):
        if self._closing or not message.guild or message.author.bot:
            return
        attachment = voice_note_attachment(message)
        if attachment is None:
            return
        conf = self.config.guild(message.guild)
        if not await conf.enabled():
            return
        ignored = await conf.excluded_channels()
        if message.channel.id in ignored or getattr(message.channel, "parent_id", None) in ignored:
            return
        bot_member = message.guild.me
        if bot_member is None or not self._can_reply(message, bot_member):
            return
        if len(self._jobs) >= MAX_PENDING:
            LOG.info("Voice note queue full in guild %s; skipping message %s", message.guild.id, message.id)
            return
        task = asyncio.create_task(self._process(message, attachment))
        self._jobs.add(task)
        task.add_done_callback(self._jobs.discard)

    async def _process(self, message, attachment):
        try:
            async with self._work:
                if self._closing or not await self.config.guild(message.guild).enabled():
                    return
                ignored = await self.config.guild(message.guild).excluded_channels()
                if message.channel.id in ignored or getattr(message.channel, "parent_id", None) in ignored:
                    return
                with tempfile.TemporaryDirectory(prefix="fatboy_voice_", dir=None) as dirname:
                    # Use our own fixed filename, never the user's attachment path.
                    suffix = Path(attachment.filename).suffix.lower()
                    filepath = Path(dirname) / ("note" + suffix)
                    await attachment.save(filepath)
                    model = await self._get_model()
                    words = await asyncio.to_thread(self._recognize, model, str(filepath))
                if not words or self._closing:
                    return
                escaped = discord.utils.escape_markdown(words)
                chunks = transcript_chunks(escaped, CHUNK_SIZE)
                header = "**Voice note transcription:**\n"
                no_mentions = discord.AllowedMentions.none()
                if len(chunks) > MAX_CHUNKS:
                    perms = message.channel.permissions_for(message.guild.me)
                    if perms.attach_files:
                        content = words.encode("utf-8")
                        file = discord.File(io.BytesIO(content), filename="voice-transcript.txt")
                        await message.reply(
                            "**Voice note transcription:** Full text attached.",
                            file=file,
                            mention_author=False,
                            allowed_mentions=no_mentions,
                        )
                        return
                    # Rare fallback when Attach Files is unavailable: preserve all text.
                for idx, chunk in enumerate(chunks):
                    body = (header if idx == 0 else "") + chunk
                    await message.reply(
                        body,
                        mention_author=False,
                        allowed_mentions=no_mentions,
                    )
        except asyncio.CancelledError:
            raise
        except discord.HTTPException:
            LOG.warning("Unable to retrieve or post transcription for voice message %s", message.id)
        except Exception:
            LOG.exception("Failed to transcribe voice message %s", message.id)

    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    @commands.group(name="voicetranscribe", aliases=["vt"], invoke_without_command=True)
    async def vt(self, ctx):
        """Show voice transcription status and settings."""
        conf = self.config.guild(ctx.guild)
        active = await conf.enabled()
        ignored = await conf.excluded_channels()
        await ctx.send(
            ("Voice note transcription: **{}**. Ignored channels: **{}**. "
             "Model: **base** (local CPU). Queue: **{}/{}**.").format(
                "ON" if active else "OFF", len(ignored), len(self._jobs), MAX_PENDING
            )
        )

    @vt.command(name="on")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def vt_on(self, ctx):
        """Enable automatic transcription for this server."""
        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.send("Voice note transcription **enabled** for this server.")

    @vt.command(name="off")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def vt_off(self, ctx):
        """Disable automatic transcription for this server."""
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.send("Voice note transcription **disabled** for this server.")

    @vt.command(name="ignore")
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def vt_ignore(self, ctx, channel: discord.TextChannel = None):
        """Toggle transcription in a channel (defaults to current channel)."""
        channel = channel or ctx.channel
        async with self.config.guild(ctx.guild).excluded_channels() as ignored:
            if channel.id in ignored:
                ignored.remove(channel.id)
                enabled = True
            else:
                ignored.append(channel.id)
                enabled = False
        await ctx.send(
            "Voice transcription **{}** in {}."
            .format("enabled" if enabled else "disabled", channel.mention)
        )
