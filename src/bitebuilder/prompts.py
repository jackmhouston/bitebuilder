from __future__ import annotations

from bitebuilder.models import GenerationRequest, PremiereProject, TranscriptDocument


def build_selection_prompt(
    request: GenerationRequest,
    transcript: TranscriptDocument,
    project: PremiereProject,
    max_segments: int = 40,
    max_clips: int = 25,
) -> str:
    segment_lines = []
    for segment in transcript.segments[:max_segments]:
        time_range = _format_time_range(segment.start_seconds, segment.end_seconds)
        segment_lines.append(f"{segment.index}. {time_range} {segment.text}".strip())

    clip_lines = []
    for clip in project.clips[:max_clips]:
        path_hint = clip.file_name or clip.path_url or "unknown-file"
        clip_lines.append(f"- {clip.clip_id}: {clip.name} [{path_hint}]")

    return f"""
You are an editor building a short-form bite-select sequence from a transcript and a Premiere project export.

Creative brief:
{request.brief}

Constraints:
- Pick 3 to 8 transcript moments.
- Build a clear beginning, middle, and ending.
- Prefer emotionally specific, self-contained lines.
- Avoid redundant beats and vague filler.
- Keep the total runtime tight.
- Match picks to source clips when you can infer them from the metadata.

Transcript segments:
{chr(10).join(segment_lines)}

Available source clips:
{chr(10).join(clip_lines)}

Return only valid JSON in this exact shape:
{{
  "title": "Short sequence title",
  "creative_rationale": "1-2 sentence summary",
  "selected_segments": [
    {{
      "transcript_index": 1,
      "quote": "exact or near-exact quote",
      "reason": "why this moment belongs",
      "source_clip_id": "clipitem-1",
      "source_clip_name": "optional clip name",
      "duration_seconds": 4.0
    }}
  ]
}}
""".strip()


def _format_time_range(start_seconds: float | None, end_seconds: float | None) -> str:
    if start_seconds is None:
        return ""
    if end_seconds is None:
        return f"[{start_seconds:0.2f}s]"
    return f"[{start_seconds:0.2f}s-{end_seconds:0.2f}s]"

