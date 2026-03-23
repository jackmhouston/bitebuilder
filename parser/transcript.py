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


@dataclass
class TranscriptSegment:
    tc_in: str
    tc_out: str
    speaker: str
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


# Match timecode pairs: "00:14:31:11 - 00:14:42:02"
TC_PATTERN = re.compile(
    r'(\d{2}:\d{2}:\d{2}:\d{2})\s*-\s*(\d{2}:\d{2}:\d{2}:\d{2})'
)

# Match speaker labels: "Speaker 1", "Speaker 2", "Unknown"
SPEAKER_PATTERN = re.compile(
    r'^(Speaker\s+\d+|Unknown)\s*$', re.IGNORECASE
)


def parse_transcript(text: str) -> list[TranscriptSegment]:
    """
    Parse a timecoded transcript string into a list of segments.

    Args:
        text: Raw transcript text

    Returns:
        List of TranscriptSegment objects, ordered by tc_in
    """
    lines = text.strip().split('\n')
    segments = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Look for a timecode line
        tc_match = TC_PATTERN.search(line)
        if tc_match:
            tc_in = tc_match.group(1)
            tc_out = tc_match.group(2)

            # Next line should be speaker
            speaker = "Unknown"
            i += 1
            if i < len(lines):
                speaker_match = SPEAKER_PATTERN.match(lines[i].strip())
                if speaker_match:
                    speaker = speaker_match.group(1)
                    i += 1

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

            # Only include segments with actual dialogue
            if dialogue:
                segments.append(TranscriptSegment(
                    tc_in=tc_in,
                    tc_out=tc_out,
                    speaker=speaker,
                    text=dialogue
                ))
        else:
            i += 1

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
