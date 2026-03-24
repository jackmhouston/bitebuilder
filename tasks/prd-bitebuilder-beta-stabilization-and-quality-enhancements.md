# PRD: BiteBuilder Beta Stabilization and Quality Enhancements

## 1) Introduction/Overview

BiteBuilder is a local Python tool that converts timecoded interview transcripts + Premiere Pro XML exports into importable Premiere XML sequences using an Ollama-powered LLM. The current proof-of-concept works end-to-end, but production readiness is incomplete. This PRD defines a public-beta-quality upgrade focused on solo filmmakers/pilot users, with goals to stabilize workflows, improve bite selection quality, harden timecode handling, and improve integration reliability while keeping scope contained and implementation-oriented.

## 2) Goals

- Deliver a stable public beta path (target: within ~1 month) for small external pilot users.
- Improve correctness across CLI and web UI paths through robust validation and deterministic failure handling.
- Improve LLM-generated editing quality across:
  - timing consistency,
  - editorial relevance,
  - and XML schema/output format compliance.
- Upgrade workflow usability in the web UI with clearer status, step-level recoverability, and smoother editing progression.
- Expand deterministic fixture-backed integration tests for full CLI and web orchestration paths.

## 3) User Stories

### US-001: Surface and classify CLI/Web input and runtime errors
**Description:** As a solo filmmaker, I want clear, actionable errors when input or processing fails so I can recover quickly without restarting from scratch.

**Acceptance Criteria:**
- [ ] The app returns structured, user-facing errors for missing/invalid transcript file, invalid XML, malformed brief, and unsupported file content.
- [ ] Every validation error includes: error type, expected format, and next action.
- [ ] Errors are logged with stable codes for troubleshooting in both CLI and Flask logs.
- [ ] CLI returns non-zero exit on hard failures and prints concise remediation text.
- [ ] A “recoverable” status is used where partial progress exists (e.g., XML parsed but selection failed).

### US-002: Validate timecode format and continuity before LLM invocation
**Description:** As a filmmaker, I want transcript timecodes checked and normalized before generation so I avoid misaligned output and broken sequences.

**Acceptance Criteria:**
- [ ] The parser validates all timecode formats against expected schema and rejects invalid values with line/context references.
- [ ] Start/end ordering is validated (`start < end`) with explicit checks for zero-length or reversed ranges.
- [ ] Overlap or impossible transitions are flagged and either auto-rejected or normalized per policy.
- [ ] Timecode conversion boundaries (string <-> frame index <-> seconds) preserve round-trip consistency in deterministic test fixtures.
- [ ] Invalid input produces deterministic failure message and no partial XML output is written.

### US-003: Improve LLM prompt for balanced bite quality (time, relevance, schema)
**Description:** As an editor, I want better prompt instructions and guardrails so selected bites are timely, relevant, and format-compliant.

**Acceptance Criteria:**
- [ ] Prompt defines output schema constraints and example-valid/invalid output pairs.
- [ ] Prompt enforces that selected segments align to transcript timecodes exactly.
- [ ] Prompt requires confidence fields (or equivalent scoring metadata) when choosing each bite.
- [ ] Prompt includes fallback policy when no valid candidate exists (explicit “no-op” structure).
- [ ] Deterministic seed/temperature settings are documented and configurable for repeatable generation.

### US-004: Add LLM response validator + hardening fallback
**Description:** As a solo filmmaker, I want generated content to be validated automatically before writing output so broken XML is avoided.

**Acceptance Criteria:**
- [ ] Validate LLM JSON shape before downstream XML generation.
- [ ] Validate each selected segment against time bounds and transcript segments.
- [ ] On validation failure, return a specific parse/validation error and no sequence write.
- [ ] Provide one automatic recovery attempt path with a corrected/retry prompt (bounded to 1 retry).
- [ ] UI shows retry status and reason for failed validation.

### US-005: Improve web UI editorial workflow (status, resumable progress, clarity)
**Description:** As a user in the Flask UI, I want clearer step-by-step flow and recoverable interactions so I can continue editing with less confusion.

**Acceptance Criteria:**
- [ ] UI shows step markers: Upload -> Validate -> Preview/Confirm -> Generate -> Download.
- [ ] Input errors show inline and panel-level messaging with action buttons (“Fix inputs”, “Try again”).
- [ ] Long-running operations show progress and state snapshots (received, validating, prompting, generating, finalizing).
- [ ] Preserve user inputs across recoverable failures to avoid re-uploading data.
- [ ] Verify in browser using dev-browser skill.

### US-006: Add deterministic integration tests for CLI and web orchestration
**Description:** As an engineering owner, I want fixture-backed integration tests that exercise happy and failure paths so regressions are caught before release.

**Acceptance Criteria:**
- [ ] Add CLI integration fixture tests: transcript + XML + brief -> expected deterministic output shape.
- [ ] Add UI flow integration tests using mocked LLM outputs for success and validation-failure paths.
- [ ] Add test for malformed transcript and invalid XML fixture paths.
- [ ] Add test for timecode edge-case fixture handling and expected error payload format.
- [ ] Test suite can run without local Ollama dependency by using mock LLM responses.

### US-007: Improve output determinism and traceability
**Description:** As a developer, I want repeatable generation for same inputs to simplify debugging and user trust.

**Acceptance Criteria:**
- [ ] Generation pipeline enforces deterministic ordering for segment selection candidates.
- [ ] Sequence XML output includes a small metadata block with source hashes/input versions.
- [ ] CLI and UI output include generated run metadata (timestamp, inputs, parser/validator version, model id).
- [ ] Same input + same mock model output always produces identical sequence filename/content.

## 4) Functional Requirements

- FR-1: The system must implement centralized error model types with user-friendly and developer-focused messages across CLI and web.
- FR-2: The system must validate transcript timecode syntax (regex + semantic checks), chronology, and overlap policy before LLM calls.
- FR-3: The system must validate transcript/clip boundaries in frame/timecode space before output generation.
- FR-4: The prompt module must include strict output-format constraints and an explicit confidence strategy.
- FR-5: The system must add an LLM response parser/validator that checks schema, segment bounds, and duplicate/overlap logic.
- FR-6: The generator must fail fast when validation fails and skip XML writes unless all validation gates pass.
- FR-7: The web UI must provide explicit workflow status messaging and retain uploaded content across recoverable failures.
- FR-8: The web UI must support resumable run progression and a clear retry action at each failure point.
- FR-9: The CLI must provide deterministic output filenames and include run metadata for traceability.
- FR-10: Integration tests must include fixture datasets for:
  - valid generation flow
  - invalid XML
  - invalid transcript format
  - invalid timecode order
  - mocked LLM schema violations.
- FR-11: All tests must not require a running Ollama service.
- FR-12: Success and failure messages must include machine-readable markers for automated assertions.

## 5) Non-Goals (Out of Scope)

- Not building a full timeline editor in the browser.
- Not adding third-party LLM provider support beyond existing Ollama integration path.
- Not adding cloud multi-tenant deployments.
- Not introducing mobile web app redesign or advanced accessibility audit at this stage.
- Not implementing enterprise-level batch workflows or asynchronous queue processing.
- Not adding non-English transcript or XML parsing support beyond current expected formats.

## 6) Design Considerations

- Keep UI updates minimal and focused on flow clarity and recoverability, avoiding a broad visual redesign.
- Preserve current Flask architecture and file-upload behavior (client-provided transcript/XML content).
- Error states should prioritize “what to fix next” messaging, not raw stack traces.
- Test fixtures should include representative solo filmmaker interview style content and timing pitfalls.

## 7) Technical Considerations

- Dependency boundaries:
  - `parser/`: strengthen parse-time validation and typed structures.
  - `llm/`: prompt and response schema enforcement layer.
  - `generator/`: strict sequence generation precondition checks and deterministic ordering.
  - `webapp.py`: UI state machine and robust request/response handling.
  - `tests/`: fixtures + integration harness with mocked LLM transport.
- Determinism:
  - avoid unordered dict/set serialization when building output and ensure stable ordering.
- Logging:
  - include error code, component, and offending input segment in logs.
- Performance:
  - preserve expected interactive responsiveness for local runs with modest transcript sizes.

## 8) Success Metrics

- Crash/error rate:
  - Reduce user-facing failures in beta flows by 50% vs current baseline after 3 pilot users/2 weeks.
- Recovery:
  - At least 80% of recoverable UI failures should be resolvable with one retry action.
- LLM quality:
  - ≥90% of generated segments must pass schema + boundary validation in integration fixtures.
  - ≥85% segment timing adherence to transcript timestamps in fixture tests.
  - Qualitative relevance score improvement tracked with a 5-point editorial rubric (target +1 average vs baseline by beta review).
- Testing:
  - Add at least 12 new integration tests across CLI and web paths using fixtures.
  - 0 tests should depend on a live Ollama service.
- Time-to-complete:
  - Reduce average time from upload to downloadable XML from current baseline by 20% for pilot users (excluding model latency).

## 9) Open Questions

- What is the hard error policy for partial segment overlaps: reject entire run or auto-truncate/filter segments?
- Should there be a hard cap on number of generated bites in beta mode (and who sets it)?
- What minimum confidence threshold should be used for selection (e.g., warn, drop, or auto-filter)?
- What is the exact metadata schema to include in generated XML output comments/attributes?
- Which failure states should block sequence export vs allow partial output with warnings?