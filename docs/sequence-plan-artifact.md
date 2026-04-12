# Sequence Plan Artifact

The sequence plan is the planned intermediate artifact between LLM bite selection and Premiere/XMEML generation.

It is intentionally data-first: future refinement can remove, swap, search, and regenerate from this structure before any web UI or chat command layer is rebuilt.

## Goals

- Preserve the editorial intent that produced a sequence.
- Keep selected bites ordered and addressable.
- Store exact transcript segment references and timecodes.
- Support future replacement/removal semantics without appending new bites blindly.
- Keep enough metadata to regenerate XML deterministically.

## Draft JSON Shape

```json
{
  "schema_version": "sequence_plan.v1",
  "project_context": "Interview footage about a solar panel company and its CEO.",
  "goal": "Create an engaging 7 minute narrative that is insightful and not negative.",
  "speaker_names": {
    "Speaker 1": "CEO",
    "Speaker 2": "Interviewer"
  },
  "source": {
    "transcript": {
      "sha256": "...",
      "segment_count": 42
    },
    "premiere_xml": {
      "sha256": "...",
      "source_name": "interview.mov",
      "timebase": 30,
      "ntsc": true
    }
  },
  "options": [
    {
      "option_id": "option-1",
      "name": "Cohesive CEO narrative",
      "estimated_duration_seconds": 420,
      "bites": [
        {
          "bite_id": "bite-001",
          "segment_index": 12,
          "tc_in": "00:01:22:10",
          "tc_out": "00:01:38:04",
          "speaker": "CEO",
          "text": "Exact transcript text for this bite.",
          "purpose": "opening hook",
          "rationale": "Why this bite belongs here.",
          "status": "selected",
          "replaces_bite_id": null,
          "source_action": "llm_first_pass"
        }
      ]
    }
  ],
  "revision_log": [
    {
      "revision": 1,
      "action": "llm_first_pass",
      "summary": "Initial sequence plan generated from user goal."
    }
  ]
}
```

## Future Refinement Semantics

Future refinement should update bite records in-place instead of concatenating new material at the end:

- **Remove**: mark a bite `status: "removed"` and record the revision reason.
- **Swap**: add a replacement bite with `replaces_bite_id` pointing to the original bite.
- **Search**: return candidate transcript segment IDs without mutating the plan until accepted.
- **Regenerate XML**: render only bites with active/selected status, preserving current order.

## Non-goals for the current tranche

- Do not implement a chat interface.
- Do not implement multi-turn refinement commands yet.
- Do not make the web UI depend on this artifact yet.
- Do not add new dependencies.

## Implemented API

The current core implementation lives in `generator/sequence_plan.py` and keeps the draft JSON shape intact:

- `SequencePlan`, `SequencePlanOption`, and `SequencePlanBite` model the artifact in memory.
- `build_sequence_plan(...)` constructs a validated plan from option dictionaries and zero-based `TranscriptSegment` references.
- `SequencePlan.from_dict(..., transcript_segments=...)` and `SequencePlan.to_dict()` provide JSON-safe round-trip behavior.
- `SequencePlan.to_cuts(option_id=None)` returns only `status: "selected"` bites as `[{"tc_in": ..., "tc_out": ...}]` dictionaries for `generator.xmeml.generate_sequence`.
- Valid bite statuses are `selected` and `removed`; removed bites remain in the artifact but are omitted from XMEML-ready cuts.
- `replaces_bite_id` is preserved as metadata only. The module does not apply replacement/swap behavior in this tranche.

`segment_index` is zero-based and must exactly reference the transcript segment whose `tc_in` and `tc_out` match the bite. Invalid indexes, mismatched timecode pairs, unknown statuses, and missing bite identifiers fail fast with `SequencePlanValidationError`.

## Rendering a saved plan

Phase 2 adds a non-LLM render path for saved plans:

```bash
.venv/bin/python bitebuilder.py \
  --sequence-plan output/run/_sequence_plan.json \
  --transcript path/to/transcript.txt \
  --xml path/to/source.xml \
  --output output/plan-render \
  --option-id option-1
```

Notes:

- `--option-id` is optional; when omitted, the first option renders.
- This mode does not require `--brief`, model, host, timeout, or Ollama.
- The source plan is not mutated.
- Successful renders write an XML file plus `_sequence_plan_render.json` metadata.

## Evaluating refinement constraints

Phase 5 adds pure editorial constraint checks in `generator/sequence_plan_constraints.py`.

Use `evaluate_sequence_plan_constraints(...)` to detect when a structurally valid revised plan still fails editorial instructions such as "make this shorter":

- `bite_duration_exceeds_max` when a selected bite is longer than the configured max bite duration.
- `total_duration_exceeds_max` when selected bite duration exceeds the configured max total duration.
- `selected_cuts_unchanged` when `require_changed_selected_cuts=True` and the selected `(segment_index, tc_in, tc_out, status)` tuples match the previous plan.

These checks do not call Gemma and do not render XML. They produce JSON-safe results intended for future retry prompts.
