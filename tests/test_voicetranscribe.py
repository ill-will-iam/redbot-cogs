"""Unit tests for native Discord voice notes, helper options and output formatting."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

MODULE_PATH = Path(__file__).resolve().parents[1] / "voicetranscribe" / "utils.py"
spec = importlib.util.spec_from_file_location("voice_utils", MODULE_PATH)
utils = importlib.util.module_from_spec(spec)
spec.loader.exec_module(utils)


def note(*, flags=0, duration=3.0, waveform=b"abc", size=1000,
         filename="voice-message.ogg", content_type="audio/ogg"):
    attachment = SimpleNamespace(duration=duration, waveform=waveform, size=size,
                                 filename=filename, content_type=content_type)
    return SimpleNamespace(flags=SimpleNamespace(value=flags), attachments=[attachment]), attachment


def test_voice_flag_with_missing_waveform():
    msg, attachment = note(flags=1 << 13, waveform=None)
    assert utils.voice_note_attachment(msg) is attachment


def test_voice_attachment_metadata_without_flag():
    msg, attachment = note()
    assert utils.voice_note_attachment(msg) is attachment


def test_normal_audio_upload_is_not_transcribed():
    msg, _ = note(duration=None, waveform=None)
    assert utils.voice_note_attachment(msg) is None


def test_invalid_audio_rejected():
    for kwargs in (
        {"duration": 601}, {"duration": 0}, {"size": 0},
        {"size": utils.MAX_AUDIO_BYTES + 1}, {"filename": "fake.png"},
        {"content_type": "image/png"},
    ):
        msg, _ = note(flags=1 << 13, **kwargs)
        assert utils.voice_note_attachment(msg) is None


def test_chunker_preserves_every_character():
    for phrase in ("a" * 101, "hello world hello world " * 20, "a b c d e f g"):
        chunks = utils.transcript_chunks(phrase, 15)
        assert "".join(chunks) == phrase
        assert all(0 < len(chunk) <= 15 for chunk in chunks)


def test_chunker_rejects_invalid_length():
    try:
        utils.transcript_chunks("Hello", 0)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_labels_for_multilingual_output():
    expected = "Original (Russian):\nПривет\n\nEnglish translation:\nHello"
    assert utils.format_transcript("Привет", "ru", "Hello") == expected
    assert utils.format_transcript("hello", "en") == "Original (English):\nhello"
    assert utils.language_label("es") == "Spanish"
    assert utils.language_label("xx") == "XX"


def test_multilingual_model_options_and_decoding_speed():
    assert set(("tiny", "base", "small", "medium")) <= set(utils.MODEL_SIZES)
    assert utils.SPEED_BEAMS["fast"] < utils.SPEED_BEAMS["balanced"]
    assert utils.SPEED_BEAMS["balanced"] < utils.SPEED_BEAMS["accurate"]
