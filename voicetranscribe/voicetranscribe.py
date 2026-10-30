"""Automatically transcribe Discord voice notes with local Whisper."""
import asyncio
import logging
import tempfile
from pathlib import Path

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red

log = logging.getLogger("red.voicetranscribe")

class VoiceTranscribe(commands.Cog):
    """Replies to Discord voice messages with a text transcription."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=948127610, force_registration=True)
        self.config.register_guild(enabled=True, excluded_channels=[])
        self._model = None
        self._model_lock = asyncio.Lock()
        self._slots = asyncio.Semaphore(2)
        self._model_name = "base"

    async def _get_model(self):
        if self._model is None:
            async with self._model_lock:
                if self._model is None:
                    from faster_whisper import WhisperModel
                    self._model = await asyncio.to_thread(
                        WhisperModel, self._model_name, device="cpu", compute_type="int8"
                    )
        return self._model

    @staticmethod
    def _transcribe(model, filename: str):
        segments, _ = model.transcribe(filename, beam_size=5, vad_filter=True)
        return " ".join(segment.text.strip() for segment in segments).strip()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot or not message.attachments:
            return
        if not await self.config.guild(message.guild).enabled():
            return
        if message.channel.id in await self.config.guild(message.guild).excluded_channels():
            return
        me = message.guild.me
        if not me:
            return
        perms = message.channel.permissions_for(me)
        if not (perms.view_channel and perms.send_messages and perms.read_message_history):
            return
        if isinstance(message.channel, discord.Thread) and not perms.send_messages_in_threads:
            return

        # Native Discord voice messages have this message flag.
        if not message.flags.voice:
            return
        audio = next(
            (a for a in message.attachments
             if a.filename.lower().endswith((".ogg", ".oga", ".mp3", ".wav", ".m4a", ".webm"))),
            None,
        )
        if audio is None or audio.size > 15 * 1024 * 1024:
            return
        async with self._slots:
            try:
                with tempfile.TemporaryDirectory(prefix="fatboy_voice_") as folder:
                    path = Path(folder) / ("voice" + Path(audio.filename).suffix.lower())
                    await audio.save(path)
                    model = await self._get_model()
                    transcript = await asyncio.to_thread(self._transcribe, model, str(path))
                if not transcript:
                    return
                # Discord messages are limited to 2000 characters; split safely.
                header = "📝 **Voice note transcription:**\n"
                remaining = transcript
                first = True
                while remaining:
                    limit = 2000 - len(header) if first else 2000
                    if len(remaining) <= limit:
                        chunk, remaining = remaining, ""
                    else:
                        cut = remaining.rfind(" ", 0, limit + 1)
                        if cut < limit // 2:
                            cut = limit
                        chunk, remaining = remaining[:cut], remaining[cut:].lstrip()
                    await message.reply(
                        (header if first else "") + chunk,
                        mention_author=False,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                    first = False
            except (discord.HTTPException, discord.Forbidden):
                log.warning("Could not read or reply to voice note %s", message.id)
            except Exception:
                log.exception("Voice transcription failed for message %s", message.id)

    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    @commands.group(name="voicetranscribe", aliases=["vt"], invoke_without_command=True)
    async def vt(self, ctx: commands.Context):
        """Configure automatic transcription."""
        enabled = await self.config.guild(ctx.guild).enabled()
        await ctx.send(f"Automatic voice transcription is **{'ON' if enabled else 'OFF'}**.")

    @vt.command(name="on")
    async def vt_on(self, ctx: commands.Context):
        """Enable automatic transcription for this server."""
        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.send("Voice transcription enabled.")

    @vt.command(name="off")
    async def vt_off(self, ctx: commands.Context):
        """Disable automatic transcription for this server."""
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.send("Voice transcription disabled.")

    @vt.command(name="ignore")
    async def vt_ignore(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Toggle transcription in a channel (defaults to current channel)."""
        channel = channel or ctx.channel
        async with self.config.guild(ctx.guild).excluded_channels() as excluded:
            if channel.id in excluded:
                excluded.remove(channel.id)
                state = "enabled"
            else:
                excluded.append(channel.id)
                state = "disabled"
        await ctx.send(f"Transcription {state} in {channel.mention}.")
