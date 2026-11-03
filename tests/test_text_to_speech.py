import json

import pytest
from haystack import Pipeline
from haystack.components.builders import PromptBuilder
from haystack.utils import Secret

from lazybird_haystack import LazybirdError, LazybirdTextToSpeech, list_voices

MP3 = b"ID3 fake mp3"
SPEECH_URL = "https://api.lazybird.app/v2/generate-speech"


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("LAZYBIRD_API_KEY", "test-key")


def sent_body(httpx_mock):
    return json.loads(httpx_mock.get_request().content)


def test_sends_the_text_and_returns_the_mp3(httpx_mock):
    httpx_mock.add_response(url=SPEECH_URL, method="POST", content=MP3, headers={"Content-Type": "audio/mpeg"})
    tts = LazybirdTextToSpeech(voice_id="v1", locale="es-ES", speed=1.2)

    audio = tts.run(text="Hola")["audio"]

    assert audio.data == MP3
    assert audio.mime_type == "audio/mpeg"
    assert audio.meta == {"voice_id": "v1"}
    assert httpx_mock.get_request().headers["X-API-Key"] == "test-key"
    assert sent_body(httpx_mock) == {"voiceId": "v1", "text": "Hola", "settings": {"locale": "es-ES", "speed": 1.2}}


def test_sends_ssml_and_takes_overrides_per_call(httpx_mock):
    httpx_mock.add_response(url=SPEECH_URL, content=MP3)
    tts = LazybirdTextToSpeech(speed=1.2, settings={"pitch": 0.9})

    tts.run(text='<speak>Hi <break time="1s"/> there</speak>', voice_id="v2", settings={"speed": 0.8})

    assert sent_body(httpx_mock) == {
        "voiceId": "v2",
        "ssml": '<speak>Hi <break time="1s"/> there</speak>',
        "settings": {"speed": 0.8, "pitch": 0.9},
    }


def test_uses_the_default_voice_without_settings(httpx_mock):
    httpx_mock.add_response(url=SPEECH_URL, content=MP3)

    LazybirdTextToSpeech().run(text="Hello")

    assert sent_body(httpx_mock) == {"voiceId": "tgJ2Hes6DauwTg8kFrRPLN", "text": "Hello"}


async def test_run_async(httpx_mock):
    httpx_mock.add_response(url=SPEECH_URL, content=MP3)

    result = await LazybirdTextToSpeech().run_async(text="Hello")

    assert result["audio"].data == MP3


@pytest.mark.parametrize(
    ("status", "body", "message"),
    [
        (401, {"error": "Authorization Error: bad key"}, "Your Lazybird API key is not valid"),
        (422, {"error": "Insufficient Credits: 0 left"}, "You are out of Lazybird credits"),
        (429, {"error": "Too many requests", "retryAfterSeconds": 30}, "Try again in 30 seconds"),
        (400, {"error": "Invalid Input: Unknown voice"}, "^Unknown voice$"),
    ],
)
def test_explains_api_errors(httpx_mock, status, body, message):
    httpx_mock.add_response(url=SPEECH_URL, status_code=status, json=body)

    with pytest.raises(LazybirdError, match=message):
        LazybirdTextToSpeech().run(text="Hello")


def test_rejects_empty_text_without_calling_the_api(httpx_mock):
    with pytest.raises(ValueError, match="text must be the text"):
        LazybirdTextToSpeech().run(text="  ")

    assert httpx_mock.get_requests() == []


def test_serializes_without_the_key():
    tts = LazybirdTextToSpeech(voice_id="v1", locale="fr-FR", settings={"volume": 1.5})

    data = tts.to_dict()

    assert data == {
        "type": "lazybird_haystack.text_to_speech.LazybirdTextToSpeech",
        "init_parameters": {
            "api_key": {"type": "env_var", "env_vars": ["LAZYBIRD_API_KEY"], "strict": True},
            "voice_id": "v1",
            "locale": "fr-FR",
            "speed": None,
            "settings": {"volume": 1.5},
            "timeout": 120.0,
        },
    }
    restored = LazybirdTextToSpeech.from_dict(data)
    assert restored.voice_id == "v1"
    assert restored.api_key == Secret.from_env_var("LAZYBIRD_API_KEY")


def test_runs_in_a_pipeline_after_a_prompt_builder(httpx_mock, monkeypatch):
    # Haystack 3 loads saved pipelines only from modules the user trusts.
    monkeypatch.setenv("HAYSTACK_DESERIALIZATION_ALLOWLIST", "lazybird_haystack")
    httpx_mock.add_response(url=SPEECH_URL, content=MP3)
    pipeline = Pipeline()
    pipeline.add_component("template", PromptBuilder(template="Hi {{ name }}, your order has shipped."))
    pipeline.add_component("tts", LazybirdTextToSpeech())
    pipeline.connect("template.prompt", "tts.text")

    result = pipeline.run({"template": {"name": "Maya"}})

    assert result["tts"]["audio"].data == MP3
    assert sent_body(httpx_mock)["text"] == "Hi Maya, your order has shipped."
    assert Pipeline.loads(pipeline.dumps()).get_component("tts").voice_id == "tgJ2Hes6DauwTg8kFrRPLN"


def test_lists_your_voices_first(httpx_mock):
    httpx_mock.add_response(
        url="https://api.lazybird.app/v2/voices?limit=100&q=warm",
        json={"myVoices": [{"id": "m1", "displayName": "Me"}], "library": [{"id": "l1", "displayName": "Elyssia"}]},
    )

    assert [voice["id"] for voice in list_voices("warm")] == ["m1", "l1"]
