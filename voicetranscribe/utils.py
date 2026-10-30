"""Pure helpers for native Discord voice notes and message-sized transcript chunks."""

VOICE_MESSAGE_FLAG = 1 << 13  # Discord IS_VOICE_MESSAGE
MAX_AUDIO_BYTES = 8 * 1024 * 1024
MAX_AUDIO_SECONDS = 600
MAX_PENDING = 6
MAX_CHUNKS = 6
CHUNK_SIZE = 1800
AUDIO_EXTENSIONS = frozenset({".ogg", ".oga", ".opus", ".webm", ".mp3", ".m4a", ".wav"})


def voice_note_attachment(message):
    """Return the native voice attachment, or None for regular audio uploads.

    A voice message is recognized by Discord's message flag, with attachment
    duration + waveform as a supported fallback for older library versions.
    File extensions alone are never used to recognize a voice message.
    """
    flags = getattr(getattr(message, "flags", None), "value", 0)
    is_voice = bool(flags & VOICE_MESSAGE_FLAG)
    for attachment in getattr(message, "attachments", ()):
        duration = getattr(attachment, "duration", None)
        waveform = getattr(attachment, "waveform", None)
        if not is_voice and (duration is None or waveform is None):
            continue
        if not isinstance(duration, (float, int)) or not (0 < duration <= MAX_AUDIO_SECONDS):
            continue
        size = getattr(attachment, "size", 0)
        if not isinstance(size, int) or not (0 < size <= MAX_AUDIO_BYTES):
            continue
        filename = getattr(attachment, "filename", "")
        suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if "." + suffix not in AUDIO_EXTENSIONS:
            continue
        content_type = (getattr(attachment, "content_type", None) or "").lower()
        if content_type and not (content_type.startswith("audio/") or content_type == "application/ogg"):
            continue
        return attachment
    return None


def transcript_chunks(text, limit=CHUNK_SIZE):
    """Split a transcript without discarding characters; preserve word breaks where possible."""
    if limit < 1:
        raise ValueError("limit must be positive")
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split = text.rfind(" ", 0, limit + 1)
        if split < limit // 2:
            split = limit
        chunks.append(text[:split])
        text = text[split:]
    return chunks
