# VoiceTranscribe — Discord voice notes with language detection and English translation

Fatboy automatically replies to **native Discord voice messages** with the text as spoken, followed immediately by a translation into English when the detected source language is not English. It does not listen to live voice channels or transcribe regular audio file uploads.

## Update an existing installation

```text
~cog update voicetranscribe
~reload voicetranscribe
~vt
~vt translate on
~vt language auto
```

If not installed, use `~repo update redbot-cogs`, `~cog install redbot-cogs voicetranscribe`, `~load voicetranscribe`, and `~vt on`. Red Downloader installs `faster-whisper>=1.1.0,<2` in Red's environment. **Python 3.10+** is required. The selected multilingual model downloads once on first use; outbound access and free disk space are required.

## Result format

A Russian voice note produces a reply like:

> **Original (Russian)**
> Привет! Как дела?
>
> **English translation**
> Hi! How are you?

English notes only show the original text. Mixed-language notes may be treated as the predominant detected language. A low-confidence language guess can cause incorrect translations. Nothing is sent to paid cloud transcription services. The audio is briefly downloaded to a temporary directory and removed once decoded; the transcript remains visible in Discord.

## Commands

| Command | Who | Meaning |
| --- | --- | --- |
| `~vt` | Server admin | Status, current model, translation and processing queue |
| `~vt on` / `~vt off` | Server admin | Enable or disable for the server |
| `~vt translate on` / `~vt translate off` | Server admin | Add English translation below non-English text (default on) |
| `~vt language auto` | Server admin | Automatic language recognition (recommended) |
| `~vt language es` | Server admin | Force Spanish for all messages in this server (skip auto-detection) |
| `~vt ignore #channel` | Server admin | Toggle channel and thread exclusions |
| `~vt words add Ribbit Royale` | Server admin | Add custom proper nouns or jargon to recognition hints |
| `~vt words` / `~vt words remove <phrase>` / `~vt words clear` | Server admin | Manage up to 20 recognition hints |
| `~vt speed fast` / `balanced` / `accurate` | Bot owner | Beam search 1 / 3 / 5. Fast is now the default. |
| `~vt model tiny` / `base` / `small` / `medium` / `large-v3` | Bot owner | Choose a multilingual recognition model for all servers |
| `~vt threads 2` | Bot owner | Limit per-inference CPU threads (1–8) |
| `~vt engine auto` / `whisper` | Bot owner | Use installed offline Argos text models when available, otherwise Whisper's audio-to-English translation |

The selected model is global across Fatboy's servers so one server cannot cause the bot to download an enormous model. Changing model or CPU-thread settings reloads the model before the next voice note, and may temporarily pause the queue.

## Speed versus accuracy

- **Fastest CPU:** `~vt model tiny`, `~vt speed fast`. Best for short, clear voice notes; less reliable on accents, slang and background noise.
- **Recommended starting point:** `~vt model base`, `~vt speed fast`. Faster decoding than the original cog (beam 1 instead of 3).
- **Improved recognition:** `~vt model small`, `~vt speed balanced`, and use `~vt words add ...` for names, locations, game vocabulary or recurring jargon. Needs more CPU/RAM and can be slower.
- **Heavier:** `medium` and `large-v3` provide more model capacity but **can be very slow** on a CPU-only VPS. They download substantial model weights; don't assume bigger is faster.

Language detection is automatic; the model supports many languages, including Russian, Spanish, German, French, Japanese, Korean, Chinese, Ukrainian and more. Accuracy varies by language. Translating non-English speech with Whisper requires **a second recognition pass** and can take noticeably longer than transcribing English alone. `~vt translate off` avoids this extra work.

## Optional faster local translation (Argos)

For frequently used languages, you may install **Argos Translate** and specific offline source-to-English language packs into the same Redbot Python environment. For example:

```bash
/path/to/redbot/venv/bin/python -m pip install argostranslate
/path/to/redbot/venv/bin/argospm update
/path/to/redbot/venv/bin/argospm install translate-es_en
/path/to/redbot/venv/bin/argospm install translate-ru_en
```

Replace the example virtual-environment path with Fatboy's actual Python environment. These are optional manual installs, not automatically downloaded by the cog. The `auto` engine tries locally installed Argos text models first; if one is unavailable it falls back to Whisper's speech-to-English translation. Argos can avoid the second audio pass but introduces its own model and CPU/memory usage. `~vt engine whisper` always uses Whisper. No externally hosted translation API is called. Some languages have no available Argos pack.

## Permissions and bounds

Message Content Intent must be enabled in Discord's Developer Portal and the running bot. Fatboy needs **View Channel, Read Message History, Send Messages**, plus **Send Messages in Threads** when applicable. **Attach Files** is useful for long results. The bot processes only notes posted while it is online. A voice note must be at most **10 minutes / 8 MiB**. Only one transcription is processed at once; at most six can be queued/running globally. New notes beyond the queue limit are skipped rather than overloading the VPS. Transcription is opt-in per server; existing enabled/ignored settings are preserved during upgrade.

Word hints are untrusted user-entered text added to the recognition prompt; don't include secrets. Recognition and translation can make mistakes; do not treat their output as definitive evidence of what someone said. The bot does not store user audio or transcript history in Red configuration, but it does post transcription text into Discord and that text follows the server's message retention policy.
