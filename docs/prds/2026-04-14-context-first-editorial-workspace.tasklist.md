# Tasklist: Context-First Editorial Workspace

Branch: feat/context-first-editorial-workspace
PRD: docs/prds/2026-04-14-context-first-editorial-workspace.prd.md
Audience: Codex agent

## Implementation goal
Push BiteBuilder toward one context-first browser workspace centered on:
- transcript context
- transcript summary
- creative ask
- candidate bites
- selected sequence
- export

Reuse existing backend domain logic whenever possible. Do not rewrite parsing, validation, generation, or export logic.

## Constraints
- Python remains authoritative for model calls, transcript/XML parsing, sequence-plan validation, and XMEML generation.
- The browser workspace is the primary UI surface.
- The Go TUI is on hold except for preserving regression coverage on existing bridge/reference code.
- Keep the implementation simple and editorially useful.
- Do not add unrelated polish or wizard-like flow.

## Codebase entry points
Inspect these first:
- `webapp.py`
- `templates/workspace.html`
- `static/app.js`
- `static/app.css`
- `bitebuilder.py`
- `tests/test_request_int.py`
- `README.md`
- `docs/canonical-runtime-proof.md`

---

## Task 1: Keep the browser workspace canonical
Objective:
Make `/workspace` the explicit center of gravity in code paths, launchers, and docs.

Deliverable:
- workspace route is documented and easy to launch
- launcher/help text does not imply TUI-first usage
- stale low-priority webapp language is removed

Verification:
- `./bin/bitebuilder --help`
- `./bin/bitebuilder flask-smoke`

---

## Task 2: Keep the workspace generic, not demo-branded
Objective:
Remove solar-specific product copy and hide demo affordances from the primary UI.

Requirements:
- no visible “Load solar demo” control in the main workspace
- neutral placeholders/copy in intake fields
- backend-only demo helpers may remain for local smoke/reference if not surfaced as product UX

Files likely touched:
- `templates/workspace.html`
- `static/app.js`
- `tests/test_request_int.py`

Verification:
- workspace route renders without solar demo UI
- related tests still pass

---

## Task 3: Keep transcript + ask + board visible together
Objective:
Preserve the context-first editing model in the browser workspace.

Requirements:
- transcript browser stays visible
- creative ask / context remains in the same working surface
- candidate bites and selected lane stay visible without screen-hopping
- export remains part of the same workflow

Files likely touched:
- `templates/workspace.html`
- `static/app.js`
- `static/app.css`

Verification:
- manual workspace check confirms one coherent editing surface

---

## Task 4: Preserve backend authority and deterministic export
Objective:
Make sure UI cleanup does not weaken the real value of the tool.

Requirements:
- browser actions still flow through Python-backed parsing, validation, generation, and XMEML export
- no fake client-only success state for export
- structured errors remain visible in the workspace

Files likely touched:
- `webapp.py`
- `bitebuilder.py`
- `tests/`

Verification:
- deterministic XML smoke still passes
- export-related tests still pass

---

## Task 5: Reconcile product docs with current reality
Objective:
Align docs and PRDs around the browser workspace as the active UI/UX priority.

Requirements:
- README, runtime docs, and PRDs point to `/workspace`
- TUI is described as on hold, not as the primary implementation surface
- historical Go/TUI docs are either marked as reference-only or no longer contradict the current direction

Files likely touched:
- `README.md`
- `docs/canonical-runtime-proof.md`
- `docs/codebase-index.md`
- `docs/prds/*.md`

Verification:
- spot-check docs for contradictory “Go TUI is primary” claims

---

## Required verification commands
Run at minimum:
- `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'`
- `./bin/bitebuilder flask-smoke`
- `./bin/bitebuilder smoke`
- `cd go-tui && go test ./...` as regression coverage for held code

Manual verification script:
1. `make workspace` or `./bin/bitebuilder`
2. open `http://127.0.0.1:8000/workspace`
3. load transcript
4. load XML
5. enter creative ask
6. generate V1
7. inspect/edit selected lane
8. export XML

Expected pass signal:
- the flow feels like one editorial workspace, not a wizard
- the workspace reads as product-generic, not solar-demo-specific
- export still succeeds through the Python path
