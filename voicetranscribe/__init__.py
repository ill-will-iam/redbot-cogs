"""Red-DiscordBot extension entry point for automatic voice note transcription."""

from .voicetranscribe import VoiceTranscribe


async def setup(bot):
    await bot.add_cog(VoiceTranscribe(bot))
