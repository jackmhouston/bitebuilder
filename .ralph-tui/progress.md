# Ralph Progress Log

This file tracks progress across iterations. Agents update this file
after each iteration and it's included in prompts for context.

## Codebase Patterns (Study These First)

*Add reusable patterns discovered during development here.*

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
