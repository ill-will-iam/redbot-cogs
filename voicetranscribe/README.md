# VoiceTranscribe (Red-DiscordBot V3)

Automatically **reply to native Discord voice messages** with readable text. It does not join or record live voice channels, transcribe ordinary audio uploads, or call a paid speech API.

## Install / update

```text
~load downloader
~repo update redbot-cogs
~cog install redbot-cogs voicetranscribe
~load voicetranscribe
~vt on
```

If already installed, run `~cog update voicetranscribe`, then `~reload voicetranscribe` if prompted. `~repo update` alone doesn't update an installed cog.

Red's Downloader installs `faster-whisper` from `info.json`. **Python 3.10+** is required. On first use, it downloads the multilingual **base** Whisper model into the bot account's model cache (outbound Internet required for this initial download). Transcription runs on the VPS CPU, without uploading recordings to a transcription API. Allocate spare memory/CPU for inference; performance varies by hardware.

## Commands (admin / Manage Server)

- `~vt` — see status, number of ignored channels, and queued jobs.
- `~vt on` — enable for the server (off by default).
- `~vt off` — disable for the server.
- `~vt ignore` — toggle transcription for current channel.
- `~vt ignore #channel` — toggle a named text channel (including its threads).

## Permissions and requirements

Enable **Message Content Intent** in the Discord Developer Portal and in Red's intents configuration. Fatboy needs **View Channel, Read Message History, Send Messages**, and **Send Messages in Threads** for thread support; **Attach Files** allows very long transcripts to be sent as a text attachment. The bot only handles voice notes sent while it is online.

## Safety / limits

- Only native voice messages recognized by the Discord flag or voice attachment metadata.
- Max **10 minutes** and **8 MiB** per note; larger notes are skipped.
- At most **one CPU transcription** runs at a time; at most **6 notes** may be queued/running globally. Overflow is skipped rather than overloading the VPS.
- Server opt-in, channel exclusions, no mentions/pings, and temporary audio deletion.
- Very long transcripts are split into readable replies, or attached as a `.txt` file if the bot has permission.
- Whisper transcripts can contain recognition errors, especially with noise, accents, overlapping voices or music.

The model download is external, but voice audio stays on the VPS for inference; the resulting transcript is visible in Discord. No audio/transcript history is written to Red's persistent config.
