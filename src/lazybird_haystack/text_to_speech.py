import re
from typing import Any

import httpx
from haystack import component, default_from_dict, default_to_dict
from haystack.dataclasses import ByteStream
from haystack.utils import Secret, deserialize_secrets_inplace

BASE_URL = "https://api.lazybird.app/v2"
DEFAULT_VOICE_ID = "tgJ2Hes6DauwTg8kFrRPLN"  # Elyssia, a warm narrator
SSML = re.compile(r"^\s*<speak[\s>]", re.IGNORECASE)


class LazybirdError(Exception):
    """A Lazybird API request failed. The message says what to fix."""


@component
class LazybirdTextToSpeech:
    """
    Turns text into natural AI speech with [Lazybird](https://www.lazybird.app) and returns the MP3 as a `ByteStream`.

    Text that starts with `<speak>` is sent as SSML. API reference:
    [lazybird.app/docs/api-reference](https://www.lazybird.app/docs/api-reference).

    ### Usage example
    ```python
    from lazybird_haystack import LazybirdTextToSpeech

    tts = LazybirdTextToSpeech()  # reads the API key from LAZYBIRD_API_KEY
    result = tts.run(text="Your order has shipped.")
    result["audio"].to_file("order.mp3")
    ```
    """

    def __init__(
        self,
        api_key: Secret = Secret.from_env_var("LAZYBIRD_API_KEY"),
        voice_id: str = DEFAULT_VOICE_ID,
        locale: str | None = None,
        speed: float | None = None,
        settings: dict[str, Any] | None = None,
        timeout: float = 120.0,
    ) -> None:
        """
        Creates a LazybirdTextToSpeech component.

        :param api_key: Your Lazybird API key, from [Studio settings](https://www.lazybird.app/studio/settings).
        :param voice_id: The voice to speak with. Any voice can speak other languages; see `locale`.
        :param locale: Optional language and accent to speak in, such as `es-ES` or `hi-IN`.
        :param speed: Optional speaking speed, 1 is normal (0.5 to 2).
        :param settings: Optional more voice settings: `pitch` (0.5 to 1.5), `volume` (0 to 2), and `style` and
            `styleIntensity` for voices with speaking styles.
        :param timeout: Seconds to wait for the audio.
        """
        self.api_key = api_key
        self.voice_id = voice_id
        self.locale = locale
        self.speed = speed
        self.settings = settings
        self.timeout = timeout

    @component.output_types(audio=ByteStream)
    def run(self, text: str, voice_id: str | None = None, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Generates speech for `text`.

        :param text: The text to speak, or SSML that starts with `<speak>`.
        :param voice_id: If given, overrides the voice set at initialization.
        :param settings: If given, overrides voice settings set at initialization, such as `speed` or `locale`.
        :returns: A dictionary with `audio`, the MP3 as a `ByteStream` with `mime_type` `audio/mpeg`.
        :raises LazybirdError: If the API key is not valid, credits ran out or the request failed.
        """
        body = self._request_body(text, voice_id, settings)
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(f"{BASE_URL}/generate-speech", headers=self._headers(), json=body)
        return {"audio": _audio(response, body["voiceId"])}

    @component.output_types(audio=ByteStream)
    async def run_async(
        self, text: str, voice_id: str | None = None, settings: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Generates speech for `text`. The asynchronous version of `run`, with the same parameters and output.
        """
        body = self._request_body(text, voice_id, settings)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{BASE_URL}/generate-speech", headers=self._headers(), json=body)
        return {"audio": _audio(response, body["voiceId"])}

    def to_dict(self) -> dict[str, Any]:
        """
        Serializes the component to a dictionary.
        """
        return default_to_dict(
            self,
            api_key=self.api_key.to_dict(),
            voice_id=self.voice_id,
            locale=self.locale,
            speed=self.speed,
            settings=self.settings,
            timeout=self.timeout,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LazybirdTextToSpeech":
        """
        Deserializes the component from a dictionary.
        """
        deserialize_secrets_inplace(data["init_parameters"], keys=["api_key"])
        return default_from_dict(cls, data)

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key.resolve_value() or ""}

    def _request_body(self, text: str, voice_id: str | None, settings: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be the text (or SSML) to speak.")
        merged = {"locale": self.locale, "speed": self.speed, **(self.settings or {}), **(settings or {})}
        merged = {key: value for key, value in merged.items() if value is not None}
        return {
            "voiceId": voice_id or self.voice_id,
            **({"ssml": text} if SSML.match(text) else {"text": text}),
            **({"settings": merged} if merged else {}),
        }


def list_voices(query: str | None = None, api_key: Secret = Secret.from_env_var("LAZYBIRD_API_KEY")) -> list[dict]:
    """
    Lists voices you can use as `voice_id`: your own voices first, then the Lazybird library.

    :param query: Optional search by name, language or style, such as `"british narrator"`.
    :param api_key: Your Lazybird API key.
    :returns: Voices as dictionaries with `id`, `displayName`, `language` and `description`.
    """
    params = {"limit": 100, **({"q": query} if query else {})}
    response = httpx.get(
        f"{BASE_URL}/voices", headers={"X-API-Key": api_key.resolve_value() or ""}, params=params, timeout=30
    )
    _raise_for_error(response)
    voices = response.json()
    return [*voices.get("myVoices", []), *voices.get("library", [])]


def _audio(response: httpx.Response, voice_id: str) -> ByteStream:
    _raise_for_error(response)
    return ByteStream(data=response.content, mime_type="audio/mpeg", meta={"voice_id": voice_id})


def _raise_for_error(response: httpx.Response) -> None:
    if response.is_success:
        return
    try:
        body = response.json()
    except ValueError:
        body = {}
    # "Authorization Error: …", "Invalid Input: …" read better without the prefix.
    message = re.sub(r"^[A-Za-z ]+(?:Error|Input): ", "", str(body.get("error") or ""))
    status = response.status_code
    if status == 401:
        raise LazybirdError("Your Lazybird API key is not valid. Check LAZYBIRD_API_KEY.")
    if status == 422:
        if re.search("credit", message, re.IGNORECASE):
            raise LazybirdError(
                "You are out of Lazybird credits. Get more at lazybird.app/pricing, "
                "or wait for your monthly credits to reset."
            )
        raise LazybirdError(f"{message or 'Your plan does not allow this request.'} See lazybird.app/pricing.")
    if status == 429:
        wait = body.get("retryAfterSeconds")
        raise LazybirdError(f"Too many requests. Try again in {wait or 'a few'} seconds.")
    if status == 503:
        raise LazybirdError("Lazybird is busy right now. Try again in a minute.")
    raise LazybirdError(message or f"Lazybird request failed ({status})")
