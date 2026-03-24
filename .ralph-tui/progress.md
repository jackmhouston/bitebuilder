# Ralph Progress Log

This file tracks progress across iterations. Agents update this file
after each iteration and it's included in prompts for context.

## Codebase Patterns (Study These First)

*Add reusable patterns discovered during development here.*

- ### Fixture-driven integration test pattern
- Prefer end-to-end CLI/web tests driven by files in `tests/fixtures` and patching LLM/host interactions at the highest calling layer.
- Assert deterministic payload structure (status/error codes + keys/shape), then add path-level assertions (for example generated files) on positive paths.
- Keep malformed/edge fixture coverage in one place per suite (pipeline for CLI surface, webapp for HTTP payload contract).

### Error-response pattern (CLI + Flask)
- For user-facing recoverable failures, use a single typed payload shape:
  - `code`
  - `type`
  - `message`
  - `expected_input_format`
  - `next_action`
  - optional `recoverable` and `stage`
- Raise these via a `BiteBuilderError` carrying `.error` so both CLI and Flask can log/render consistently.
- For partial recovery, include a `partial` object with current progress state and stage.
- For transcript validation, parse once with explicit `strict` mode and normalize failures into a list of `{line, field, message, context}` objects, then map directly to structured payloads before selection starts.

### Validation separation pattern (Schema + Warnings)
- Keep hard-validation and warning collections separate.
- Return hard validation errors (`validation_errors`) only when selection output violates schema or constraints.
- Track optimization/duration notices under warning metadata to avoid blocking valid generations.

### Deterministic LLM selection pattern
- Keep the same schema contract in prompt text and validator code, including explicit status values and fallback structure.
- Enforce candidate-boundary constraints using exact `tc_in`/`tc_out` pairs from shortlisted segments.
- Add explicit confidence score requirements on every cut and reject out-of-range values.


### Recoverable UI workflow pattern (webapp)
- Keep a single `state` object as the recovery source of truth for form values plus recent operation snapshots, so each failure can be resumed without re-uploading files.
- Map backend operation states into a compact stage enum and render both inline user errors plus snapshots in the shared status surface (`data-page-message`, `data-page-error`, `data-page-snapshot`).
- Use explicit recovery actions (`fix`, `retry`, `resume`) that mutate only one state transition at a time, preserving all entered values unless they are intentionally corrected.


### Deterministic artifact pattern
- Keep content identity deterministic end-to-end by threading the same ordered identity inputs through:
  - candidate ranking/sorting,
  - sequence UUID generation,
  - output naming,
  - and metadata stamping.
- Prefer `json.dumps(..., sort_keys=True, separators=(..., :))` for stable signature and deterministic IDs.


## 2026-03-23 - US-007
- Enforced deterministic candidate shortlist ordering for tie cases and deterministic fallback ordering.
- Added deterministic run metadata to pipeline output with timestamp, input hashes, parser/validator versions, and model id.
- Added metadata block injection into generated XMEML sequence XML and deterministic sequence IDs driven by content + metadata.
- Exposed run metadata through CLI and web API payloads.
- Added reproducibility coverage:
  - deterministic candidate ordering test,
  - metadata presence test in generated XML,
  - identical filename/content test across repeated identical runs.
- Files changed:
  - [bitebuilder.py](/home/dietrich001/bitebuilder/bitebuilder.py)
  - [generator/xmeml.py](/home/dietrich001/bitebuilder/generator/xmeml.py)
  - [tests/test_pipeline.py](/home/dietrich001/bitebuilder/tests/test_pipeline.py)
  - [tests/test_webapp.py](/home/dietrich001/bitebuilder/tests/test_webapp.py)
  - [.ralph-tui/progress.md](/home/dietrich001/bitebuilder/.ralph-tui/progress.md)
- **Learnings:**
  - Patterns discovered:
    - Stable IDs are reliable when generated once from ordered payloads and reused, instead of recomputing from ad-hoc string concatenations.
    - Reproducibility checks are easiest to validate by asserting sorted filename + hash tuples, not just file existence.
  - Gotchas encountered:
    - Candidate ranking must include explicit tie-break fields (`segment_index`) for equal-score and equal-duration ties.
    - Source or model metadata included in UUID payloads must be stable/ordered to avoid accidental nondeterminism.
---

## 2026-03-24 - US-005
- Implemented UI workflow status and recoverability enhancements in the Flask experience so users can see clear step progression and recover from failures without re-uploading data.
- Renamed and aligned workflow steps to: Upload, Validate, Preview/Confirm, Generate, Download.
- Added multi-channel operation visibility with per-step snapshots for:
  - received
  - validating
  - prompting
  - generating
  - finalizing
- Implemented inline error rendering on each UI page with:
  - operation/error code
  - actionable message
  - expected input format
  - next action
  - Fix inputs and Try again controls
- Wired recoverable state retention across failure paths:
  - transcript
  - XML content
  - brief context
  - chat and short list content
  - selected segment edits
- Kept generation and export flows resumable after recoverable errors by preserving server payloads and reusing cached state in page operations.
- Files changed:
  - [webapp.py](/home/dietrich001/bitebuilder/webapp.py)
  - [static/app.js](/home/dietrich001/bitebuilder/static/app.js)
  - [static/app.css](/home/dietrich001/bitebuilder/static/app.css)
  - [templates/context.html](/home/dietrich001/bitebuilder/templates/context.html)
  - [templates/copilot.html](/home/dietrich001/bitebuilder/templates/copilot.html)
  - [templates/export.html](/home/dietrich001/bitebuilder/templates/export.html)
  - [templates/generate.html](/home/dietrich001/bitebuilder/templates/generate.html)
  - [templates/intake.html](/home/dietrich001/bitebuilder/templates/intake.html)
  - [.ralph-tui/progress.md](/home/dietrich001/bitebuilder/.ralph-tui/progress.md)
- **Learnings:**
  - Patterns discovered:
    - Front-end recovery is easier when every failure writes both an error object and a resilient fallback state snapshot before a rerender.
    - Reusing the same status container (message/error/snapshot) across all workflow pages reduces template drift and makes acceptance testing easier.
    - Mapping backend error `stage` to UI operation enum in one helper keeps snapshot transitions deterministic and debuggable.
  - Gotchas encountered:
    - `refreshTranscriptSegments` path can fail during transcript parsing and needed dedicated `validate`-stage mapping, otherwise generated status stuck at stale preview state.
    - Template-level status markers were inconsistent (`data-page-status` typo and mixed containers), so page-level rendering failed silently until aligned.
    - Recovery controls had to be wired to explicit operation labels to avoid launching resume logic against stale job state.
---

## 2026-03-24 - US-004
- Added bounded one-shot LLM recovery and strict fail-safe gating before XML write.
- Added segment-definition boundary validation in `validate_llm_response` using transcript segment pairs.
- Blocked XML generation when model output fails parse/validation after retries.
- Added structured selection-retry telemetry for UI and debug artifacts:
  - `used_retry`
  - `selection_retry.attempted`
  - `selection_retry.errors`
  - `selection_retry.parse_or_validation_error`
- Updated web payload serialization and UI result card to show when correction retry occurred and why.
- Files changed:
  - [llm/prompts.py](/home/dietrich001/bitebuilder/llm/prompts.py)
  - [bitebuilder.py](/home/dietrich001/bitebuilder/bitebuilder.py)
  - [webapp.py](/home/dietrich001/bitebuilder/webapp.py)
  - [static/app.js](/home/dietrich001/bitebuilder/static/app.js)
  - [tests/test_pipeline.py](/home/dietrich001/bitebuilder/tests/test_pipeline.py)
  - [.ralph-tui/progress.md](/home/dietrich001/bitebuilder/.ralph-tui/progress.md)
- **Learnings:**
  - Patterns discovered:
    - Preserve `BiteBuilderError` in selection flow; rewrapping all exceptions hides meaningful model-output codes.
    - Separating warnings from validation failures prevents false negative pipeline aborts after a successful LLM pass.
  - Gotchas encountered:
    - Candidate/segment mismatch messages needed to explicitly include "transcript segment definition" for test and operator clarity.
    - Retry metadata is easier to use in UI debugging when captured on every generation attempt.
---

## 2026-03-24 - US-003
- Added stricter LLM guardrails for schema compliance, candidate-aligned outputs, and deterministic behavior.
- Updated selection prompts and validators to require:
  - `selection_status` (`ok` or `no_candidates`).
  - `segment_index`, exact `tc_in`/`tc_out`, `purpose`, and `confidence` per cut.
  - `no_candidate_reason` when `selection_status` is `no_candidates`.
- Added explicit valid and invalid JSON examples to the prompt, plus no-op output guidance for empty candidate sets.
- Enforced optional validation of selected cuts against the shortlist timecode pairs (`tc_in` + `tc_out`) in both `collect_candidate_validation_errors` and `validate_llm_response`.
- Added deterministic seed/temperature documentation and existing env-driven settings.
- Added explicit no-candidate fallback handling before model generation when shortlist is empty and ensured `_llm_response.json` is still written without sequence output generation.
- Files changed:
  - [llm/prompts.py](/home/dietrich001/bitebuilder/llm/prompts.py)
  - [bitebuilder.py](/home/dietrich001/bitebuilder/bitebuilder.py)
  - [tests/test_pipeline.py](/home/dietrich001/bitebuilder/tests/test_pipeline.py)
  - [README.md](/home/dietrich001/bitebuilder/README.md)
  - [.ralph-tui/progress.md](/home/dietrich001/bitebuilder/.ralph-tui/progress.md)
- **Learnings:**
  - Patterns discovered:
    - Early shortlist exhaustion should short-circuit into a typed no-candidate response before any LLM call.
    - Avoid nullable fields in variant response contracts to prevent parser ambiguity.
    - Preserve `selection_status` / `no_candidate_reason` when mutating options in post-processing.
  - Gotchas encountered:
    - `no_candidate_reason` should only appear in `no_candidates` responses; emitting it as `null` for `ok` caused test and caller ambiguity.
    - Determinism is stronger when generation settings are configured in code and documented in README for operator overrides.
    - Post-processing passes must preserve top-level schema contract, not just `options`.
---


## 2026-03-23 - US-002
- Added strict transcript timecode validation before LLM selection and XML generation, including schema checks, zero/negative ranges, overlap detection, duplicate range checks, and optional frame-bound checks when source timebase is known.
- Added parser-level `TranscriptValidationError` with deterministic line-level context (`line`, `context`) for malformed timecodes, ordering issues, and impossible transitions.
- Added strict transcript validation integration in `run_pipeline()` and relevant Flask parsing endpoints so invalid input fails before sequence output creation.
- Added deterministic timecode round-trip/fixture tests for parser and generator math.
- Files changed:
  - [parser/transcript.py](/home/dietrich001/bitebuilder/parser/transcript.py)
  - [bitebuilder.py](/home/dietrich001/bitebuilder/bitebuilder.py)
  - [webapp.py](/home/dietrich001/bitebuilder/webapp.py)
  - [generator/timecode.py](/home/dietrich001/bitebuilder/generator/timecode.py)
  - [tests/test_pipeline.py](/home/dietrich001/bitebuilder/tests/test_pipeline.py)
  - [.ralph-tui/progress.md](/home/dietrich001/bitebuilder/.ralph-tui/progress.md)
- **Learnings:**
  - Patterns discovered:
    - Strict parsing mode with structured context enables deterministic pre-LLM failure behavior and keeps web/CLI payloads consistent.
    - Parsing timebase-aware frame ceilings early prevents downstream generation-time failures for invalid timecode fragments.
    - For metadata extraction from XML parsing outputs, prefer a helper that checks attribute access first, then `to_dict()`, then dict fallback (`_source_value`) to support lightweight fixtures.
  - Gotchas encountered:
    - `parse_transcript` is used in many web paths; defaulting to permissive mode preserves current behavior while strict calls target user-facing validation paths.
    - Overlap checks must compare current `tc_in` against previous segment `tc_out` to avoid false transitions.
---

## 2026-03-23 - US-001
- Verified US-001 behavior is already implemented end-to-end in code and tests.
- Confirmed CLI and Flask both return stable machine-readable error objects for brief validation, transcript parsing/emptiness, missing/invalid input files, XML parsing failures, and unsupported content.
- Confirmed structured logs are emitted with `format_error_for_log(...)` and recovery payloads are surfaced when partial progress exists.
- Confirmed CLI exits with non-zero status on `BiteBuilderError` and prints concise remediation text with `error_code`, expected format, and next action.
- Files changed:
  - [ .ralph-tui/progress.md](/home/dietrich001/bitebuilder/.ralph-tui/progress.md)
- **Learnings:**
  - Patterns discovered:
    - Stable payload schema plus `BiteBuilderError` allows CLI and Flask to share one semantic contract for recoverability.
  - Gotchas encountered:
    - The web endpoints that rely on `parse_transcript(...)` in a few paths are safe today because parser returns an empty list for malformed content rather than raising, but this makes content invalidness map to `unsupported_file_content` only if explicitly checked for emptiness.
---

## 2026-03-23 - US-001
- Implemented structured validation and runtime errors across CLI and Flask:
  - Added shared structured payload helpers in `bitebuilder.py`:
    - `build_validation_error(...)`
    - `BiteBuilderError`
    - `format_error_for_log(...)`
  - Added validation helpers:
    - `validate_brief(...)`
    - `parse_transcript_file_bytes(...)`
    - `parse_premiere_xml_safe(...)`
  - Updated CLI `main()` and `run_pipeline(...)` to emit machine-readable error payloads, non-zero exits, and concise remediation hints.
  - Added `partial` progress reporting on recoverable failures (notably when selection or output generation fails after XML parse).
  - Updated Flask endpoints to return consistent JSON error objects (`status: error`) with stable error codes, plus recoverable status on partial generation.
- Files changed:
  - [bitebuilder.py](/home/dietrich001/bitebuilder/bitebuilder.py)
  - [webapp.py](/home/dietrich001/bitebuilder/webapp.py)
  - [tests/test_pipeline.py](/home/dietrich001/bitebuilder/tests/test_pipeline.py)
  - [tests/test_webapp.py](/home/dietrich001/bitebuilder/tests/test_webapp.py)
  - [.ralph-tui/progress.md](/home/dietrich001/bitebuilder/.ralph-tui/progress.md)
- **Learnings:**
  - Patterns discovered:
    - Centralizing error schema construction avoids divergence between CLI and HTTP paths.
    - Reusing a typed exception object (`BiteBuilderError.error`) made partial-progress propagation simple for both synchronous and background job flows.
  - Gotchas encountered:
    - Flask tests still referenced `parse_premiere_xml_string`; after replacing callers with `parse_premiere_xml_safe`, patch target paths needed test updates.
  - `rg` across missing files (`setup.cfg`, `tox.ini`, `.github`) in this repo produced noisy shell errors; use targeted file checks instead.
  - A legacy global `python` binary is absent; use `.venv/bin/python` for checks.

## 2026-03-23 - US-001
- Re-validated existing implementation against the acceptance criteria and found it already complete.
- Confirmed all required CLI/web error paths are surfaced with stable machine-readable fields and remediation hints:
  - missing/malformed file inputs
  - malformed brief
  - unsupported transcript/XML content
- Confirmed recoverable partial status is preserved when parse succeeds but generation later fails.
- Verified quality checks:
  - `.venv/bin/python -m unittest discover -s tests -v`
  - `.venv/bin/python -m compileall ...`
  - `.venv/bin/python -m py_compile ...`
- Added no code changes in this iteration; only progress log update with verification status.
- Files changed:
  - [.ralph-tui/progress.md](/home/dietrich001/bitebuilder/.ralph-tui/progress.md)
- **Learnings:**
  - Patterns discovered:
    - Keep CLI and Flask sharing one `BiteBuilderError` payload schema to minimize drift in user-facing diagnostics.
  - Gotchas encountered:
    - `mypy` and `flake8` are not installed in this environment; only compile- and test-level checks were executable.
---

## 2026-03-24 - US-006
- Added fixture-backed deterministic integration tests for CLI and web paths with mocked LLM responses.
- Added end-to-end coverage for malformed fixtures and transcript timecode edge failures with structured payload assertions.
- Ensured success and validation-failure UI orchestration paths avoid live Ollama by mocking endpoint-level LLM orchestration behavior.
- Added new fixtures:
  - `tests/fixtures/malformed_transcript.txt`
  - `tests/fixtures/invalid_premiere.xml`
- Files changed:
  - [tests/fixtures/malformed_transcript.txt](/home/dietrich001/bitebuilder/tests/fixtures/malformed_transcript.txt)
  - [tests/fixtures/invalid_premiere.xml](/home/dietrich001/bitebuilder/tests/fixtures/invalid_premiere.xml)
  - [tests/test_pipeline.py](/home/dietrich001/bitebuilder/tests/test_pipeline.py)
  - [tests/test_webapp.py](/home/dietrich001/bitebuilder/tests/test_webapp.py)
  - [.ralph-tui/progress.md](/home/dietrich001/bitebuilder/.ralph-tui/progress.md)
- **Learnings:**
  - Patterns discovered:
    - CLI shape assertions are most stable when they assert both output artifacts and `_llm_response.json` contract.
    - Fixture-level malformed inputs (timecode edge + XML parse errors) are easier to maintain than repeated inline strings.
  - Gotchas encountered:
    - `serialize_generation_result()` expects `source.to_dict()`; mocked run payloads should use a source object (not a raw dict) in web endpoint tests.
    - `parse_transcript()` can return multiple errors per line, so assertions should target the expected error field rather than full-string equality.
---
