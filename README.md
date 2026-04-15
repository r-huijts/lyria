# Lyria Song Generator

A small Python CLI tool that generates a song using the Lyria model via Portkey/OpenRouter, saves the audio to disk, and prints the returned transcript/lyrics.

## What This Project Does

- Sends your prompt to the Lyria model
- Streams response events from the API
- Shows live progress in the terminal using Rich
- Collects streamed audio chunks and writes an `.mp3` file
- Prints transcript/lyrics (when provided)

## Requirements

- Python 3.10+ (recommended)
- A Portkey API key with access to this model

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

Then edit `.env` and set your real key:

```bash
PORTKEY_API_KEY=your_real_key_here
```

## Run the Script

```bash
python lyria.py
```

The script will ask for:

- **Song prompt** (press Enter to use default prompt)
- **Output file name** (default: `song.mp3`)

## Example Usage

```text
Song prompt (press Enter for default): Dreamy synthwave with airy vocals and uplifting chorus
Output file (default: song.mp3): neon-dream.mp3
```

Output:

- Audio saved to your chosen file (for example, `neon-dream.mp3`)
- Transcript/lyrics printed in terminal (if present in streamed response)

## Troubleshooting

- **Missing key error**
  - `Missing PORTKEY_API_KEY. Add it to your .env file.`
  - Fix: add your key to `.env` and rerun.

- **Unauthorized (401)**
  - `Unauthorized (401). Check PORTKEY_API_KEY in your .env file.`
  - Fix: verify key is valid and has permission for this model.

- **Slow or timeout behavior**
  - The API may stream non-audio events before audio arrives.
  - You should still see event counters moving in the progress display.

- **No audio data received**
  - If stream events are received but audio is missing, retry with a clearer prompt or verify model/account access.

## Notes

- Keep `.env` private and never commit real keys.
- Generated audio files are ignored by `.gitignore` by default.
