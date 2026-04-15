# Implementation Plan: Selection-Aware Editorial Workspace Prototype

> For Hermes/Codex: implement this as a working prototype, not a full product. Reuse backend logic. Keep changes minimal and architectural intent clear.

Branch: feat/selection-aware-editorial-workspace-prototype
PRD: docs/prds/2026-04-14-selection-aware-editorial-workspace-mvp.prd.md

Goal:
Build a fresh workspace-centered TUI/app shell that supports selection-aware editorial iteration on top of the existing BiteBuilder backend.

Architecture:
Keep Python as the authoritative backend for generation, validation, and XML export. Build a new workspace interaction model in Go that surfaces transcript context, creative ask, candidate/selected bites, and selection-aware model actions in one main working surface.

Tech stack:
- Go Bubble Tea UI
- existing Go bridge layer
- existing Python bitebuilder.py backend
- existing sequence-plan and XML render flow

---

## Task 1: Freeze the backend contract you are reusing

Objective:
Identify the existing backend/bridge operations that the prototype will keep.

Files:
- Read: `go-tui/internal/bridge/bridge.go`
- Read: `go-tui/internal/bridge/types.go`
- Read: `bitebuilder.py`
- Read: `tests/test_go_tui_bridge.py`
- Read: `docs/go-tui-bridge.md`

Required output:
- short internal note or comments listing the exact operations/data you will reuse for:
  - summarize
  - generate
  - hydrate board
  - ask-about-selection / refine
  - export

Verification:
- No implementation yet
- Must be able to name the specific bridge/backend entrypoints before changing UI

---

## Task 2: Define a new main workspace state model

Objective:
Stop treating the UI as a wizard/screen stack. Create one dominant editorial workspace model.

Files:
- Modify: `go-tui/internal/ui/model.go`
- Test: `go-tui/internal/ui/model_test.go`

Requirements:
- represent one main workspace with regions for:
  - transcript context
  - transcript summary
  - creative ask
  - candidate bites
  - selected sequence
  - status/export info
- keep navigation simple
- separate detail views only if they support the workspace, not replace it

Verification:
- `cd go-tui && go test ./internal/ui`
- workspace rendering compiles and tests stay coherent

---

## Task 3: Add transcript-summary as a first-class workspace action

Objective:
After ingest, user can summarize the interview material and keep that summary visible.

Files:
- Modify: `bitebuilder.py` only if a narrow backend operation is needed
- Modify: `go-tui/internal/bridge/bridge.go`
- Modify: `go-tui/internal/bridge/types.go`
- Modify: `go-tui/internal/ui/model.go`
- Test: `go-tui/internal/bridge/bridge_test.go`
- Test: `tests/test_go_tui_bridge.py`
- Test: `go-tui/internal/ui/model_test.go`

Requirements:
- summary uses Python authority
- summary is stored in session state
- summary is visible in the workspace
- summary can be refreshed/regenerated

Verification:
- bridge tests pass
- Go UI tests cover summary state rendering

---

## Task 4: Reframe brief input as the creative ask panel

Objective:
Make the editor’s intent explicit and persistent.

Files:
- Modify: `go-tui/internal/ui/model.go`
- Test: `go-tui/internal/ui/model_test.go`

Requirements:
- rename visible workflow copy from generic brief behavior to creative ask behavior where sensible
- keep creative ask visible while generating/reviewing
- avoid breaking backend compatibility if the backend still calls it `brief`

Verification:
- copy reflects editorial ask framing
- tests updated if string expectations change

---

## Task 5: Make generation a workspace action, not a detached screen action

Objective:
Generate V1 from the current visible context.

Files:
- Modify: `go-tui/internal/ui/model.go`
- Test: `go-tui/internal/ui/model_test.go`

Requirements:
- generate uses current transcript + XML + creative ask
- resulting candidate/selected bites update in the workspace
- transcript context and creative ask remain visible enough during review

Verification:
- generation flow tests pass
- no confusing navigation requirement to see the result

---

## Task 6: Add explicit bite selection state

Objective:
Allow user to select one or more bites as the subject of model feedback/actions.

Files:
- Modify: `go-tui/internal/ui/model.go`
- Test: `go-tui/internal/ui/model_test.go`

Requirements:
- selected bite(s) are explicit in UI state
- selection works for both candidate and selected-sequence items as appropriate
- selection can drive model actions

Verification:
- tests cover selecting and deselecting bites
- workspace displays selection clearly enough for use

---

## Task 7: Add “ask about selection” model action

Objective:
The model should be able to reason about currently selected bites.

Files:
- Modify: `go-tui/internal/bridge/bridge.go`
- Modify: `go-tui/internal/bridge/types.go`
- Modify: `bitebuilder.py` if needed for narrow request shaping
- Modify: `go-tui/internal/ui/model.go`
- Test: `go-tui/internal/bridge/bridge_test.go`
- Test: `tests/test_go_tui_bridge.py`
- Test: `go-tui/internal/ui/model_test.go`

Requirements:
- selected bite text/timecodes are passed to Python-backed model reasoning
- user can ask questions like:
  - why this bite?
  - replace this with something less negative
  - give me a better opening/closing
- response appears inside workspace context

Verification:
- tests cover request shaping and result handling
- UI state remains stable after selection-aware query

---

## Task 8: Keep delete / replace / regenerate in the same workspace loop

Objective:
Support practical editorial iteration without mode-switching.

Files:
- Modify: `go-tui/internal/ui/model.go`
- Test: `go-tui/internal/ui/model_test.go`
- Modify bridge/backend only if current paths are insufficient

Requirements:
- delete bite
- replace bite from candidates
- regenerate whole pass
- keep exportable selected sequence intact

Verification:
- tests cover delete/replace/regenerate flows
- selected sequence remains coherent after edits

---

## Task 9: Preserve export correctness as the main gate

Objective:
Do not lose the one thing that makes the tool real.

Files:
- Modify as needed: `go-tui/internal/ui/model.go`
- Test: `go-tui/internal/ui/model_test.go`
- Test: `tests/test_go_tui_bridge.py`
- Test existing end-to-end flow

Requirements:
- current selected-board state must still drive Python-backed export
- export path visible in workspace
- export disabled or blocked when invalid
- no fake UI-only success state

Verification:
- `cd go-tui && go test ./...`
- relevant Python tests
- `make test` if end-to-end flow changes
- manual check: launch, ingest, summarize, ask, generate, select, ask-about-selection, edit, export

---

## Task 10: Cut dead weight from the prototype

Objective:
Avoid rebuilding the wrong app with better code.

Files:
- Modify: `go-tui/internal/ui/model.go`
- Test: `go-tui/internal/ui/model_test.go`

Demote or remove from primary flow if they fight the workspace model:
- welcome screen as a meaningful destination
- transcript-only screen as a primary working surface
- detached assistant-first flow
- excessive screen switching for ordinary editorial tasks

Verification:
- workflow is simpler after changes, not more complicated

---

## Required verification commands

Run at minimum:
- `cd go-tui && go test ./...`
- relevant Python bridge tests
- `make test` if export/generation flow changed materially

Manual prototype script:
1. `make tui`
2. load transcript
3. load XML
4. summarize transcript
5. enter creative ask
6. generate V1
7. select bites
8. ask model about selected bites
9. delete or replace a bite
10. export XML

Expected pass signal:
- one coherent workspace
- selection-aware model interaction works
- export still reflects current selected sequence state

---

## Commit strategy
Prefer a few clean commits:
1. feat: define workspace-centered UI state
2. feat: add transcript summary and creative ask workflow
3. feat: add bite selection and selection-aware model actions
4. feat: preserve export correctness from edited workspace state
5. test: cover workspace interaction and export contract

---

## Final reminder
Do not overbuild this.
The prototype succeeds if it behaves like an editor’s workstation and preserves deterministic XML export.
