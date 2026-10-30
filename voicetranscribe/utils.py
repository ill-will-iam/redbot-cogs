"""Pure helpers for Discord voice-note detection, transcription and formatting."""

VOICE_MESSAGE_FLAG = 1 << 13  # Discord IS_VOICE_MESSAGE
MAX_AUDIO_BYTES = 8 * 1024 * 1024
MAX_AUDIO_SECONDS = 600
MAX_PENDING = 6
MAX_CHUNKS = 6
CHUNK_SIZE = 1800
AUDIO_EXTENSIONS = frozenset({".ogg", ".oga", ".opus", ".webm", ".mp3", ".m4a", ".wav"})
MODEL_SIZES = ("tiny", "base", "small", "medium", "large-v3")
SPEED_BEAMS = {"fast": 1, "balanced": 3, "accurate": 5}
LANGUAGE_NAMES = {
    "ar": "Arabic", "bg": "Bulgarian", "cs": "Czech", "da": "Danish",
    "de": "German", "el": "Greek", "en": "English", "es": "Spanish",
    "fa": "Persian", "fi": "Finnish", "fr": "French", "he": "Hebrew",
    "hi": "Hindi", "hr": "Croatian", "hu": "Hungarian", "id": "Indonesian",
    "it": "Italian", "ja": "Japanese", "ko": "Korean", "ms": "Malay",
    "nl": "Dutch", "no": "Norwegian", "pl": "Polish", "pt": "Portuguese",
    "ro": "Romanian", "ru": "Russian", "sk": "Slovak", "sv": "Swedish",
    "ta": "Tamil", "th": "Thai", "tr": "Turkish", "uk": "Ukrainian",
    "ur": "Urdu", "vi": "Vietnamese", "zh": "Chinese",
}


def language_label(code):
    """Produce a human-readable language label without additional dependencies."""
    return LANGUAGE_NAMES.get(str(code).lower(), str(code).upper() if code else "Unknown")


def voice_note_attachment(message):
    """Return a valid native voice-note attachment, never an ordinary audio upload."""
    flags = getattr(getattr(message, "flags", None), "value", 0)
    is_voice = bool(flags & VOICE_MESSAGE_FLAG)
    for attachment in getattr(message, "attachments", ()):
        duration = getattr(attachment, "duration", None)
        waveform = getattr(attachment, "waveform", None)
        if not is_voice and (duration is None or waveform is None):
            continue
        if not isinstance(duration, (float, int)) or not 0 < duration <= MAX_AUDIO_SECONDS:
            continue
        size = getattr(attachment, "size", 0)
        if not isinstance(size, int) or not 0 < size <= MAX_AUDIO_BYTES:
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
    """Split without losing characters; prefer word boundaries."""
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


def format_transcript(original, language, english=None):
    """Build plain-text headings; Discord markdown escaping is applied by the caller."""
    result = "Original ({}):\n{}".format(language_label(language), original)
    if english:
        result += "\n\nEnglish translation:\n" + english
    return result
