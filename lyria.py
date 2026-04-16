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

    if spec.vocals:
        vocal_line = spec.vocals
        if spec.language:
            vocal_line = f"{vocal_line} in {spec.language}"
        lines.append(f"Vocals: {vocal_line}.")
    elif spec.language:
        lines.append(f"Language: {spec.language}.")

    if spec.instrumentation:
        lines.append(f"Instrumentation: {', '.join(spec.instrumentation)}.")

    if spec.structure:
        lines.append(f"Structure: {', '.join(spec.structure)}.")

    if spec.lyrical_theme:
        lines.append(f"Lyrics theme: {spec.lyrical_theme}.")

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
    prompt = build_lyria_prompt(spec)
    return generate_song(prompt, output_file=output_file)


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
    console.print("How do you want to build your prompt?")
    console.print("  [cyan][1][/cyan] Freeform   — write your own prompt")
    console.print("  [cyan][2][/cyan] Structured — fill in individual fields")
    mode = input("Choice (1 or 2, default 1): ").strip() or "1"

    output_file = input("Output file (default: song.mp3): ").strip() or "song.mp3"

    if mode == "2":
        console.print("\n[dim]Press Enter to skip any field.[/dim]\n")
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
            vocals=input(
                "Vocals (optional — leave blank for instrumental)\n"
                "  e.g. expressive female lead, warm male baritone, ethereal choir,\n"
                "       raspy male vocal, soft androgynous voice, spoken-word narrator\n"
                "> "
            ).strip() or None,
            language=input(
                "Language (optional)\n"
                "  e.g. English, French, Spanish, Japanese, Portuguese, no lyrics\n"
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
            lyrical_theme=input(
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
        )
        prompt = build_lyria_prompt(spec)
        _print_generation_start(prompt, output_file)
        try:
            transcript = generate_song(prompt, output_file=output_file)
        except RuntimeError as err:
            console.print(f"[red]Error:[/red] {err}")
        else:
            if transcript:
                console.print("\n[bold]Transcript / lyrics:[/bold]")
                console.print(transcript)
            else:
                console.print("\n[dim]No transcript returned by the model.[/dim]")
    else:
        default_prompt = (
            "Create a full-length cinematic synth-pop song with a huge chorus and female vocals."
        )
        console.print("\n[dim]Describe your song in plain language. Press Enter to use the default.[/dim]")
        console.print(f"[dim]Default: {default_prompt}[/dim]\n")
        prompt = input("> ").strip() or default_prompt
        _print_generation_start(prompt, output_file)
        try:
            transcript = generate_song(prompt, output_file=output_file)
        except RuntimeError as err:
            console.print(f"[red]Error:[/red] {err}")
        else:
            if transcript:
                console.print("\n[bold]Transcript / lyrics:[/bold]")
                console.print(transcript)
            else:
                console.print("\n[dim]No transcript returned by the model.[/dim]")