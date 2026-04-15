# Tasklist: Context-First Editorial Workspace

Branch: feat/context-first-editorial-workspace
PRD: docs/prds/2026-04-14-context-first-editorial-workspace.prd.md
Audience: Codex agent

## Implementation goal
Rework the Go TUI into a simple editorial workspace centered on:
- transcript context
- transcript summary
- creative ask
- candidate bites
- selected sequence
- export

Reuse existing v2 functionality whenever possible. Do not rewrite backend domain logic.

## Constraints
- Python remains authoritative for model calls, transcript/XML parsing, sequence-plan validation, and XMEML generation.
- Go remains UI + subprocess NDJSON client.
- Do not add Phase 5/6 polish features.
- Keep the implementation simple and editorially useful.

## Codebase entry points
Primary files to inspect first:
- go-tui/internal/ui/model.go
- go-tui/internal/ui/model_test.go
- go-tui/internal/app/app.go
- go-tui/internal/bridge/bridge.go
- go-tui/internal/bridge/types.go
- go-tui/internal/bridge/bridge_test.go
- bitebuilder.py
- tests/test_go_tui_bridge.py
- docs/go-tui-bridge.md

---

## Task 1: Audit current TUI flow and reuse candidates

Objective:
Document which current pieces can be kept and which should be demoted/removed from the main flow.

Deliverable:
Short implementation note (can be temporary) listing:
- existing reusable state/actions
- current screen stack problems
- target workspace regions

Check for reusable current behavior:
- transcript file selection
- XML file selection
- assistant chat state
- generation bridge calls
- plan hydration
- candidate/selected bite board state
- export flow

Verification:
- No code change required yet
- Confirm by naming exact functions/state blocks to keep

---

## Task 2: Define the new primary workspace layout in code terms

Objective:
Replace the current mental model of “screen hopping” with one dominant editorial workspace.

Implementation notes:
- Keep setup/file loading if needed, but make it a lightweight prelude
- Main workspace should become the default working surface after ingest
- Workspace should display at minimum:
  - transcript context region
  - summary region
  - creative ask region
  - candidate bites region
  - selected sequence region
  - status/export region

Files likely touched:
- go-tui/internal/ui/model.go
- go-tui/internal/ui/model_test.go

Verification:
- Go tests still compile
- Manual TUI launch shows a coherent main workspace direction

---

## Task 3: Add transcript-summary as a first-class model action

Objective:
After transcript + XML are loaded, the operator can request a summary of the transcript/interview contents.

Requirements:
- summary is generated through Python, not Go-native inference
- summary is persisted in current TUI session state
- summary is visible in the main workspace
- summary can be regenerated if needed

Implementation suggestions:
- either extend existing assistant/bridge operation or add a narrow summary-oriented operation that still uses Python authority
- avoid inventing a new complex subsystem if current assistant bridge can be reused cleanly

Files likely touched:
- bitebuilder.py
- go-tui/internal/bridge/bridge.go
- go-tui/internal/bridge/types.go
- go-tui/internal/ui/model.go
- tests/test_go_tui_bridge.py
- go-tui/internal/bridge/bridge_test.go
- go-tui/internal/ui/model_test.go

Verification:
- bridge tests cover summary response shape
- UI test covers summary state rendering

---

## Task 4: Reframe “brief” as “creative ask” in the product flow

Objective:
The operator-facing concept should be the creative ask, not a generic brief rewrite field.

Requirements:
- rename visible labels/copy where appropriate
- preserve compatibility with backend brief plumbing if renaming internals is too expensive
- creative ask remains visible during generation/review

Files likely touched:
- go-tui/internal/ui/model.go
- go-tui/internal/ui/model_test.go
- docs/go-tui-bridge.md if contract wording changes materially

Verification:
- UI copy reflects “creative ask” or equivalent editorial language
- tests updated if text expectations change

---

## Task 5: Make Generate V1 operate from the main editorial workspace

Objective:
Generation should feel like a natural action from the context-rich workspace, not a detached screen action.

Requirements:
- generate uses currently loaded transcript/XML + current creative ask
- after generation, candidate bites and selected sequence update in place
- transcript context and creative ask remain accessible/visible enough during review

Files likely touched:
- go-tui/internal/ui/model.go
- go-tui/internal/ui/model_test.go

Verification:
- tests cover generation from current workspace state
- manual launch supports load -> ask -> generate without confusing navigation

---

## Task 6: Support the iteration loop in place

Objective:
Enable the real editing loop without forcing the user out of context.

Required actions:
- ask about selected bite
- regenerate full pass
- delete bite
- replace bite
- keep selected sequence exportable

Notes:
- use existing board/assistant/bridge logic where possible
- avoid new modal complexity unless necessary
- chat is a tool for iteration, not the dominant app mode

Files likely touched:
- go-tui/internal/ui/model.go
- go-tui/internal/ui/model_test.go
- maybe bridge/types + tests if a new event/data shape is required

Verification:
- tests cover delete/replace/regenerate/ask-about-selected behavior
- no regression in export path

---

## Task 7: Preserve export as the terminal action of the same workflow

Objective:
Export remains simple and reliable after the workspace reorganization.

Requirements:
- selected sequence exports through Python-backed validation/XMEML path
- output XML path is visible in the workspace
- export errors remain structured/recoverable

Files likely touched:
- go-tui/internal/ui/model.go
- go-tui/internal/ui/model_test.go
- possibly no backend change if current export path already works

Verification:
- existing export-related tests still pass
- end-to-end manual check reaches export from the workspace

---

## Task 8: Remove or demote workflow dead weight

Objective:
Reduce interaction clutter that fights the editorial workflow.

Candidates to demote/remove from primary flow:
- welcome screen as a meaningful destination
- transcript-only screen as primary working area
- detached assistant-first workflow
- bite-detail screen as required destination rather than optional inspector

Important:
Do this surgically. Do not destroy working code if it can simply be deprioritized.

Verification:
- navigation feels simpler, not more clever
- main workspace is clearly the center of gravity

---

## Task 9: Verification

Run at minimum:
- cd go-tui && go test ./...
- relevant Python bridge tests
- make test if bridge or end-to-end path changed

Manual verification script:
1. make tui
2. load transcript
3. load XML
4. request/view transcript summary
5. enter creative ask
6. generate V1
7. delete or replace at least one bite
8. ask about a selected bite or regenerate
9. export XML

Expected pass signal:
- the flow feels like one editorial workspace, not a wizard
- transcript + ask + current cut remain legible enough while working
- export still succeeds through Python path

---

## Suggested commit strategy

Prefer a few clean commits over checkpoint noise:
1. feat: define context-first workspace structure
2. feat: add transcript summary workflow
3. feat: move generation and iteration into workspace
4. test: cover workspace-driven editorial loop

---

## Handoff note for Codex

Implement the smallest set of changes that makes the editorial loop feel correct.
Do not add extra polish or speculative systems.
Take what already works in v2 and reorganize it into the right product shape.
