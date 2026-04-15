# ADR: Go TUI Generation Transport

- **Status:** Accepted for the Go TUI prototype transport gate (historical reference; the TUI is currently on hold while UI/UX work is focused on the webapp)
- **Date:** 2026-04-13
- **Scope:** Phase 4 generation transport for the additive Bubble Tea Go TUI

## Context

BiteBuilder's Python CLI remains the authoritative runtime for transcript parsing, Gemma/model calls, sequence-plan validation, and XMEML export. The Go TUI prototype is additive and must not call Gemma or write Premiere/XMEML output directly.

The first bridge milestone for Phases 1-3 is intentionally read-only and request/response oriented: the Go process sends a single structured JSON request to Python, Python returns one structured JSON success/error envelope on stdout, and logs/tracebacks stay off stdout.

Phase 4 adds a different shape of work. Model-backed generation can be slow, may need progress updates, and must surface model/runtime failures clearly while preserving cancellation/progress options for a terminal UI. A blocking single JSON response would hide all intermediate state until the Python process exits.

## Decision

Use **newline-delimited JSON (NDJSON) events over a Python subprocess** for future Go TUI generation progress.

Keep the existing **single request/response JSON bridge** for Phase 1-3 read-only operations such as transcript metadata, Premiere XML metadata, sequence-plan summaries, and bridge health checks.

For generation, the Go TUI should start a Python subprocess command dedicated to generation and consume one JSON object per stdout line. Each line is a complete event envelope. Python owns all model calls and XMEML writes; Go only renders state, progress, errors, and final artifact locations.

## Event envelope sketch

Generation event stdout remains machine-readable only: one compact JSON object per line.

```json
{"event":"started","request_id":"...","schema_version":"go_tui_generation_events.v1"}
{"event":"progress","stage":"model_request","message":"Requesting candidate bites"}
{"event":"artifact","kind":"sequence_plan","path":"output/run/_sequence_plan.json"}
{"event":"artifact","kind":"xmeml","path":"output/run/option-1.xml"}
{"event":"completed","ok":true}
```

Structured failures are events, not tracebacks:

```json
{"event":"error","ok":false,"error":{"code":"model_unavailable","message":"Gemma runtime is not reachable","details":{}}}
```

Diagnostics, logs, and tracebacks must go to stderr or be converted into a structured `error` event. The Go side must treat malformed stdout lines as protocol errors and render them as bridge failures.

## Rationale

- Preserves Python ownership of model and export behavior.
- Avoids adding a local server lifecycle before the TUI proves value.
- Gives Bubble Tea enough state to show spinner/progress/error screens during slow generation.
- Keeps the read-only bridge simple and testable for Phases 1-3.
- Leaves room for cancellation/progress semantics without committing to HTTP yet.

## Alternatives considered

### Blocking JSON request/response for generation

Rejected for Phase 4 generation. It is sufficient for read-only metadata operations, but it does not expose progress, stage transitions, or partial artifact milestones. It would make long Gemma calls appear hung in the TUI.

### Local Python HTTP API

Deferred. HTTP could eventually support streaming, cancellation, and shared web/TUI backend behavior, but it adds server startup, port management, lifecycle, and security considerations too early for this additive prototype.

### Go calls Gemma or writes XMEML directly

Rejected. This would duplicate core Python behavior and bypass the validated pipeline. Python remains the single owner of model calls, sequence-plan validation, and XMEML generation.

## Consequences

- Phase 1-3 bridge tests should continue to assert single JSON response envelopes for read-only operations.
- Phase 4 must add NDJSON parser tests on the Go side before wiring model-backed generation screens.
- Python generation transport tests should cover ordered events, structured errors, malformed-output handling, and JSON-only stdout hygiene.
- The Go TUI must display protocol failures distinctly from model failures.
- `bitebuilder.py --tui` remains the Python curses TUI until a separate parity/default-switch ADR approves changing it.

## Implementation guardrails

- Do not implement model-backed generation in Go until the NDJSON event contract is covered by tests.
- Do not replace the Phase 1-3 request/response bridge with NDJSON for simple read-only operations.
- Do not introduce a local HTTP server for this prototype unless a later ADR supersedes this decision.
- Do not allow logs or tracebacks on generation stdout; stdout is reserved for event envelopes.
