# Implementation Plan: Selection-Aware Editorial Workspace Prototype

> For Hermes/Codex: implement this as a working prototype, not a full product. Reuse backend logic. Keep changes minimal and architectural intent clear.

Branch: feat/selection-aware-editorial-workspace-prototype
PRD: docs/prds/2026-04-14-selection-aware-editorial-workspace-mvp.prd.md

Goal:
Build a workspace-centered browser prototype that supports selection-aware editorial iteration on top of the existing BiteBuilder backend.

Architecture:
Keep Python as the authoritative backend for generation, validation, and XML export. Build the workspace interaction model in the Flask/browser layer so transcript context, creative ask, candidate/selected bites, and selection-aware model actions stay in one visible working surface.

Tech stack:
- Flask webapp + browser UI
- existing Python `bitebuilder.py` backend
- existing sequence-plan and XML render flow
- browser-side workspace state in `static/app.js`

---

## Task 1: Freeze the backend contract you are reusing
Objective:
Identify the existing backend operations the browser workspace will keep.

Files:
- Read: `webapp.py`
- Read: `bitebuilder.py`
- Read: `tests/test_request_int.py`
- Read: `README.md`

Required output:
- short internal note or comments listing the exact entrypoints/data reused for:
  - summarize
  - generate
  - hydrate board
  - ask-about-selection / refine
  - export

Verification:
- no implementation yet
- must be able to name the specific backend entrypoints before changing UI

---

## Task 2: Keep one dominant workspace state model
Objective:
Stop treating the UI as a wizard/screen stack. Keep one dominant editorial workspace model.

Files:
- Modify: `templates/workspace.html`
- Modify: `static/app.js`
- Modify: `static/app.css`
- Test: `tests/test_request_int.py`

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
- workspace route renders
- browser-side state stays coherent after generate/edit/export actions

---

## Task 3: Keep transcript summary and creative ask first-class
Objective:
After ingest, the user can summarize material and keep that summary plus the creative ask visible.

Files:
- Modify: `webapp.py` only if a narrow backend operation is needed
- Modify: `templates/workspace.html`
- Modify: `static/app.js`
- Test: `tests/test_request_int.py`

Requirements:
- summary uses Python authority
- summary is stored in workspace state
- summary is visible in the workspace
- creative ask framing is explicit and persistent

Verification:
- relevant Python/web tests pass
- workspace keeps summary + ask visible during iteration

---

## Task 4: Hide demo-specific product affordances
Objective:
Remove solar-demo-first UX from the primary workspace.

Files:
- Modify: `templates/workspace.html`
- Modify: `static/app.js`
- Test: `tests/test_request_int.py`

Requirements:
- no visible solar demo button in the main workspace
- neutral placeholders and copy
- backend-only demo endpoints may remain for local reference if not surfaced in product UX

Verification:
- workspace route no longer contains demo-specific CTA text
- demo endpoint tests still pass if retained

---

## Task 5: Make generation and iteration happen from the same workspace
Objective:
Generate V1 and iterate from the current visible context.

Files:
- Modify: `webapp.py`
- Modify: `static/app.js`
- Test: `tests/test_request_int.py`
- Test any directly affected Python tests

Requirements:
- generate uses current transcript + XML + creative ask
- resulting candidate/selected bites update in the workspace
- transcript context and creative ask remain visible enough during review
- delete/replace/regenerate keep exportable selected sequence intact

Verification:
- generation flow tests pass
- no confusing navigation requirement to see the result

---

## Task 6: Preserve export correctness as the main gate
Objective:
Do not lose the one thing that makes the tool real.

Files:
- Modify as needed: `webapp.py`, `bitebuilder.py`, `static/app.js`
- Test existing end-to-end flow

Requirements:
- current selected-board state must still drive Python-backed export
- export path visible in workspace
- export blocked when invalid
- no fake UI-only success state

Verification:
- `./bin/bitebuilder smoke`
- relevant Python tests
- manual check: launch, ingest, summarize, ask, generate, edit, export

---

## Task 7: Reconcile docs with current product direction
Objective:
Make docs reflect that the webapp is the active UI/UX surface and the TUI is on hold.

Files:
- Modify: `README.md`
- Modify: `docs/canonical-runtime-proof.md`
- Modify: `docs/codebase-index.md`
- Modify: `docs/prds/*.md`

Requirements:
- `/workspace` is documented as the main interactive surface
- launcher/docs do not imply TUI-first usage
- TUI docs are either marked as reference-only or explicitly on hold

Verification:
- spot-check docs for contradictory “Go TUI is primary” claims

---

## Required verification commands
Run at minimum:
- `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'`
- `./bin/bitebuilder flask-smoke`
- `./bin/bitebuilder smoke`
- `cd go-tui && go test ./...` as regression coverage for held code

Manual prototype script:
1. `make workspace` or `./bin/bitebuilder`
2. open `http://127.0.0.1:8000/workspace`
3. load transcript
4. load XML
5. summarize transcript or confirm summary state works
6. enter creative ask
7. generate V1
8. select/edit bites
9. export XML

Expected pass signal:
- one coherent workspace
- selection-aware model interaction works in the browser flow
- export still reflects current selected sequence state
- the primary UI no longer reads like a solar demo or a TUI detour
