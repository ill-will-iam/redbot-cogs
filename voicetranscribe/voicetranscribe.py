"""Automatically transcribe and optionally translate native Discord voice notes."""

import asyncio
import io
import logging
import tempfile
from pathlib import Path

import discord
from redbot.core import Config, commands

from .utils import (
    CHUNK_SIZE, MAX_CHUNKS, MAX_PENDING, MODEL_SIZES, SPEED_BEAMS,
    format_transcript, language_label, transcript_chunks, voice_note_attachment,
)

LOG = logging.getLogger("red.voicetranscribe")


class VoiceTranscribe(commands.Cog):
    """Native-language voice-note transcription, with optional English translation."""

    def __init__(self, bot):
        self.bot = bot
        # Preserve previous enabled/ignored settings with the same Config ID.
        self.config = Config.get_conf(self, identifier=948127611, force_registration=True)
        self.config.register_guild(
            enabled=False, excluded_channels=[], translate=True,
            language="auto", vocabulary=[],
        )
        # One model shared by all servers; admins cannot trigger model downloads.
        self.config.register_global(model="base", speed="fast", cpu_threads=2, engine="auto")
        self._jobs = set()
        self._work = asyncio.Semaphore(1)
        self._model_lock = asyncio.Lock()
        self._model = None
        self._model_spec = None
        self._closing = False

    def cog_unload(self):
        # Don't cancel running to_thread jobs while their TemporaryDirectory is in use.
        # Tasks finish silently, and no new notes are accepted after unload.
        self._closing = True

    async def red_delete_data_for_user(self, *, requester, user_id):
        """The cog stores server settings, not user data or voice-note history."""
        return

    async def _get_model(self):
        spec = (await self.config.model(), await self.config.cpu_threads())
        if self._model is not None and self._model_spec == spec:
            return self._model
        async with self._model_lock:
            if self._model is None or self._model_spec != spec:
                from faster_whisper import WhisperModel
                name, threads = spec
                loaded = await asyncio.to_thread(
                    WhisperModel, name, device="cpu", compute_type="int8",
                    cpu_threads=threads, num_workers=1,
                )
                self._model = loaded
                self._model_spec = spec
        return self._model

    @staticmethod
    def _argos_translate(text, language):
        """Use existing offline Argos models if installed, without downloading data."""
        try:
            import argostranslate.translate as argos
        except ImportError:
            return None
        try:
            installed = argos.get_installed_languages()
            source = next((lang for lang in installed if lang.code == language), None)
            target = next((lang for lang in installed if lang.code == "en"), None)
            if source is None or target is None:
                return None
            translation = source.get_translation(target)
            result = translation.translate(text).strip()
            return result or None
        except Exception:
            LOG.debug("Optional Argos translation not available for %s", language, exc_info=True)
            return None

    @staticmethod
    def _recognize(model, filename, language_hint, translate, beam_size, hotwords, engine):
        """Run in a worker thread: audio decode, speech recognition, translation."""
        kwargs = {
            "language": None if language_hint == "auto" else language_hint,
            "beam_size": beam_size,
            "best_of": 1,
            "vad_filter": True,
            "condition_on_previous_text": False,
        }
        if hotwords:
            kwargs["hotwords"] = ", ".join(hotwords)
        segments, info = model.transcribe(filename, task="transcribe", **kwargs)
        original = " ".join(segment.text.strip() for segment in segments).strip()
        detected = info.language or "unknown"
        confidence = getattr(info, "language_probability", None)
        if not original or not translate or detected == "en":
            return original, None, detected, confidence, None

        english = None
        method = None
        if engine == "auto":
            english = VoiceTranscribe._argos_translate(original, detected)
            if english:
                method = "argos"
        if not english:
            # Whisper translation is an additional audio pass, but needs no extra packages.
            # Do not feed hint words to translation: they can bias target-language output.
            translation_kwargs = dict(kwargs)
            translation_kwargs.pop("hotwords", None)
            translation_kwargs["language"] = detected
            segments, _ = model.transcribe(filename, task="translate", **translation_kwargs)
            english = " ".join(segment.text.strip() for segment in segments).strip() or None
            if english:
                method = "whisper"
        return original, english, detected, confidence, method

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
        audio = voice_note_attachment(message)
        if audio is None:
            return
        conf = self.config.guild(message.guild)
        if not await conf.enabled():
            return
        ignored = await conf.excluded_channels()
        if message.channel.id in ignored or getattr(message.channel, "parent_id", None) in ignored:
            return
        member = message.guild.me
        if member is None or not self._can_reply(message, member):
            return
        if len(self._jobs) >= MAX_PENDING:
            LOG.info("Voice transcription queue full, skipping %s", message.id)
            return
        task = asyncio.create_task(self._process(message, audio))
        self._jobs.add(task)
        task.add_done_callback(self._jobs.discard)

    async def _process(self, message, attachment):
        try:
            async with self._work:
                if self._closing:
                    return
                conf = self.config.guild(message.guild)
                if not await conf.enabled():
                    return
                ignored = await conf.excluded_channels()
                if message.channel.id in ignored or getattr(message.channel, "parent_id", None) in ignored:
                    return
                translate, hint, hotwords, speed, engine = await asyncio.gather(
                    conf.translate(), conf.language(), conf.vocabulary(),
                    self.config.speed(), self.config.engine(),
                )
                with tempfile.TemporaryDirectory(prefix="fatboy_voice_") as tmpdir:
                    suffix = Path(attachment.filename).suffix.lower()
                    filename = Path(tmpdir) / ("note" + suffix)
                    await attachment.save(filename)
                    model = await self._get_model()
                    original, english, lang, confidence, method = await asyncio.to_thread(
                        self._recognize, model, str(filename), hint, translate,
                        SPEED_BEAMS.get(speed, 1), hotwords, engine,
                    )
            if not original or self._closing or not await conf.enabled():
                return
            ignored = await conf.excluded_channels()
            if message.channel.id in ignored or getattr(message.channel, "parent_id", None) in ignored:
                return
            await self._reply(message, original, english, lang)
        except asyncio.CancelledError:
            raise
        except discord.HTTPException:
            LOG.warning("Cannot read or reply to voice message %s", message.id)
        except Exception:
            LOG.exception("Voice transcription failed for message %s", message.id)

    async def _reply(self, message, original, english, language):
        # Escaped markdown preserves the spoken content without fake formatting.
        plain = format_transcript(original, language, english)
        original = discord.utils.escape_markdown(original)
        if english:
            english = discord.utils.escape_markdown(english)
        heading = "**Original ({})**".format(language_label(language))
        body = heading + "\n" + original
        if english:
            body += "\n\n**English translation**\n" + english
        pieces = transcript_chunks(body, CHUNK_SIZE)
        mention_settings = discord.AllowedMentions.none()
        if len(pieces) > MAX_CHUNKS:
            perms = message.channel.permissions_for(message.guild.me)
            if perms.attach_files:
                file = discord.File(io.BytesIO(plain.encode("utf-8")), filename="voice-transcript.txt")
                await message.reply(
                    "Voice note transcript and English translation are attached.",
                    file=file, mention_author=False, allowed_mentions=mention_settings,
                )
                return
        for chunk in pieces:
            if self._closing:
                return
            await message.reply(
                chunk, mention_author=False, allowed_mentions=mention_settings,
            )

    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    @commands.group(name="voicetranscribe", aliases=["vt"], invoke_without_command=True)
    async def vt(self, ctx):
        """Show voice transcription status."""
        guild = self.config.guild(ctx.guild)
        enabled, translate, language, vocabulary, model, speed, threads, engine = await asyncio.gather(
            guild.enabled(), guild.translate(), guild.language(), guild.vocabulary(),
            self.config.model(), self.config.speed(), self.config.cpu_threads(), self.config.engine(),
        )
        await ctx.send(
            "**VoiceTranscribe**: {} | English translation: {} | Detection: {}\n"
            "Model: **{}** | Speed: **{}** | CPU threads: {} | Translator: {}\n"
            "Vocabulary hints: {} | Queue: {}/{}".format(
                "ON" if enabled else "OFF", "ON" if translate else "OFF", language,
                model, speed, threads, engine, len(vocabulary), len(self._jobs), MAX_PENDING,
            )
        )

    @vt.command(name="on")
    async def vt_on(self, ctx):
        """Start automatic transcription for this server."""
        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.send("Voice note transcription **enabled** (English translation is configurable).")

    @vt.command(name="off")
    async def vt_off(self, ctx):
        """Stop automatic transcription for this server."""
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.send("Voice note transcription **disabled**.")

    @vt.command(name="translate")
    async def vt_translate(self, ctx, mode: str = None):
        """Toggle English translation: [p]vt translate on|off."""
        conf = self.config.guild(ctx.guild).translate
        if mode is None:
            await ctx.send("English translation: **{}**.".format("ON" if await conf() else "OFF"))
        elif mode.lower() in ("on", "off"):
            await conf.set(mode.lower() == "on")
            await ctx.send("English translation **{}**.".format(mode.lower()))
        else:
            await ctx.send("Usage: {}vt translate on|off".format(ctx.clean_prefix))

    @vt.command(name="language")
    async def vt_language(self, ctx, code: str = None):
        """Auto-detect or lock the source language (e.g., es, ru, ja)."""
        if code is None:
            await ctx.send("Source language: **{}**. Use {}vt language auto|<code>.".format(
                await self.config.guild(ctx.guild).language(), ctx.clean_prefix))
            return
        code = code.lower().strip()
        if code != "auto":
            from faster_whisper.tokenizer import LANGUAGES
            if code not in LANGUAGES:
                await ctx.send("Unknown Whisper language code. Try auto, es, ru, ja, fr, etc.")
                return
        await self.config.guild(ctx.guild).language.set(code)
        await ctx.send("Voice recognition language: **{}**.".format("automatic" if code == "auto" else language_label(code)))

    @vt.command(name="ignore")
    async def vt_ignore(self, ctx, channel: discord.TextChannel = None):
        """Toggle transcription for a channel and its threads."""
        channel = channel or ctx.channel
        async with self.config.guild(ctx.guild).excluded_channels() as ignored:
            if channel.id in ignored:
                ignored.remove(channel.id)
                enabled = True
            else:
                ignored.append(channel.id)
                enabled = False
        await ctx.send("Transcription **{}** in {}.".format("enabled" if enabled else "disabled", channel.mention))

    @vt.group(name="words", invoke_without_command=True)
    async def vt_words(self, ctx):
        """List custom recognition vocabulary hints."""
        words = await self.config.guild(ctx.guild).vocabulary()
        output = ", ".join(discord.utils.escape_markdown(w) for w in words) if words else "(none)"
        await ctx.send("Recognition words: " + output, allowed_mentions=discord.AllowedMentions.none())

    @vt_words.command(name="add")
    async def vt_words_add(self, ctx, *, phrase: str):
        """Help Whisper recognize a name, slang or technical term."""
        phrase = " ".join(phrase.split())
        if not (1 <= len(phrase) <= 80):
            await ctx.send("Use a phrase between 1 and 80 characters.")
            return
        async with self.config.guild(ctx.guild).vocabulary() as words:
            if any(w.casefold() == phrase.casefold() for w in words):
                await ctx.send("That phrase is already in the recognition vocabulary.")
                return
            if len(words) >= 20 or sum(map(len, words)) + len(phrase) > 400:
                await ctx.send("Vocabulary full (20 phrases / 400 characters maximum).")
                return
            words.append(phrase)
        await ctx.send("Added a recognition hint: **{}**".format(discord.utils.escape_markdown(phrase)), allowed_mentions=discord.AllowedMentions.none())

    @vt_words.command(name="remove")
    async def vt_words_remove(self, ctx, *, phrase: str):
        """Remove a recognition vocabulary hint."""
        async with self.config.guild(ctx.guild).vocabulary() as words:
            index = next((i for i, value in enumerate(words) if value.casefold() == phrase.strip().casefold()), None)
            if index is None:
                await ctx.send("That phrase is not in the vocabulary.")
                return
            words.pop(index)
        await ctx.send("Recognition hint removed.")

    @vt_words.command(name="clear")
    async def vt_words_clear(self, ctx):
        """Clear this server's custom recognition vocabulary."""
        await self.config.guild(ctx.guild).vocabulary.set([])
        await ctx.send("Recognition vocabulary cleared.")

    @vt.command(name="model")
    @commands.is_owner()
    async def vt_model(self, ctx, name: str = None):
        """Bot owner: choose a multilingual Whisper model (tiny/base/small/medium/large-v3)."""
        if name is None:
            await ctx.send("Model: **{}**. Available: {}".format(await self.config.model(), ", ".join(MODEL_SIZES)))
            return
        name = name.lower()
        if name not in MODEL_SIZES:
            await ctx.send("Choose: " + ", ".join(MODEL_SIZES))
            return
        await self.config.model.set(name)
        await ctx.send("Whisper model set to **{}**. Downloads/loads at next voice note. Large models are substantially slower on CPU.".format(name))

    @vt.command(name="speed")
    @commands.is_owner()
    async def vt_speed(self, ctx, name: str = None):
        """Bot owner: fast (beam 1), balanced (beam 3), or accurate (beam 5)."""
        if name is None:
            await ctx.send("Decode mode: **{}**. Available: {}".format(await self.config.speed(), ", ".join(SPEED_BEAMS)))
            return
        name = name.lower()
        if name not in SPEED_BEAMS:
            await ctx.send("Choose: " + ", ".join(SPEED_BEAMS))
            return
        await self.config.speed.set(name)
        await ctx.send("Decode mode: **{}** (beam {}).".format(name, SPEED_BEAMS[name]))

    @vt.command(name="threads")
    @commands.is_owner()
    async def vt_threads(self, ctx, count: int = None):
        """Bot owner: limit CPU inference threads (1 to 8)."""
        if count is None:
            await ctx.send("Whisper CPU threads: **{}**.".format(await self.config.cpu_threads()))
            return
        if not 1 <= count <= 8:
            await ctx.send("Select 1 through 8 CPU threads.")
            return
        await self.config.cpu_threads.set(count)
        await ctx.send("CPU threads set to **{}**. Takes effect on next note (reloads model).".format(count))

    @vt.command(name="engine")
    @commands.is_owner()
    async def vt_engine(self, ctx, mode: str = None):
        """Bot owner: auto (installed Argos language pack first) or whisper."""
        if mode is None:
            await ctx.send("Translation engine: **{}** (auto/whisper).".format(await self.config.engine()))
            return
        mode = mode.lower()
        if mode not in ("auto", "whisper"):
            await ctx.send("Choose: auto or whisper.")
            return
        await self.config.engine.set(mode)
        await ctx.send("Translation engine set to **{}**.".format(mode))
