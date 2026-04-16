# Lyria Song Generator

A Python CLI tool for generating songs with Google Lyria 3 Pro through Portkey/OpenRouter.

It supports freeform prompting, structured song specifications with guided fields, and advanced features like image-to-music generation, custom lyrics with section tags, timestamp-based structure control, and both MP3/WAV output formats.

## Features

- **Three input modes:**
  - Freeform: single prompt string
  - Structured: guided basic fields (genre, mood, BPM, vocals, instrumentation, etc.)
  - Advanced: custom lyrics, timestamp control, image input, format selection
- **Quick presets** for common use cases (full song, instrumental, custom lyrics)
- **Image-to-music generation** - up to 10 images for visual inspiration
- **Custom lyrics** with section tags (`[Verse]`, `[Chorus]`, `[Bridge]`)
- **Timestamp-based structure** for precise timing control
- **Instrumental-only mode** for background music
- **Output format selection** - MP3 or WAV
- **Live stream progress** with separate rows for stream events and audio payload
- **Automatic dual-file output:**
  - audio: `your-file.mp3` (or `.wav`)
  - lyrics/transcript: `your-file.txt`
- `.env`-based API key loading

## Requirements

- Python 3.10+
- A valid Portkey API key with access to Lyria 3 Pro model
- Image files (optional, for image-to-music generation)

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

On launch, choose:

- Quick presets: `p1`, `p2`, `p3`
- Or modes: `1` (Freeform), `2` (Structured), `3` (Advanced)

Then set output file name (default: `song.mp3`).

**Mode 1: Freeform**
- Type one prompt directly

**Mode 2: Structured**
- Fill guided fields for genre, mood, BPM, vocals, instrumentation, etc.
- Option for instrumental-only mode

**Mode 3: Advanced**
- All structured fields
- Custom lyrics with section tags
- Timestamp-based structure
- Image input (up to 10 images)
- Output format selection (MP3/WAV)

Before generation starts, the tool displays:
- Prompt preview panel
- Starting generation line with output paths

## Output files

If your output file is `song.mp3`, the tool writes:

- `song.mp3` - generated audio
- `song.txt` - lyrics/transcript text (when returned)

## Prompt building API

The script includes reusable components:

- `SongSpec` dataclass - structured prompt inputs
- `build_lyria_prompt(spec: SongSpec) -> str` - builds natural Lyria prompt
- `generate_song(prompt, output_file, output_format, image_paths)` - core generation
- `generate_song_from_spec(spec: SongSpec, output_file) -> str` - convenience wrapper

### Example: Basic programmatic usage

```python
from lyria import SongSpec, generate_song_from_spec

spec = SongSpec(
    genre="cinematic",
    mood="uplifting, emotional",
    bpm=100,
    vocals="expressive female lead vocal",
    language="English",
    instrumentation=["shimmering pads", "punchy drums", "warm bass"],
    structure=["intro", "verse", "chorus", "bridge", "final chorus", "outro"],
    lyrical_theme="rebuilding after a storm and finding hope again",
)

transcript = generate_song_from_spec(spec, output_file="cinematic-pop.mp3")
```

### Example: Custom lyrics

```python
spec = SongSpec(
    genre="indie pop",
    mood="dreamy, nostalgic",
    custom_lyrics="""[Verse 1]
Walking through the neon glow,
city lights reflect below,

[Chorus]
We are the echoes in the night,
burning brighter than the light,

[Verse 2]
Footsteps lost on empty streets,
rhythms sync to heartbeats.""",
)

transcript = generate_song_from_spec(spec, output_file="echoes.mp3")
```

### Example: Timestamp-based structure

```python
spec = SongSpec(
    genre="lo-fi hip hop",
    instrumental_only=True,
    timestamped_structure=[
        {"start": "0:00", "end": "0:10", "description": "Intro: vinyl crackle and mellow chords"},
        {"start": "0:10", "end": "0:40", "description": "Main beat: boom-bap drums and jazzy piano"},
        {"start": "0:40", "end": "1:00", "description": "Outro: fade with piano melody"},
    ],
)

transcript = generate_song_from_spec(spec, output_file="lofi-beat.mp3")
```

### Example: Image-to-music

```python
spec = SongSpec(
    genre="ambient",
    mood="atmospheric, cinematic",
    instrumentation=["strings", "pads", "subtle percussion"],
    image_paths=["sunset.jpg", "desert.png"],
)

transcript = generate_song_from_spec(spec, output_file="visual-ambient.mp3")
```

### Example: WAV output format

```python
spec = SongSpec(
    genre="orchestral",
    mood="epic, cinematic",
    output_format="wav",
)

transcript = generate_song_from_spec(spec, output_file="epic-score.wav")
```

## Progress view

During generation, two progress rows display:

- **Stream status** - event count and elapsed time
- **Audio status** - chunks received and approximate size

When complete, both rows show green checkmarks, followed by saved file logs.

## Advanced features

### Instrumental-only mode

Set `instrumental_only=True` to enforce no vocals:

```python
spec = SongSpec(
    genre="ambient",
    instrumental_only=True,
    instrumentation=["piano", "strings"],
)
```

### Custom lyrics with section tags

Provide full lyrics with structure tags:

```python
spec = SongSpec(
    genre="pop",
    custom_lyrics="""[Intro]
Piano melody...

[Verse 1]
First verse lyrics...

[Chorus]
Chorus lyrics...""",
)
```

### Timestamp-based structure

Control exact timing of song segments:

```python
spec = SongSpec(
    timestamped_structure=[
        {"start": "0:00", "end": "0:15", "description": "Intro: soft piano"},
        {"start": "0:15", "end": "0:45", "description": "Verse: add vocals"},
        {"start": "0:45", "end": "1:15", "description": "Chorus: full band"},
    ],
)
```

### Image input

Provide up to 10 images for visual inspiration:

```python
spec = SongSpec(
    genre="ambient",
    image_paths=["sunset.jpg", "ocean.png", "mountains.webp"],
)
```

Supported formats: JPEG, PNG, GIF, WebP

## Troubleshooting

- **Missing key**
  - Error: `Missing PORTKEY_API_KEY. Add it to your .env file.`
  - Fix: set `PORTKEY_API_KEY` in `.env`.

- **Unauthorized (401)**
  - Error: `Unauthorized (401). Check PORTKEY_API_KEY in your .env file.`
  - Fix: verify key value and account/model access.

- **Image not found**
  - Error: `Image not found: path/to/file.jpg`
  - Fix: verify image path is correct and file exists.

- **Too many images**
  - Error: `Max 10 images allowed, got N`
  - Fix: reduce to 10 or fewer images.

- **Invalid timestamp**
  - Error: `Invalid start timestamp: X`
  - Fix: use format `M:SS` (e.g., `0:00`, `1:30`, `2:15`).

- **Appears slow before audio starts**
  - The API streams text/metadata events before audio chunks arrive.
  - This is expected; stream event counters should still move.

- **No audio data received**
  - Retry with a clearer prompt and confirm model access permissions.

## Security note

- Keep `.env` private.
- Never commit real API keys.
- Generated audio and lyrics files are ignored by `.gitignore` by default.
