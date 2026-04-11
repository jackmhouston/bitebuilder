"""Pure sequence-plan artifact helpers.

The sequence plan is the small data boundary between LLM bite selection and
XMEML generation.  It intentionally has no runtime, web, or Ollama coupling:
callers pass transcript segments in, receive JSON-safe dictionaries out, and
render selected bites as the cut dictionaries consumed by ``generate_sequence``.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from parser.transcript import TranscriptSegment


SCHEMA_VERSION = "sequence_plan.v1"
SELECTED_STATUS = "selected"
REMOVED_STATUS = "removed"
VALID_BITE_STATUSES = frozenset({SELECTED_STATUS, REMOVED_STATUS})


class SequencePlanValidationError(ValueError):
    """Raised when a sequence-plan bite does not match the transcript contract."""


@dataclass
class SequencePlanBite:
    """A single ordered, addressable bite in a sequence-plan option."""

    bite_id: str
    segment_index: int
    tc_in: str
    tc_out: str
    speaker: str | None = None
    text: str | None = None
    dialogue_summary: str | None = None
    purpose: str | None = None
    confidence: float | int | None = None
    rationale: str | None = None
    status: str = SELECTED_STATUS
    replaces_bite_id: str | None = None
    source_action: str | None = None

    def __post_init__(self) -> None:
        if self.status not in VALID_BITE_STATUSES:
            raise SequencePlanValidationError(
                f"Unknown bite status {self.status!r}; expected one of {sorted(VALID_BITE_STATUSES)}"
            )
        if isinstance(self.segment_index, bool) or not isinstance(self.segment_index, int):
            raise SequencePlanValidationError("segment_index must be a zero-based integer")
        if self.segment_index < 0:
            raise SequencePlanValidationError("segment_index must be zero-based and non-negative")
        if not self.bite_id:
            raise SequencePlanValidationError("bite_id is required")
        if not self.tc_in or not self.tc_out:
            raise SequencePlanValidationError("tc_in and tc_out are required")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SequencePlanBite":
        return cls(
            bite_id=str(data.get("bite_id") or ""),
            segment_index=data.get("segment_index"),
            tc_in=str(data.get("tc_in") or ""),
            tc_out=str(data.get("tc_out") or ""),
            speaker=data.get("speaker"),
            text=data.get("text"),
            dialogue_summary=data.get("dialogue_summary"),
            purpose=data.get("purpose"),
            confidence=data.get("confidence"),
            rationale=data.get("rationale"),
            status=data.get("status", SELECTED_STATUS),
            replaces_bite_id=data.get("replaces_bite_id"),
            source_action=data.get("source_action"),
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "bite_id": self.bite_id,
            "segment_index": self.segment_index,
            "tc_in": self.tc_in,
            "tc_out": self.tc_out,
            "status": self.status,
        }
        optional = {
            "speaker": self.speaker,
            "text": self.text,
            "dialogue_summary": self.dialogue_summary,
            "purpose": self.purpose,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "replaces_bite_id": self.replaces_bite_id,
            "source_action": self.source_action,
        }
        data.update({key: value for key, value in optional.items() if value is not None})
        return data

    def to_cut(self) -> dict[str, str]:
        """Return the XMEML-ready cut representation for this bite."""
        return {"tc_in": self.tc_in, "tc_out": self.tc_out}


@dataclass
class SequencePlanOption:
    """An ordered candidate sequence made of bite records."""

    option_id: str
    name: str | None = None
    estimated_duration_seconds: float | int | None = None
    bites: list[SequencePlanBite] = field(default_factory=list)
    description: str | None = None

    def __post_init__(self) -> None:
        if not self.option_id:
            raise SequencePlanValidationError("option_id is required")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SequencePlanOption":
        return cls(
            option_id=str(data.get("option_id") or ""),
            name=data.get("name"),
            estimated_duration_seconds=data.get("estimated_duration_seconds"),
            description=data.get("description"),
            bites=[SequencePlanBite.from_dict(bite) for bite in data.get("bites", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "option_id": self.option_id,
            "bites": [bite.to_dict() for bite in self.bites],
        }
        optional = {
            "name": self.name,
            "description": self.description,
            "estimated_duration_seconds": self.estimated_duration_seconds,
        }
        data.update({key: value for key, value in optional.items() if value is not None})
        return data

    def selected_bites(self) -> list[SequencePlanBite]:
        return [bite for bite in self.bites if bite.status == SELECTED_STATUS]

    def to_cuts(self) -> list[dict[str, str]]:
        """Return selected bites as the cut dictionaries expected by XMEML generation."""
        return [bite.to_cut() for bite in self.selected_bites()]


@dataclass
class SequencePlan:
    """JSON-safe sequence-plan artifact."""

    options: list[SequencePlanOption]
    schema_version: str = SCHEMA_VERSION
    project_context: str | None = None
    goal: str | None = None
    speaker_names: dict[str, str] = field(default_factory=dict)
    source: dict[str, Any] = field(default_factory=dict)
    revision_log: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        transcript_segments: Sequence[TranscriptSegment] | None = None,
    ) -> "SequencePlan":
        plan = cls(
            schema_version=str(data.get("schema_version") or SCHEMA_VERSION),
            project_context=data.get("project_context"),
            goal=data.get("goal"),
            speaker_names=dict(data.get("speaker_names") or {}),
            source=deepcopy(dict(data.get("source") or {})),
            options=[SequencePlanOption.from_dict(option) for option in data.get("options", [])],
            revision_log=deepcopy(list(data.get("revision_log") or [])),
        )
        if transcript_segments is not None:
            plan.validate(transcript_segments)
        return plan

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_version": self.schema_version,
            "options": [option.to_dict() for option in self.options],
        }
        optional = {
            "project_context": self.project_context,
            "goal": self.goal,
            "speaker_names": deepcopy(self.speaker_names) if self.speaker_names else None,
            "source": deepcopy(self.source) if self.source else None,
            "revision_log": deepcopy(self.revision_log) if self.revision_log else None,
        }
        data.update({key: value for key, value in optional.items() if value is not None})
        return data

    def option(self, option_id: str | None = None) -> SequencePlanOption:
        """Return the requested option, or the first option when no id is supplied."""
        if not self.options:
            raise SequencePlanValidationError("sequence plan has no options")
        if option_id is None:
            return self.options[0]
        for option in self.options:
            if option.option_id == option_id:
                return option
        raise SequencePlanValidationError(f"Unknown option_id {option_id!r}")

    def to_cuts(self, option_id: str | None = None) -> list[dict[str, str]]:
        return self.option(option_id).to_cuts()

    def validate(self, transcript_segments: Sequence[TranscriptSegment]) -> None:
        for option in self.options:
            for bite in option.bites:
                validate_bite_against_transcript(bite, transcript_segments)


def validate_bite_against_transcript(
    bite: SequencePlanBite,
    transcript_segments: Sequence[TranscriptSegment],
) -> None:
    """Validate that a bite references a real zero-based transcript segment exactly."""
    if bite.segment_index >= len(transcript_segments):
        raise SequencePlanValidationError(
            f"segment_index {bite.segment_index} is outside transcript bounds 0..{len(transcript_segments) - 1}"
        )

    segment = transcript_segments[bite.segment_index]
    if bite.tc_in != segment.tc_in or bite.tc_out != segment.tc_out:
        raise SequencePlanValidationError(
            "Bite timecodes do not match transcript segment "
            f"{bite.segment_index}: expected {segment.tc_in} - {segment.tc_out}, "
            f"got {bite.tc_in} - {bite.tc_out}"
        )


def build_sequence_plan(
    *,
    options: Iterable[Mapping[str, Any]],
    transcript_segments: Sequence[TranscriptSegment],
    project_context: str | None = None,
    goal: str | None = None,
    speaker_names: Mapping[str, str] | None = None,
    source: Mapping[str, Any] | None = None,
    revision_log: Iterable[Mapping[str, Any]] | None = None,
) -> SequencePlan:
    """Build and validate a sequence plan from model/editor option dictionaries.

    Bite ids are caller-supplied when present, otherwise deterministic and ordered
    as ``bite-001``, ``bite-002``, ... across the plan. ``replaces_bite_id`` is
    preserved as metadata only; this helper does not apply replacement behavior.
    """
    plan_options: list[SequencePlanOption] = []
    bite_counter = 1

    for option_index, option_data in enumerate(options, start=1):
        raw_bites = option_data.get("bites", [])
        bites: list[SequencePlanBite] = []
        for raw_bite in raw_bites:
            bite_payload = dict(raw_bite)
            bite_payload.setdefault("bite_id", f"bite-{bite_counter:03d}")
            bite_counter += 1
            bite = SequencePlanBite.from_dict(bite_payload)
            validate_bite_against_transcript(bite, transcript_segments)
            bites.append(bite)

        plan_options.append(SequencePlanOption(
            option_id=str(option_data.get("option_id") or f"option-{option_index}"),
            name=option_data.get("name"),
            description=option_data.get("description"),
            estimated_duration_seconds=option_data.get("estimated_duration_seconds"),
            bites=bites,
        ))

    return SequencePlan(
        project_context=project_context,
        goal=goal,
        speaker_names=dict(speaker_names or {}),
        source=deepcopy(dict(source or {})),
        options=plan_options,
        revision_log=deepcopy([dict(entry) for entry in (revision_log or [])]),
    )
