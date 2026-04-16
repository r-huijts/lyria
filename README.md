# Lyria Song Generator

A Python CLI tool for generating songs with Google Lyria through Portkey/OpenRouter.

It supports both freeform prompting and a structured song-spec workflow, streams generation progress in a Rich terminal UI, saves audio to an `.mp3`, and saves lyrics/transcript to a matching `.txt` file.

## Features

- Freeform mode for quick prompt-based generation
- Structured mode with guided fields (`genre`, `mood`, `BPM`, `instrumentation`, etc.)
- Prompt builder (`SongSpec` -> `build_lyria_prompt`) for better Lyria-ready prompts
- Live stream progress with separate status for stream events and audio payload
- Automatic output saving:
  - audio: `your-file.mp3`
  - lyrics/transcript: `your-file.txt`
- `.env`-based API key loading (`PORTKEY_API_KEY`)

## Requirements

- Python 3.10+
- A valid Portkey API key with access to the Lyria model

## Setup

1. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure environment variables:

```bash
cp .env.example .env
```

Then edit `.env`:

```bash
PORTKEY_API_KEY=your_real_key_here
```

## Run

```bash
python lyria.py
```

### Interactive flow

On launch, you can choose:

- `1` Freeform - type one prompt directly
- `2` Structured - fill guided fields that are converted into a high-quality Lyria prompt

You'll also set an output file name (default: `song.mp3`).

Before generation starts, the tool prints:

- A prompt preview panel
- A "Starting generation" line with target output paths for audio and lyrics

## Output files

If your output file is `song.mp3`, the tool writes:

- `song.mp3` - generated audio
- `song.txt` - lyrics/transcript text (when text is returned)

## Prompt building API

The script includes these reusable pieces:

- `SongSpec` dataclass - structured prompt inputs
- `build_lyria_prompt(spec: SongSpec) -> str` - builds a natural multi-line Lyria prompt
- `generate_song_from_spec(spec: SongSpec, output_file: str = "song.mp3") -> str`

### Example (programmatic)

```python
from lyria import SongSpec, build_lyria_prompt, generate_song_from_spec

spec = SongSpec(
    genre="cinematic",
    subgenre="synth-pop",
    mood="uplifting, emotional, expansive",
    bpm=100,
    vocals="expressive female lead vocal",
    language="English",
    instrumentation=["shimmering pads", "punchy drums", "warm bass"],
    structure=["intro", "verse", "chorus", "bridge", "final chorus", "outro"],
    lyrical_theme="rebuilding after a storm and finding hope again",
)

prompt = build_lyria_prompt(spec)
print(prompt)

transcript = generate_song_from_spec(spec, output_file="cinematic-pop.mp3")
```

## Progress view

During generation, progress rows show:

- stream status (event count)
- audio status (chunks + approximate size)

When complete, both rows end with checkmarks, followed by saved file logs.

## Troubleshooting

- **Missing key**
  - Error: `Missing PORTKEY_API_KEY. Add it to your .env file.`
  - Fix: set `PORTKEY_API_KEY` in `.env`.

- **Unauthorized (401)**
  - Error: `Unauthorized (401). Check PORTKEY_API_KEY in your .env file.`
  - Fix: verify key value and account/model access.

- **Appears slow before audio starts**
  - The API may stream text/events before audio chunks arrive.
  - This is expected; stream event counters should still move.

- **No audio data received**
  - Retry with a clearer prompt and confirm model access permissions.

## Security note

- Keep `.env` private.
- Never commit real API keys.
