from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class TranscriptSegment:
    index: int
    text: str
    start_seconds: float | None = None
    end_seconds: float | None = None


@dataclass(slots=True)
class TranscriptDocument:
    source_path: Path
    segments: list[TranscriptSegment] = field(default_factory=list)


@dataclass(slots=True)
class SourceClip:
    clip_id: str
    name: str
    file_id: str | None = None
    file_name: str | None = None
    path_url: str | None = None
    masterclip_id: str | None = None
    start_frame: int = 0
    end_frame: int = 0
    in_frame: int = 0
    out_frame: int = 0


@dataclass(slots=True)
class PremiereProject:
    source_path: Path
    sequence_name: str
    fps: int = 30
    clips: list[SourceClip] = field(default_factory=list)


@dataclass(slots=True)
class SelectionCandidate:
    transcript_index: int
    quote: str
    reason: str
    source_clip_id: str | None = None
    source_clip_name: str | None = None
    duration_seconds: float | None = None


@dataclass(slots=True)
class GenerationRequest:
    transcript_path: Path
    premiere_xml_path: Path
    brief: str
    output_path: Path
    sequence_title: str = "BiteBuilder Selects"
    model: str = "gemma3:12b"
    ollama_url: str = "http://127.0.0.1:11434"
    dry_run: bool = False


@dataclass(slots=True)
class GenerationResult:
    output_path: Path
    sequence_title: str
    selected_count: int
    warnings: list[str] = field(default_factory=list)

