import base64
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import requests
from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Column

console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, show_path=False, markup=True)],
)

load_dotenv()
PORTKEY_API_KEY = os.getenv("PORTKEY_API_KEY")


# ---------------------------------------------------------------------------
# Song specification
# ---------------------------------------------------------------------------

@dataclass
class SongSpec:
    """Structured description of a song to generate with Lyria.

    All fields are optional. Only the fields you set will appear in the
    generated prompt. The more detail you provide, the more directed the
    model output tends to be.
    """

    genre: Optional[str] = None
    subgenre: Optional[str] = None
    mood: Optional[str] = None
    bpm: Optional[int] = None
    key: Optional[str] = None
    vocals: Optional[str] = None
    language: Optional[str] = None
    instrumentation: Optional[list[str]] = field(default=None)
    structure: Optional[list[str]] = field(default=None)
    lyrical_theme: Optional[str] = None
    duration: Optional[str] = None
    negative_constraints: Optional[list[str]] = field(default=None)
    reference_style: Optional[str] = None
    output_format: Optional[str] = "mp3"  # "mp3" or "wav"
    instrumental_only: bool = False  # If True, enforce no vocals
    custom_lyrics: Optional[str] = None  # Full lyrics with [Verse], [Chorus] tags
    timestamped_structure: Optional[list[dict]] = field(default=None)  # [{"start": "0:00", "end": "0:10", "description": "..."}]
    image_paths: Optional[list[str]] = field(default=None)  # Up to 10 image paths for visual inspiration


def _guess_image_mime_type(ext: str) -> str:
    """Map file extension to MIME type."""
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(ext, "image/jpeg")


def _load_images_as_base64(paths: list[str]) -> list[dict]:
    """Load image files and encode as base64 inline_data parts.

    Args:
        paths: List of image file paths (max 10)

    Returns:
        List of dicts with format: {"inline_data": {"mime_type": "...", "data": "..."}}
    """
    from pathlib import Path

    parts = []
    for path in paths[:10]:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Image not found: {path}")

        mime_type = _guess_image_mime_type(p.suffix.lower())
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")

        parts.append({
            "inline_data": {
                "mime_type": mime_type,
                "data": data,
            }
        })
    return parts


def _validate_timestamp(time_str: str) -> bool:
    """Validate format like '0:00', '1:30', '2:15'."""
    import re
    pattern = r'^\d+:[0-5]\d$'
    return bool(re.match(pattern, time_str))


def _validate_image_paths(paths: list[str]) -> None:
    """Validate image files exist and are supported formats.

    Raises:
        ValueError: If more than 10 images or unsupported format
        FileNotFoundError: If any image file doesn't exist
    """
    from pathlib import Path

    if len(paths) > 10:
        raise ValueError(f"Max 10 images allowed, got {len(paths)}")

    supported = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    for path in paths:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Image not found: {path}")
        if p.suffix.lower() not in supported:
            raise ValueError(f"Unsupported image format: {p.suffix}")


def _validate_timestamped_structure(structure: list[dict]) -> None:
    """Validate timestamp structure format.

    Raises:
        ValueError: If structure is malformed or timestamps invalid
    """
    for i, segment in enumerate(structure):
        if not all(k in segment for k in ["start", "end", "description"]):
            raise ValueError(f"Segment {i} missing required keys (start, end, description)")
        if not _validate_timestamp(segment["start"]):
            raise ValueError(f"Invalid start timestamp: {segment['start']}")
        if not _validate_timestamp(segment["end"]):
            raise ValueError(f"Invalid end timestamp: {segment['end']}")


def build_lyria_prompt(spec: SongSpec) -> str:
    """Convert a SongSpec into a natural, Lyria-optimised prompt string.

    The output reads like a deliberate creative brief, not serialised data.
    Only fields that are set are included. An 'Avoid:' line is appended when
    negative_constraints is provided.

    Args:
        spec: A populated SongSpec instance.

    Returns:
        A multi-line prompt string ready to send to the Lyria model.
    """
    genre_parts = [p for p in (spec.genre, spec.subgenre) if p]
    genre_label = " ".join(genre_parts) if genre_parts else None

    headline = (
        f"Create a full-length {genre_label} song."
        if genre_label
        else "Create a full-length song."
    )

    lines: list[str] = [headline, ""]

    if spec.mood:
        lines.append(f"Mood: {spec.mood}.")

    if spec.bpm:
        lines.append(f"Tempo: around {spec.bpm} BPM.")

    if spec.key:
        lines.append(f"Key: {spec.key}.")

    # Handle instrumental_only flag
    if spec.instrumental_only:
        lines.append("Instrumental only, no vocals.")
    else:
        if spec.vocals:
            vocal_line = spec.vocals
            if spec.language:
                vocal_line = f"{vocal_line} in {spec.language}"
            lines.append(f"Vocals: {vocal_line}.")
        elif spec.language:
            lines.append(f"Language: {spec.language}.")

    if spec.instrumentation:
        lines.append(f"Instrumentation: {', '.join(spec.instrumentation)}.")

    # Handle timestamped structure (takes precedence over free-form structure)
    if spec.timestamped_structure:
        lines.append("")
        for segment in spec.timestamped_structure:
            lines.append(f"[{segment['start']} - {segment['end']}] {segment['description']}")
        lines.append("")
    elif spec.structure:
        lines.append(f"Structure: {', '.join(spec.structure)}.")

    if spec.lyrical_theme:
        lines.append(f"Lyrics theme: {spec.lyrical_theme}.")

    # Handle custom lyrics with section tags
    if spec.custom_lyrics:
        lines.append("")
        lines.append(spec.custom_lyrics)
        lines.append("")

    if spec.duration:
        lines.append(f"Duration: {spec.duration}.")

    if spec.reference_style:
        lines.append(f"Style reference: {spec.reference_style}.")

    if spec.negative_constraints:
        lines.append(f"Avoid: {', '.join(spec.negative_constraints)}.")

    return "\n".join(lines)


def _fmt_bytes(n: int) -> str:
    """Format a byte count as a human-readable string."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} MB"
    if n >= 1_000:
        return f"{n / 1_000:.0f} KB"
    return f"{n} B"


def generate_song(
    prompt: str,
    output_file: str = "song.mp3",
    output_format: str = "mp3",
    image_paths: Optional[list[str]] = None,
) -> str:
    """Generate a song from a text prompt using Lyria 3 Pro.

    Args:
        prompt: Text description of the song to generate
        output_file: Path to save the generated audio file
        output_format: Audio format - "mp3" or "wav"
        image_paths: Optional list of image file paths (max 10) for visual inspiration

    Returns:
        The lyrics/transcript text returned by the model
    """
    if not PORTKEY_API_KEY:
        raise RuntimeError(
            "Missing PORTKEY_API_KEY. Add it to your .env file."
        )

    # Auto-detect format from file extension if not explicitly set
    if output_file.endswith(".wav") and output_format == "mp3":
        output_format = "wav"
    elif output_file.endswith(".mp3") and output_format == "wav":
        output_format = "mp3"

    # Validate image inputs if provided
    if image_paths:
        _validate_image_paths(image_paths)

    url = "https://api.portkey.ai/v1/chat/completions"

    headers = {
        "x-portkey-api-key": PORTKEY_API_KEY,
        "x-portkey-custom-host": "https://openrouter.ai/api",
        "Content-Type": "application/json",
    }

    # Build message - use 'content' for text-only, 'parts' for multimodal
    if image_paths:
        message_parts = [{"text": prompt}]
        image_parts = _load_images_as_base64(image_paths)
        message_parts.extend(image_parts)
        
        payload = {
            "model": "lyria",
            "messages": [
                {
                    "role": "user",
                    "parts": message_parts,
                }
            ],
            "modalities": ["text", "audio"],
            "audio": {
                "format": output_format,
            },
            "stream": True,
        }
    else:
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
                "format": output_format,
            },
            "stream": True,
        }

    audio_chunks = []
    transcript_chunks = []
    stream_event_count = 0
    audio_event_count = 0
    audio_base64_chars = 0

    desc_col = TextColumn(
        "{task.description}",
        table_column=Column(min_width=24, no_wrap=True),
    )
    detail_col = TextColumn(
        "[dim]{task.fields[detail]}[/dim]",
        table_column=Column(min_width=28, no_wrap=True),
    )
    progress = Progress(
        SpinnerColumn(finished_text="[green]✓[/green]"),
        desc_col,
        detail_col,
        TimeElapsedColumn(),
        console=console,
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
                stream_task = progress.add_task(
                    "[cyan]Connecting...[/cyan]",
                    total=None,
                    detail="",
                )
                audio_task = progress.add_task(
                    "[dim]Audio payload[/dim]",
                    total=None,
                    detail="waiting...",
                    visible=False,
                )

                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if not line.startswith("data: "):
                        continue

                    data = line[len("data: "):].strip()
                    if data == "[DONE]":
                        approx_bytes = audio_base64_chars * 3 // 4
                        chunks_label = f"{audio_event_count} chunk{'s' if audio_event_count != 1 else ''}"
                        progress.update(
                            stream_task,
                            description="[green]Stream complete[/green]",
                            detail=f"{stream_event_count} events received",
                            completed=1,
                            total=1,
                        )
                        progress.update(
                            audio_task,
                            description="[green]Audio received[/green]",
                            detail=f"{chunks_label}  ·  {_fmt_bytes(approx_bytes)}",
                            completed=1,
                            total=1,
                        )
                        break

                    stream_event_count += 1
                    progress.update(
                        stream_task,
                        description="[cyan]Processing stream[/cyan]",
                        detail=f"{stream_event_count} events",
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
                        approx_bytes = audio_base64_chars * 3 // 4
                        chunks_label = f"{audio_event_count} chunk{'s' if audio_event_count != 1 else ''}"
                        if not progress.tasks[audio_task].visible:
                            progress.update(audio_task, visible=True)
                        progress.update(
                            audio_task,
                            description="[cyan]Receiving audio[/cyan]",
                            detail=f"{chunks_label}  ·  {_fmt_bytes(approx_bytes)}",
                        )

                    # Lyrics arrive as streamed text via delta.content (text modality).
                    # delta.audio.transcript is kept as a fallback for other providers.
                    content = delta.get("content")
                    if content:
                        transcript_chunks.append(content)
                    elif audio.get("transcript"):
                        transcript_chunks.append(audio["transcript"])
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

    console.log(f"[green]Saved audio[/green] → [yellow]{output_file}[/yellow]")

    lyrics_file = os.path.splitext(output_file)[0] + ".txt"
    if full_transcript:
        with open(lyrics_file, "w", encoding="utf-8") as lf:
            lf.write(full_transcript)
        console.log(f"[green]Saved lyrics[/green] → [yellow]{lyrics_file}[/yellow]")

    return full_transcript


def generate_song_from_spec(spec: SongSpec, output_file: str = "song.mp3") -> str:
    """Build a Lyria prompt from a SongSpec and generate the song.

    Convenience wrapper around build_lyria_prompt + generate_song.

    Args:
        spec: A populated SongSpec instance.
        output_file: Path to write the generated audio file.

    Returns:
        The transcript/lyrics string returned by the model (may be empty).
    """
    # Validate timestamped structure if provided
    if spec.timestamped_structure:
        _validate_timestamped_structure(spec.timestamped_structure)

    prompt = build_lyria_prompt(spec)
    output_format = spec.output_format or "mp3"
    return generate_song(
        prompt,
        output_file=output_file,
        output_format=output_format,
        image_paths=spec.image_paths,
    )


# ---------------------------------------------------------------------------
# Example specs (for reference / quick testing)
# ---------------------------------------------------------------------------

EXAMPLE_CINEMATIC_SYNTH_POP = SongSpec(
    genre="cinematic",
    subgenre="synth-pop",
    mood="uplifting, emotional, expansive",
    bpm=100,
    key="D minor",
    vocals="expressive female lead vocal",
    language="English",
    instrumentation=[
        "shimmering pads",
        "punchy drums",
        "warm bass",
        "airy synth arpeggios",
    ],
    structure=[
        "intro",
        "verse",
        "pre-chorus",
        "chorus",
        "verse",
        "chorus",
        "bridge",
        "final chorus",
        "outro",
    ],
    lyrical_theme="rebuilding after a storm and finding hope again",
    duration="around 2 minutes 30 seconds",
    reference_style="polished modern synth-pop with cinematic energy",
    negative_constraints=[
        "distorted guitars",
        "lo-fi texture",
        "spoken word",
        "overly sparse arrangement",
    ],
)

EXAMPLE_AMBIENT_PIANO = SongSpec(
    genre="ambient",
    subgenre="contemporary classical",
    mood="serene, introspective, meditative",
    bpm=60,
    key="C major",
    vocals=None,
    instrumentation=[
        "solo piano",
        "soft string pads",
        "subtle reverb tails",
        "gentle room ambience",
    ],
    structure=["open intro", "slow melodic development", "quiet resolution"],
    lyrical_theme=None,
    duration="around 3 minutes",
    reference_style="Nils Frahm or Max Richter — minimal, emotional, cinematic",
    negative_constraints=["drums", "vocals", "electronic beats", "bass guitar"],
)

EXAMPLE_INSTRUMENTAL_AMBIENT = SongSpec(
    genre="ambient",
    mood="serene, meditative, peaceful",
    bpm=60,
    instrumental_only=True,
    instrumentation=["piano", "soft strings", "gentle nature sounds"],
    duration="around 3 minutes",
    reference_style="Brian Eno, Stars of the Lid",
)

EXAMPLE_TIMESTAMPED_LOFI = SongSpec(
    genre="lo-fi hip hop",
    instrumental_only=True,
    timestamped_structure=[
        {"start": "0:00", "end": "0:10", "description": "Intro: vinyl crackle and mellow chords"},
        {"start": "0:10", "end": "0:40", "description": "Main beat: boom-bap drums and jazzy piano"},
        {"start": "0:40", "end": "1:00", "description": "Outro: fade with piano melody"},
    ],
)

EXAMPLE_CUSTOM_LYRICS = SongSpec(
    genre="indie pop",
    mood="dreamy, nostalgic",
    custom_lyrics="""[Verse 1]
Walking through the neon glow,
city lights reflect below,
every shadow tells a story,
every corner, fading glory.

[Chorus]
We are the echoes in the night,
burning brighter than the light,
hold on tight, don't let me go,
we are the echoes down below.

[Verse 2]
Footsteps lost on empty streets,
rhythms sync to heartbeats,
whispers carried by the breeze,
dancing through the autumn leaves.""",
)


def _print_generation_start(prompt: str, output_file: str) -> None:
    """Print a startup panel summarising what's about to be generated."""
    lyrics_file = os.path.splitext(output_file)[0] + ".txt"
    console.print()
    console.print(Panel(
        prompt,
        title="[bold cyan]Prompt[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
    ))
    console.print(
        f"[bold green]▶ Starting generation[/bold green]  "
        f"audio → [yellow]{output_file}[/yellow]  "
        f"lyrics → [yellow]{lyrics_file}[/yellow]"
    )
    console.print()


if __name__ == "__main__":
    console.print("\n[bold]Lyria Song Generator[/bold]")
    console.print("\nQuick presets:")
    console.print("  [cyan]p1[/cyan] Full song   [cyan]p2[/cyan] Instrumental   [cyan]p3[/cyan] Custom lyrics")
    console.print("\nOr choose a mode:")
    console.print("  [cyan][1][/cyan] Freeform   - write your own prompt")
    console.print("  [cyan][2][/cyan] Structured - guided basic fields")
    console.print("  [cyan][3][/cyan] Advanced   - custom lyrics, timestamps, images")
    
    choice = input("\nChoice (1/2/3 or preset, default 1): ").strip() or "1"

    output_file = input("Output file (default: song.mp3): ").strip() or "song.mp3"
    
    spec = None
    prompt = None

    # Handle presets
    if choice == "p1":
        spec = EXAMPLE_CINEMATIC_SYNTH_POP
        console.print("\n[green]Loaded preset:[/green] Full cinematic synth-pop song")
    elif choice == "p2":
        spec = EXAMPLE_INSTRUMENTAL_AMBIENT
        console.print("\n[green]Loaded preset:[/green] Instrumental ambient track")
    elif choice == "p3":
        spec = EXAMPLE_CUSTOM_LYRICS
        console.print("\n[green]Loaded preset:[/green] Indie pop with custom lyrics")
    elif choice == "2":
        # Structured mode - basic fields only
        console.print("\n[dim]Press Enter to skip any field.[/dim]\n")
        
        instrumental = input("Instrumental only? (y/n, default n): ").strip().lower() == "y"
        
        spec = SongSpec(
            genre=input(
                "Genre\n"
                "  e.g. synth-pop, ambient, jazz, hip-hop, folk, R&B, classical, EDM, lo-fi\n"
                "> "
            ).strip() or None,
            subgenre=input(
                "Subgenre (optional)\n"
                "  e.g. dream pop, nu-jazz, dark ambient, indie folk, trap soul\n"
                "> "
            ).strip() or None,
            mood=input(
                "Mood\n"
                "  e.g. uplifting, melancholic, tense, dreamy, euphoric, nostalgic, cinematic\n"
                "> "
            ).strip() or None,
            bpm=int(v) if (v := input(
                "Tempo in BPM (optional)\n"
                "  e.g. 70 (slow), 90 (mid), 120 (dance), 140 (energetic)\n"
                "> "
            ).strip()) else None,
            key=input(
                "Key (optional)\n"
                "  e.g. C major, D minor, F# major, B♭ major, G minor, A dorian\n"
                "> "
            ).strip() or None,
            vocals=None if instrumental else input(
                "Vocals (optional)\n"
                "  e.g. expressive female lead, warm male baritone, ethereal choir,\n"
                "       raspy male vocal, soft androgynous voice, spoken-word narrator\n"
                "> "
            ).strip() or None,
            language=None if instrumental else input(
                "Language (optional)\n"
                "  e.g. English, French, Spanish, Japanese, Portuguese\n"
                "> "
            ).strip() or None,
            instrumentation=(
                [i.strip() for i in v.split(",") if i.strip()]
                if (v := input(
                    "Instrumentation — comma-separated (optional)\n"
                    "  e.g. piano, punchy drums, warm bass, shimmering pads,\n"
                    "       acoustic guitar, string quartet, muted trumpet, 808 bass\n"
                    "> "
                ).strip())
                else None
            ),
            structure=(
                [s.strip() for s in v.split(",") if s.strip()]
                if (v := input(
                    "Song structure — comma-separated (optional)\n"
                    "  e.g. intro, verse, pre-chorus, chorus, bridge, outro\n"
                    "       or: intro, A section, B section, A section, coda\n"
                    "> "
                ).strip())
                else None
            ),
            lyrical_theme=None if instrumental else input(
                "Lyrical theme (optional)\n"
                "  e.g. rebuilding after heartbreak, late-night city loneliness,\n"
                "       chasing a dream, the peace of solitude, a letter to your younger self\n"
                "> "
            ).strip() or None,
            duration=input(
                "Duration (optional)\n"
                "  e.g. around 2 minutes, around 3 minutes 30 seconds, under 4 minutes\n"
                "> "
            ).strip() or None,
            reference_style=input(
                "Style reference (optional)\n"
                "  e.g. Radiohead meets Hans Zimmer, early Billie Eilish, Nils Frahm,\n"
                "       90s trip-hop, Ennio Morricone, Frank Ocean, Portishead\n"
                "> "
            ).strip() or None,
            negative_constraints=(
                [c.strip() for c in v.split(",") if c.strip()]
                if (v := input(
                    "Avoid — comma-separated (optional)\n"
                    "  e.g. distorted guitars, lo-fi texture, spoken word, drums,\n"
                    "       auto-tune, brass section, overly sparse arrangement\n"
                    "> "
                ).strip())
                else None
            ),
            instrumental_only=instrumental,
        )
    elif choice == "3":
        # Advanced mode - all features
        console.print("\n[bold cyan]Advanced Mode[/bold cyan]")
        console.print("[dim]Press Enter to skip any field.[/dim]\n")
        
        instrumental = input("Instrumental only? (y/n, default n): ").strip().lower() == "y"
        
        genre = input(
            "Genre\n"
            "  e.g. synth-pop, ambient, jazz, hip-hop, folk, R&B, classical, EDM, lo-fi\n"
            "> "
        ).strip() or None
        
        subgenre = input(
            "Subgenre (optional)\n"
            "  e.g. dream pop, nu-jazz, dark ambient, indie folk, trap soul\n"
            "> "
        ).strip() or None
        
        mood = input(
            "Mood\n"
            "  e.g. uplifting, melancholic, tense, dreamy, euphoric, nostalgic, cinematic\n"
            "> "
        ).strip() or None
        
        bpm = int(v) if (v := input(
            "Tempo in BPM (optional)\n"
            "  e.g. 70 (slow), 90 (mid), 120 (dance), 140 (energetic)\n"
            "> "
        ).strip()) else None
        
        key = input(
            "Key (optional)\n"
            "  e.g. C major, D minor, F# major, B♭ major, G minor, A dorian\n"
            "> "
        ).strip() or None
        
        vocals = None if instrumental else input(
            "Vocals (optional)\n"
            "  e.g. expressive female lead, warm male baritone, ethereal choir\n"
            "> "
        ).strip() or None
        
        language = None if instrumental else input(
            "Language (optional)\n"
            "  e.g. English, French, Spanish, Japanese, Portuguese\n"
            "> "
        ).strip() or None
        
        instrumentation = (
            [i.strip() for i in v.split(",") if i.strip()]
            if (v := input(
                "Instrumentation — comma-separated (optional)\n"
                "  e.g. piano, drums, bass, pads, guitar, strings\n"
                "> "
            ).strip())
            else None
        )
        
        # Advanced: custom lyrics or timestamped structure
        console.print("\n[bold]Advanced Options[/bold]")
        
        use_custom_lyrics = input("Provide custom lyrics? (y/n, default n): ").strip().lower() == "y"
        custom_lyrics = None
        if use_custom_lyrics and not instrumental:
            console.print("\n[dim]Enter lyrics with section tags like [Verse 1], [Chorus], [Bridge].[/dim]")
            console.print("[dim]Type 'END' on a new line when finished:[/dim]\n")
            lyrics_lines = []
            while True:
                line = input()
                if line.strip() == "END":
                    break
                lyrics_lines.append(line)
            custom_lyrics = "\n".join(lyrics_lines)
        
        use_timestamps = input("Use timestamp-based structure? (y/n, default n): ").strip().lower() == "y"
        timestamped_structure = None
        structure = None
        if use_timestamps:
            console.print("\n[dim]Enter segments in format: START END DESCRIPTION[/dim]")
            console.print("[dim]Example: 0:00 0:10 Intro: soft piano and strings[/dim]")
            console.print("[dim]Type 'END' on a new line when finished:[/dim]\n")
            segments = []
            while True:
                line = input("> ").strip()
                if line == "END":
                    break
                if line:
                    parts = line.split(None, 2)
                    if len(parts) >= 3:
                        segments.append({
                            "start": parts[0],
                            "end": parts[1],
                            "description": parts[2],
                        })
            timestamped_structure = segments if segments else None
        else:
            structure = (
                [s.strip() for s in v.split(",") if s.strip()]
                if (v := input(
                    "Song structure — comma-separated (optional)\n"
                    "  e.g. intro, verse, pre-chorus, chorus, bridge, outro\n"
                    "> "
                ).strip())
                else None
            )
        
        lyrical_theme = None if instrumental or custom_lyrics else input(
            "Lyrical theme (optional)\n"
            "  e.g. rebuilding after heartbreak, chasing a dream, solitude\n"
            "> "
        ).strip() or None
        
        duration = input(
            "Duration (optional)\n"
            "  e.g. around 2 minutes, around 3 minutes 30 seconds\n"
            "> "
        ).strip() or None
        
        reference_style = input(
            "Style reference (optional)\n"
            "  e.g. Radiohead meets Hans Zimmer, Nils Frahm, Frank Ocean\n"
            "> "
        ).strip() or None
        
        negative_constraints = (
            [c.strip() for c in v.split(",") if c.strip()]
            if (v := input(
                "Avoid — comma-separated (optional)\n"
                "  e.g. distorted guitars, spoken word, drums, auto-tune\n"
                "> "
            ).strip())
            else None
        )
        
        # Image paths
        image_paths = None
        use_images = input("\nAdd images for visual inspiration? (y/n, default n): ").strip().lower() == "y"
        if use_images:
            image_paths = (
                [p.strip() for p in v.split(",") if p.strip()]
                if (v := input(
                    "Image paths — comma-separated (max 10)\n"
                    "  e.g. sunset.jpg, desert.png, abstract.webp\n"
                    "> "
                ).strip())
                else None
            )
        
        # Output format
        output_format = input(
            "\nOutput format (mp3/wav, default mp3): "
        ).strip().lower() or "mp3"
        
        spec = SongSpec(
            genre=genre,
            subgenre=subgenre,
            mood=mood,
            bpm=bpm,
            key=key,
            vocals=vocals,
            language=language,
            instrumentation=instrumentation,
            structure=structure,
            lyrical_theme=lyrical_theme,
            duration=duration,
            negative_constraints=negative_constraints,
            reference_style=reference_style,
            output_format=output_format,
            instrumental_only=instrumental,
            custom_lyrics=custom_lyrics,
            timestamped_structure=timestamped_structure,
            image_paths=image_paths,
        )
    else:
        # Freeform mode
        default_prompt = (
            "Create a full-length cinematic synth-pop song with a huge chorus and female vocals."
        )
        console.print("\n[dim]Describe your song in plain language. Press Enter to use the default.[/dim]")
        console.print(f"[dim]Default: {default_prompt}[/dim]\n")
        prompt = input("> ").strip() or default_prompt

    # Generate from spec or prompt
    if spec:
        prompt = build_lyria_prompt(spec)
        _print_generation_start(prompt, output_file)
        try:
            transcript = generate_song_from_spec(spec, output_file=output_file)
        except (RuntimeError, ValueError, FileNotFoundError) as err:
            console.print(f"[red]Error:[/red] {err}")
        else:
            if transcript:
                console.print("\n[bold]Transcript / lyrics:[/bold]")
                console.print(transcript)
            else:
                console.print("\n[dim]No transcript returned by the model.[/dim]")
    else:
        _print_generation_start(prompt, output_file)
        try:
            transcript = generate_song(prompt, output_file=output_file)
        except (RuntimeError, ValueError, FileNotFoundError) as err:
            console.print(f"[red]Error:[/red] {err}")
        else:
            if transcript:
                console.print("\n[bold]Transcript / lyrics:[/bold]")
                console.print(transcript)
            else:
                console.print("\n[dim]No transcript returned by the model.[/dim]")