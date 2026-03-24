"""
Parse timecoded interview transcripts.

Expected format:
    HH:MM:SS:FF - HH:MM:SS:FF
    Speaker N
    Dialogue text that may span
    multiple lines...

    HH:MM:SS:FF - HH:MM:SS:FF
    Speaker N
    Next segment...
"""

import re
from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class TranscriptSegment:
    tc_in: str
    tc_out: str
    speaker: str
    text: str
    start_line: int = 1
    end_line: int = 1

    def to_dict(self) -> dict:
        return asdict(self)


# Match strict timecode pairs: "00:14:31:11 - 00:14:42:02"
TC_PATTERN = re.compile(
    r"^\s*(\d{2}:\d{2}:\d{2}:\d{2})\s*-\s*(\d{2}:\d{2}:\d{2}:\d{2})\s*$"
)

# Match likely timecode-like lines so malformed values can be reported with context.
TC_HINT_PATTERN = re.compile(
    r"\d{2}:\d{2}:\d{2}:\d+"
)


class TranscriptValidationError(ValueError):
    """
    Raised when a transcript contains malformed timecodes.

    Each error contains line-level detail with a short context string.
    """

    def __init__(self, errors: list[dict[str, Any]]):
        self.errors = errors
        summary = "; ".join(error["message"] for error in errors[:2])
        super().__init__(f"Transcript validation failed: {summary}")


def _line_context(line: str, line_number: int) -> str:
    text = line.strip()
    if len(text) > 120:
        text = text[:117] + "..."
    return f"line {line_number}: {text}"


def _normalize_and_validate_timecode(
    value: str,
    line_number: int,
    errors: list[dict[str, Any]],
) -> tuple[int, int, int, int] | None:
    match = re.match(r"^(\d{2}):(\d{2}):(\d{2}):(\d{2})$", value)
    if not match:
        errors.append({
            "line": line_number,
            "field": "timecode",
            "message": f"Invalid timecode format '{value}'. Expected HH:MM:SS:FF (2 digits each).",
            "context": _line_context(value, line_number),
        })
        return None

    hh, mm, ss, ff = map(int, match.groups())
    if mm > 59:
        errors.append({
            "line": line_number,
            "field": "timecode",
            "message": f"Invalid minutes '{value}'. Minutes must be 00-59.",
            "context": _line_context(value, line_number),
        })
    if ss > 59:
        errors.append({
            "line": line_number,
            "field": "timecode",
            "message": f"Invalid seconds '{value}'. Seconds must be 00-59.",
            "context": _line_context(value, line_number),
        })
    if hh > 99:
        errors.append({
            "line": line_number,
            "field": "timecode",
            "message": f"Invalid hours '{value}'. Hours must be 00-99 for parser compatibility.",
            "context": _line_context(value, line_number),
        })
    return hh, mm, ss, ff


def _timecode_to_tuple(tc: str) -> tuple[int, int, int, int]:
    hh, mm, ss, ff = map(int, tc.split(":"))
    return hh, mm, ss, ff

# Match speaker labels: "Speaker 1", "Speaker 2", "Unknown"
SPEAKER_PATTERN = re.compile(
    r'^(Speaker\s+\d+|Unknown)\s*$', re.IGNORECASE
)


def parse_transcript(
    text: str,
    *,
    strict: bool = False,
    timebase: int | None = None,
    ntsc: bool = False,
) -> list[TranscriptSegment]:
    """
    Parse a timecoded transcript string into a list of segments.

    Args:
        text: Raw transcript text

    Returns:
        List of TranscriptSegment objects, ordered by tc_in
    """
    _ = ntsc

    if not text:
        if strict:
            raise TranscriptValidationError([{
                "line": 0,
                "field": "transcript",
                "message": "Transcript is empty.",
                "context": "line 1: <empty transcript>",
            }])
        return []

    lines = text.strip().split('\n')
    segments = []
    errors: list[dict[str, Any]] = []
    seen_start_map: dict[str, tuple[int, int]] = {}

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Look for a timecode line
        tc_match = TC_PATTERN.match(line)
        if tc_match:
            tc_in = tc_match.group(1)
            tc_out = tc_match.group(2)
            start_line = i + 1
            end_line = i + 1
            in_components = _normalize_and_validate_timecode(
                tc_in,
                start_line,
                errors,
            )
            out_components = _normalize_and_validate_timecode(
                tc_out,
                start_line,
                errors,
            )
            if in_components is None or out_components is None:
                i += 1
                while i < len(lines) and lines[i].strip():
                    i += 1
                continue

            # Next line should be speaker
            speaker = "Unknown"
            i += 1
            if i < len(lines):
                speaker_match = SPEAKER_PATTERN.match(lines[i].strip())
                if speaker_match:
                    speaker = speaker_match.group(1)
                    i += 1

            dialogue_start = i
            # Collect dialogue lines until next timecode or end
            dialogue_lines = []
            while i < len(lines):
                next_line = lines[i].strip()
                if TC_PATTERN.search(next_line):
                    break  # Hit next segment
                if next_line:  # Skip blank lines
                    dialogue_lines.append(next_line)
                i += 1

            dialogue = ' '.join(dialogue_lines).strip()
            end_line = max(dialogue_start, i)

            if not dialogue:
                if strict:
                    errors.append({
                        "line": start_line,
                        "field": "transcript_block",
                        "message": f"Segment {start_line} has no dialogue text.",
                        "context": _line_context(line, start_line),
                    })
                continue

            in_tup = _timecode_to_tuple(tc_in)
            out_tup = _timecode_to_tuple(tc_out)
            if in_tup >= out_tup:
                errors.append({
                    "line": start_line,
                    "field": "time_range",
                    "message": f"Invalid segment range: tc_in ({tc_in}) must be before tc_out ({tc_out}).",
                    "context": _line_context(line, start_line),
                })

            in_key = f"{tc_in}-{tc_out}"
            if in_key in seen_start_map:
                errors.append({
                    "line": start_line,
                    "field": "duplicate_segment",
                    "message": f"Duplicate segment range '{tc_in} - {tc_out}'.",
                    "context": _line_context(line, start_line),
                })
            else:
                seen_start_map[in_key] = (start_line, end_line)

            if segments:
                prev = segments[-1]
                prev_out = _timecode_to_tuple(prev.tc_out)
                if prev_out > in_tup:
                    errors.append({
                        "line": start_line,
                        "field": "time_transition",
                        "message": (
                            f"Impossible transition: segment '{tc_in} - {tc_out}' starts at {tc_in} "
                            f"before previous segment ended at {prev.tc_out}."
                        ),
                        "context": f"lines {prev.start_line}-{start_line}",
                    })

            if timebase is not None and in_components is not None and out_components is not None:
                if in_components[3] >= timebase:
                    errors.append({
                        "line": start_line,
                        "field": "timecode",
                        "message": f"Frame number '{in_components[3]}' exceeds timebase '{timebase}'.",
                        "context": _line_context(line, start_line),
                    })
                if out_components[3] >= timebase:
                    errors.append({
                        "line": start_line,
                        "field": "timecode",
                        "message": f"Frame number '{out_components[3]}' exceeds timebase '{timebase}'.",
                        "context": _line_context(line, start_line),
                    })
            # Only include segments with actual dialogue
            segments.append(TranscriptSegment(
                tc_in=tc_in,
                tc_out=tc_out,
                speaker=speaker,
                text=dialogue,
                start_line=start_line,
                end_line=end_line,
            ))
        else:
            if strict and line and TC_HINT_PATTERN.search(line):
                errors.append({
                    "line": i + 1,
                    "field": "timecode_line",
                    "message": "Invalid timecode pair line format. Expected 'HH:MM:SS:FF - HH:MM:SS:FF'.",
                    "context": _line_context(line, i + 1),
                })
            i += 1

    if strict and errors:
        raise TranscriptValidationError(errors)

    return segments


def parse_transcript_file(filepath: str) -> list[TranscriptSegment]:
    """
    Parse a transcript from a file path.

    Args:
        filepath: Path to the .txt transcript file

    Returns:
        List of TranscriptSegment objects
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        return parse_transcript(f.read())


def format_for_llm(segments: list[TranscriptSegment]) -> str:
    """
    Format transcript segments into a clean string for LLM consumption.
    Includes segment index numbers for easy reference.

    Args:
        segments: List of TranscriptSegment objects

    Returns:
        Formatted string with numbered segments
    """
    lines = []
    for idx, seg in enumerate(segments):
        lines.append(
            f"[{idx}] {seg.tc_in} - {seg.tc_out} | {seg.speaker}\n"
            f"    \"{seg.text}\""
        )
    return '\n\n'.join(lines)


def get_valid_timecodes(segments: list[TranscriptSegment]) -> set[str]:
    """
    Extract all valid timecode boundaries from the transcript.
    Used for validating LLM output.

    Returns:
        Set of timecode strings that appear as in or out points
    """
    tcs = set()
    for seg in segments:
        tcs.add(seg.tc_in)
        tcs.add(seg.tc_out)
    return tcs
