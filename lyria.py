import base64
import json
import logging
import os
import requests
from dotenv import load_dotenv
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

logging.basicConfig(level=logging.INFO)

load_dotenv()
PORTKEY_API_KEY = os.getenv("PORTKEY_API_KEY")


def generate_song(prompt: str, output_file: str = "song.mp3") -> str:
    if not PORTKEY_API_KEY:
        raise RuntimeError(
            "Missing PORTKEY_API_KEY. Add it to your .env file."
        )

    url = "https://api.portkey.ai/v1/chat/completions"

    headers = {
        "x-portkey-api-key": PORTKEY_API_KEY,
        "x-portkey-custom-host": "https://openrouter.ai/api",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "lyria",
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "modalities": ["text", "audio"],
        "audio": {
            "format": "mp3",
        },
        "stream": True,
    }

    audio_chunks = []
    transcript_chunks = []
    stream_event_count = 0
    audio_event_count = 0
    audio_base64_chars = 0

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TextColumn("events: {task.fields[events]}"),
        TextColumn("audio chunks: {task.fields[audio_chunks]}"),
        TextColumn("audio chars: {task.fields[audio_chars]}"),
        TimeElapsedColumn(),
    )

    try:
        with requests.post(
            url,
            headers=headers,
            json=payload,
            stream=True,
            timeout=(20, 120),
        ) as response:
            response.raise_for_status()

            with progress:
                task_id = progress.add_task(
                    "Connecting to stream...",
                    total=None,
                    events=0,
                    audio_chunks=0,
                    audio_chars=0,
                )
                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if not line.startswith("data: "):
                        continue

                    data = line[len("data: "):].strip()
                    if data == "[DONE]":
                        progress.update(task_id, description="Stream complete.")
                        logging.info("Stream finished.")
                        break

                    stream_event_count += 1
                    progress.update(
                        task_id,
                        description="Receiving streamed events...",
                        events=stream_event_count,
                    )

                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        logging.warning("Skipping malformed JSON chunk.")
                        continue

                    choice = chunk.get("choices", [{}])[0]
                    delta = choice.get("delta", {})
                    audio = delta.get("audio", {})

                    # Some providers may place audio on message instead of delta.
                    if not audio:
                        audio = choice.get("message", {}).get("audio", {})

                    audio_data = audio.get("data")
                    if audio_data:
                        audio_chunks.append(audio_data)
                        audio_event_count += 1
                        audio_base64_chars += len(audio_data)
                        progress.update(
                            task_id,
                            description="Receiving audio payload...",
                            audio_chunks=audio_event_count,
                            audio_chars=audio_base64_chars,
                        )

                    transcript = audio.get("transcript")
                    if transcript:
                        transcript_chunks.append(transcript)
    except requests.exceptions.ReadTimeout as exc:
        raise RuntimeError(
            "Timed out while waiting for streamed response data. "
            "The model may still be generating; try again or increase timeout."
        ) from exc
    except requests.exceptions.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code == 401:
            raise RuntimeError(
                "Unauthorized (401). Check PORTKEY_API_KEY in your .env file."
            ) from exc
        raise RuntimeError(f"HTTP error while generating song: {exc}") from exc

    if not audio_chunks:
        raise RuntimeError(
            f"No audio data received from the API. Received {stream_event_count} stream events."
        )

    full_audio_base64 = "".join(audio_chunks)
    audio_bytes = base64.b64decode(full_audio_base64)

    with open(output_file, "wb") as f:
        f.write(audio_bytes)

    full_transcript = "".join(transcript_chunks)

    logging.info("Saved audio to %s", output_file)
    return full_transcript


if __name__ == "__main__":
    default_prompt = (
        "Create a full-length cinematic synth-pop song with a huge chorus and female vocals."
    )
    prompt = input("Song prompt (press Enter for default): ").strip() or default_prompt
    output_file = input("Output file (default: song.mp3): ").strip() or "song.mp3"

    try:
        transcript = generate_song(prompt, output_file=output_file)
    except RuntimeError as err:
        print(f"Error: {err}")
    else:
        print("Transcript / lyrics:")
        print(transcript)