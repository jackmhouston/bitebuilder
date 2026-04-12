"""Prompt and validation helpers for sequence-plan refinement.

These helpers prepare a future Gemma refinement pass without invoking a model.
They keep the contract strict: model output must be a complete sequence_plan.v1
JSON object that validates against exact transcript segment boundaries.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Mapping, Sequence

from generator.sequence_plan import SCHEMA_VERSION, SequencePlan, SequencePlanValidationError
from parser.transcript import TranscriptSegment


class SequencePlanRefinementError(ValueError):
    """Raised when refined sequence-plan model output violates the contract."""


def _segment_reference_lines(transcript_segments: Sequence[TranscriptSegment]) -> str:
    lines = []
    for index, segment in enumerate(transcript_segments):
        speaker = f" | {segment.speaker}" if segment.speaker else ""
        lines.append(
            f"[{index}] {segment.tc_in} - {segment.tc_out}{speaker}\n"
            f"    {segment.text}"
        )
    return "\n\n".join(lines)


def build_sequence_plan_refinement_prompt(
    *,
    current_plan: Mapping[str, Any],
    transcript_segments: Sequence[TranscriptSegment],
    instruction: str,
    target_option_id: str | None = None,
    max_bite_duration_seconds: float | None = None,
    max_total_duration_seconds: float | None = None,
    require_changed_selected_cuts: bool = False,
    constraint_feedback: Mapping[str, Any] | None = None,
) -> str:
    """Build a strict prompt for revising a full sequence_plan.v1 object."""
    plan_copy = deepcopy(dict(current_plan))
    options = plan_copy.get("options") or []
    default_option_id = options[0].get("option_id") if options and isinstance(options[0], Mapping) else None
    target = target_option_id or default_option_id or "the first option"
    constraint_lines = []
    if max_bite_duration_seconds is not None:
        constraint_lines.append(f"- Every selected bite should be at or below {max_bite_duration_seconds:g} seconds.")
    if max_total_duration_seconds is not None:
        constraint_lines.append(f"- Total selected duration should be at or below {max_total_duration_seconds:g} seconds.")
    if require_changed_selected_cuts:
        constraint_lines.append("- The revised selected cuts must differ from the current selected cuts.")
    constraints_text = "\n".join(constraint_lines) if constraint_lines else "- No additional duration/change constraints supplied."
    feedback_text = ""
    if constraint_feedback is not None:
        feedback_text = (
            "\n\nPrevious refined plan failed editorial constraints. "
            "Fix every violation in this JSON feedback:\n"
            f"{json.dumps(dict(constraint_feedback), indent=2, sort_keys=True)}"
        )

    return f"""You are revising a BiteBuilder sequence plan.

Return ONLY valid JSON. Do not return Markdown fences, prose, XML, diffs, patches, comments, or partial updates.
Return a COMPLETE {SCHEMA_VERSION} object, not a delta.

User refinement instruction:
{instruction}{feedback_text}

Target option:
{target}

Rules:
- Use only exact complete transcript segments listed below.
- Do not invent segment_index values.
- segment_index is zero-based.
- Do not trim, split, or alter timecodes.
- If the user asks for shorter bites, replace long bites with shorter complete transcript segments.
- Valid bite statuses are "selected" and "removed" only.
- Follow these additional duration/change constraints:
{constraints_text}
- Preserve replaces_bite_id as metadata only; do not apply replacement behavior.
- If a target option is specified, revise that option and preserve unrelated options unless the instruction explicitly says otherwise.
- Keep schema_version exactly "{SCHEMA_VERSION}".

Current sequence plan JSON:
{json.dumps(plan_copy, indent=2, sort_keys=True)}

Transcript segment references:
{_segment_reference_lines(transcript_segments)}
""".strip()


def _parse_refined_payload(refined_output: str | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(refined_output, str):
        stripped = refined_output.strip()
        if not stripped.startswith("{") or not stripped.endswith("}"):
            raise SequencePlanRefinementError("Refined sequence plan must be a raw JSON object with no prose or Markdown wrapping.")
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise SequencePlanRefinementError(f"Refined sequence plan is not valid JSON: {exc}") from exc
    elif isinstance(refined_output, Mapping):
        payload = deepcopy(dict(refined_output))
    else:
        raise SequencePlanRefinementError("Refined sequence plan must be a JSON object or mapping.")

    if not isinstance(payload, dict):
        raise SequencePlanRefinementError("Refined sequence plan must be a JSON object.")
    return payload


def validate_refined_sequence_plan(
    refined_output: str | Mapping[str, Any],
    *,
    transcript_segments: Sequence[TranscriptSegment],
) -> SequencePlan:
    """Parse and validate a full refined sequence-plan response."""
    payload = _parse_refined_payload(refined_output)

    if payload.get("schema_version") != SCHEMA_VERSION:
        raise SequencePlanRefinementError(f"Refined sequence plan must use schema_version {SCHEMA_VERSION!r}.")

    options = payload.get("options")
    if not isinstance(options, list) or not options:
        raise SequencePlanRefinementError("Refined sequence plan must include a non-empty options list.")

    try:
        return SequencePlan.from_dict(payload, transcript_segments=transcript_segments)
    except SequencePlanValidationError as exc:
        raise SequencePlanRefinementError(str(exc)) from exc
