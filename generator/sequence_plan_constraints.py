"""Editorial constraint evaluation for sequence plans.

These helpers deliberately sit beside schema validation.  A SequencePlan can be
structurally valid while still failing an editorial instruction like "make this
shorter"; this module produces JSON-safe evidence for those failures without
calling a model or rendering XML.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from generator.sequence_plan import SequencePlan, SequencePlanBite, SequencePlanValidationError
from generator.timecode import estimate_duration_seconds
from parser.transcript import TranscriptSegment


@dataclass
class SequencePlanConstraintViolation:
    code: str
    message: str
    bite_id: str | None = None
    segment_index: int | None = None
    actual_seconds: float | None = None
    limit_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        optional = {
            "bite_id": self.bite_id,
            "segment_index": self.segment_index,
            "actual_seconds": self.actual_seconds,
            "limit_seconds": self.limit_seconds,
        }
        data.update({key: value for key, value in optional.items() if value is not None})
        return data


@dataclass
class SequencePlanConstraintResult:
    option_id: str
    selected_bite_count: int
    total_duration_seconds: float
    max_bite_duration_seconds: float | None = None
    max_total_duration_seconds: float | None = None
    changed_selected_cuts: bool | None = None
    violations: list[SequencePlanConstraintViolation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def passes(self) -> bool:
        return not self.violations

    def to_dict(self) -> dict[str, Any]:
        return {
            "passes": self.passes,
            "option_id": self.option_id,
            "selected_bite_count": self.selected_bite_count,
            "total_duration_seconds": self.total_duration_seconds,
            "max_bite_duration_seconds": self.max_bite_duration_seconds,
            "max_total_duration_seconds": self.max_total_duration_seconds,
            "changed_selected_cuts": self.changed_selected_cuts,
            "violations": [violation.to_dict() for violation in self.violations],
            "warnings": list(self.warnings),
            "stats": deepcopy(self.stats),
        }


def _coerce_plan(
    plan: SequencePlan | Mapping[str, Any],
    transcript_segments: Sequence[TranscriptSegment] | None,
) -> SequencePlan:
    if isinstance(plan, SequencePlan):
        return plan
    if transcript_segments is None:
        raise SequencePlanValidationError("transcript_segments are required when evaluating a mapping sequence plan")
    return SequencePlan.from_dict(deepcopy(dict(plan)), transcript_segments=transcript_segments)


def _selected_cut_signature(bites: Sequence[SequencePlanBite]) -> list[tuple[int, str, str, str]]:
    return [
        (bite.segment_index, bite.tc_in, bite.tc_out, bite.status)
        for bite in bites
    ]


def evaluate_sequence_plan_constraints(
    *,
    current_plan: SequencePlan | Mapping[str, Any],
    previous_plan: SequencePlan | Mapping[str, Any] | None = None,
    transcript_segments: Sequence[TranscriptSegment] | None = None,
    option_id: str | None = None,
    timebase: int = 24,
    ntsc: bool = True,
    max_bite_duration_seconds: float | None = None,
    max_total_duration_seconds: float | None = None,
    require_changed_selected_cuts: bool = False,
) -> SequencePlanConstraintResult:
    """Evaluate editorial duration/change constraints for a sequence-plan option."""
    plan = _coerce_plan(current_plan, transcript_segments)
    option = plan.option(option_id)
    selected_bites = option.selected_bites()

    violations: list[SequencePlanConstraintViolation] = []
    by_bite: list[dict[str, Any]] = []
    total_duration = 0.0
    for bite in selected_bites:
        duration = estimate_duration_seconds(bite.tc_in, bite.tc_out, timebase, ntsc)
        total_duration += duration
        by_bite.append({
            "bite_id": bite.bite_id,
            "segment_index": bite.segment_index,
            "tc_in": bite.tc_in,
            "tc_out": bite.tc_out,
            "duration_seconds": duration,
            "status": bite.status,
        })
        if max_bite_duration_seconds is not None and duration > max_bite_duration_seconds:
            violations.append(SequencePlanConstraintViolation(
                code="bite_duration_exceeds_max",
                message=f"Bite {bite.bite_id} duration {duration:.3f}s exceeds max {max_bite_duration_seconds:.3f}s.",
                bite_id=bite.bite_id,
                segment_index=bite.segment_index,
                actual_seconds=duration,
                limit_seconds=max_bite_duration_seconds,
            ))

    if max_total_duration_seconds is not None and total_duration > max_total_duration_seconds:
        violations.append(SequencePlanConstraintViolation(
            code="total_duration_exceeds_max",
            message=f"Selected bite duration {total_duration:.3f}s exceeds max {max_total_duration_seconds:.3f}s.",
            actual_seconds=total_duration,
            limit_seconds=max_total_duration_seconds,
        ))

    changed_selected_cuts = None
    if previous_plan is not None:
        previous = _coerce_plan(previous_plan, transcript_segments)
        previous_option = previous.option(option.option_id)
        changed_selected_cuts = _selected_cut_signature(previous_option.selected_bites()) != _selected_cut_signature(selected_bites)
        if require_changed_selected_cuts and not changed_selected_cuts:
            violations.append(SequencePlanConstraintViolation(
                code="selected_cuts_unchanged",
                message="Selected cuts did not change from the previous sequence plan option.",
            ))

    return SequencePlanConstraintResult(
        option_id=option.option_id,
        selected_bite_count=len(selected_bites),
        total_duration_seconds=total_duration,
        max_bite_duration_seconds=max_bite_duration_seconds,
        max_total_duration_seconds=max_total_duration_seconds,
        changed_selected_cuts=changed_selected_cuts,
        violations=violations,
        stats={"by_bite": by_bite},
    )
