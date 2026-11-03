# lazybird-haystack

[Lazybird](https://www.lazybird.app) text to speech for [Haystack](https://haystack.deepset.ai). The `LazybirdTextToSpeech` component turns text into natural AI speech (MP3) in your pipelines and agents, for voiceovers, spoken answers, announcements and anything else that should talk.

Lazybird is an AI voiceover generator with 500+ voices in 150+ languages and accents, voice cloning, voice design and a [text to speech API](https://www.lazybird.app/text-to-speech-api).

## Install

```sh
pip install lazybird-haystack
```

Requires Python 3.10 or later and Haystack 2.12 or later.

## Set up your account

1. [Sign up for Lazybird](https://www.lazybird.app). The free plan includes 10,000 credits a month, no credit card needed.
2. Open [Studio settings](https://www.lazybird.app/studio/settings) and create an API key.
3. Set it as an environment variable:

```sh
export LAZYBIRD_API_KEY="your-api-key"
```

## Usage

### Text to speech

```python
from lazybird_haystack import LazybirdTextToSpeech

tts = LazybirdTextToSpeech()
result = tts.run(text="Welcome back. Your report is ready.")
result["audio"].to_file("welcome.mp3")
```

`run` returns `audio`, a Haystack `ByteStream` with the MP3 and `mime_type` `audio/mpeg`. Text that starts with `<speak>` is sent as SSML, for pauses and pronunciation:

```python
tts.run(text='<speak>Good morning. <break time="500ms"/> The front door is open.</speak>')
```

### Voices, languages and settings

```python
from lazybird_haystack import LazybirdTextToSpeech, list_voices

for voice in list_voices("british narrator")[:5]:
    print(voice["id"], voice["displayName"], voice["language"])

tts = LazybirdTextToSpeech(
    voice_id="tgJ2Hes6DauwTg8kFrRPLN",  # Elyssia, the default voice
    locale="es-ES",  # any voice can speak other languages and accents
    speed=1.1,  # 1 is normal (0.5 to 2)
    settings={"pitch": 1.0, "volume": 1.0},
)
```

`list_voices` returns your own voices first, then the Lazybird library. `run` also takes `voice_id` and `settings` to override them per call.

### In a pipeline

`PromptBuilder` fills in a template and `LazybirdTextToSpeech` speaks it:

```python
from haystack import Pipeline
from haystack.components.builders import PromptBuilder
from lazybird_haystack import LazybirdTextToSpeech

pipeline = Pipeline()
pipeline.add_component("template", PromptBuilder(template="Hi {{ name }}, your order {{ order }} has shipped."))
pipeline.add_component("tts", LazybirdTextToSpeech())
pipeline.connect("template.prompt", "tts.text")

result = pipeline.run({"template": {"name": "Maya", "order": "1042"}})
result["tts"]["audio"].to_file("order.mp3")
```

To load a saved pipeline in Haystack 3, add this package to the trusted modules: `Pipeline.loads(yaml, allowed_modules=["lazybird_haystack"])`.

### Spoken answers from an LLM

```python
from haystack import Pipeline
from haystack.components.builders import ChatPromptBuilder
from haystack.components.converters import OutputAdapter
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.dataclasses import ChatMessage
from lazybird_haystack import LazybirdTextToSpeech

template = [ChatMessage.from_user("Answer in two short sentences: {{ question }}")]

pipeline = Pipeline()
pipeline.add_component("prompt", ChatPromptBuilder(template=template, required_variables=["question"]))
pipeline.add_component("llm", OpenAIChatGenerator())  # needs OPENAI_API_KEY
pipeline.add_component("answer", OutputAdapter(template="{{ replies[0].text }}", output_type=str))
pipeline.add_component("tts", LazybirdTextToSpeech())
pipeline.connect("prompt.prompt", "llm.messages")
pipeline.connect("llm.replies", "answer.replies")
pipeline.connect("answer.output", "tts.text")

result = pipeline.run({"prompt": {"question": "Why is the sky blue?"}})
result["tts"]["audio"].to_file("answer.mp3")
```

### Errors

An invalid API key, missing credits or another failed request raises `LazybirdError` with a message that says what to fix.

## Pricing

One credit is one character of text, shared between the Lazybird studio and the API. The free plan includes 10,000 credits a month; paid plans start at $9 a month and include commercial usage rights. See [pricing](https://www.lazybird.app/pricing).

## Resources

- [Lazybird docs](https://www.lazybird.app/docs)
- [Lazybird API reference](https://www.lazybird.app/docs/api-reference)
- [Changelog](https://github.com/lazybirdai/lazybird-haystack/blob/main/CHANGELOG.md)

## License

[MIT](https://github.com/lazybirdai/lazybird-haystack/blob/main/LICENSE)
