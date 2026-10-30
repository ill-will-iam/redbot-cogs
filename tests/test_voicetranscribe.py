"""Tests for the pure voice-note recognition and splitting helpers."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

MODULE_PATH = Path(__file__).resolve().parents[1] / "voicetranscribe" / "utils.py"
spec = importlib.util.spec_from_file_location("voice_utils", MODULE_PATH)
utils = importlib.util.module_from_spec(spec)
spec.loader.exec_module(utils)


def note(*, flags=0, duration=3.0, waveform=b"123", size=1000, filename="voice-message.ogg", content_type="audio/ogg"):
    attachment = SimpleNamespace(duration=duration, waveform=waveform, size=size, filename=filename, content_type=content_type)
    return SimpleNamespace(flags=SimpleNamespace(value=flags), attachments=[attachment]), attachment


def test_discord_voice_flag():
    msg, att = note(flags=1 << 13, waveform=None)
    assert utils.voice_note_attachment(msg) is att


def test_discord_voice_metadata_without_flag():
    msg, att = note()
    assert utils.voice_note_attachment(msg) is att


def test_ordinary_audio_file_is_not_a_voice_note():
    msg, _ = note(duration=None, waveform=None)
    assert utils.voice_note_attachment(msg) is None


def test_limits_and_types():
    for kwargs in (
        {"duration": 601}, {"duration": 0}, {"size": 0},
        {"size": utils.MAX_AUDIO_BYTES + 1}, {"filename": "fake.png"},
        {"content_type": "image/png"},
    ):
        msg, _ = note(flags=1 << 13, **kwargs)
        assert utils.voice_note_attachment(msg) is None


def test_chunking_preserves_all_characters():
    for phrase in ("a" * 101, "hello world hello world " * 20, "a b c d e f g"):
        chunks = utils.transcript_chunks(phrase, 15)
        assert "".join(chunks) == phrase
        assert all(0 < len(chunk) <= 15 for chunk in chunks)


def test_zero_limit_rejected():
    try:
        utils.transcript_chunks("Hello", 0)
    except ValueError:
        pass
    else:
        assert False, "expected ValueError"
