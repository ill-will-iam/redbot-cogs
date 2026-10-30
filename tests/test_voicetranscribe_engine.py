"""Exercise speech/translation branching with fake model objects (no ML downloads)."""
import ast
from pathlib import Path
from types import SimpleNamespace

SOURCE = Path(__file__).resolve().parents[1] / 'voicetranscribe' / 'voicetranscribe.py'
parsed = ast.parse(SOURCE.read_text())
klass = next(node for node in parsed.body if isinstance(node, ast.ClassDef) and node.name == 'VoiceTranscribe')
func = next(node for node in klass.body if isinstance(node, ast.FunctionDef) and node.name == '_recognize')
func.decorator_list = []
namespace = {}
exec(compile(ast.Module(body=[func], type_ignores=[]), str(SOURCE), 'exec'), namespace)
recognize = namespace['_recognize']


class FakeModel:
    def __init__(self, language='ru'):
        self.calls = []
        self.language = language

    def transcribe(self, _filename, **options):
        self.calls.append(options)
        if options['task'] == 'transcribe':
            return [SimpleNamespace(text='Привет мир' if self.language == 'ru' else 'Hello world')], SimpleNamespace(language=self.language, language_probability=0.91)
        return [SimpleNamespace(text='Hello world')], None


def run(model, translate=True, engine='whisper', argos=None):
    namespace['VoiceTranscribe'] = SimpleNamespace(_argos_translate=staticmethod(argos or (lambda text, lang: None)))
    return recognize(model, 'voice.ogg', 'auto', translate, 1, ['Ribbit'], engine)


def test_non_english_whisper_is_two_pass():
    model = FakeModel()
    original, english, language, confidence, method = run(model)
    assert (original, english, language, method) == ('Привет мир', 'Hello world', 'ru', 'whisper')
    assert confidence == 0.91
    assert [x['task'] for x in model.calls] == ['transcribe', 'translate']
    assert model.calls[0]['hotwords'] == 'Ribbit'
    assert 'hotwords' not in model.calls[1]
    assert model.calls[1]['language'] == 'ru'


def test_english_skips_second_pass():
    model = FakeModel('en')
    _, english, language, _, method = run(model)
    assert (english, language, method) == (None, 'en', None)
    assert len(model.calls) == 1


def test_translation_off_skips_second_pass():
    model = FakeModel()
    _, english, _, _, method = run(model, translate=False)
    assert english is None and method is None
    assert len(model.calls) == 1


def test_argos_local_text_translation_skips_second_audio_pass():
    model = FakeModel()
    _, english, _, _, method = run(model, engine='auto', argos=lambda t, l: 'Hi world')
    assert english == 'Hi world' and method == 'argos'
    assert len(model.calls) == 1


def test_unavailable_argos_falls_back_to_whisper():
    model = FakeModel()
    _, english, _, _, method = run(model, engine='auto', argos=lambda t, l: None)
    assert english == 'Hello world' and method == 'whisper'
    assert len(model.calls) == 2
