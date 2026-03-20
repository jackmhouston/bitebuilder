from __future__ import annotations

import re
from pathlib import Path

from bitebuilder.models import TranscriptDocument, TranscriptSegment

BRACKET_TIMECODE = re.compile(
    r"^\[(?P<start>\d{2}:\d{2}:\d{2}(?:[.,]\d{1,3})?)(?:\s*-\s*(?P<end>\d{2}:\d{2}:\d{2}(?:[.,]\d{1,3})?))?\]\s*(?P<text>.+)$"
)
INLINE_TIMECODE = re.compile(
    r"^(?P<start>\d{2}:\d{2}:\d{2}(?:[.,]\d{1,3})?)(?:\s*-\s*(?P<end>\d{2}:\d{2}:\d{2}(?:[.,]\d{1,3})?))?\s*(?:\||:|-)\s*(?P<text>.+)$"
)


def parse_transcript(path: str | Path) -> TranscriptDocument:
    source_path = Path(path).expanduser().resolve()
    segments: list[TranscriptSegment] = []

    for raw_line in source_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parsed = _parse_timed_line(line)
        if parsed is None:
            segments.append(
                TranscriptSegment(index=len(segments) + 1, text=line)
            )
            continue
        start_seconds, end_seconds, text = parsed
        segments.append(
            TranscriptSegment(
                index=len(segments) + 1,
                text=text,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
            )
        )

    if not segments:
        raise ValueError(f"Transcript file is empty: {source_path}")

    return TranscriptDocument(source_path=source_path, segments=segments)


def _parse_timed_line(line: str) -> tuple[float, float | None, str] | None:
    for pattern in (BRACKET_TIMECODE, INLINE_TIMECODE):
        match = pattern.match(line)
        if not match:
            continue
        start = _timecode_to_seconds(match.group("start"))
        end = match.group("end")
        return start, _timecode_to_seconds(end) if end else None, match.group("text").strip()
    return None


def _timecode_to_seconds(value: str) -> float:
    hours, minutes, seconds = value.replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)

