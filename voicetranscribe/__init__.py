from .voicetranscribe import VoiceTranscribe

async def setup(bot):
    await bot.add_cog(VoiceTranscribe(bot))
