# BiteBuilder PRD: Context-First Editorial Workspace

Date: 2026-04-14
Branch: feat/context-first-editorial-workspace
Primary implementation surface: Go TUI

## 1. Problem

The current Go TUI behaves too much like a multi-screen app/wizard.

That is the wrong interaction model for editorial work.

The operator needs a simple workspace where source context, editorial intent, and current generated bite set are visible together while working.

Current pain points:
- transcript is hidden behind a separate screen
- creative brief/ask is not persistently visible while reviewing bites
- generation feels detached from the actual working context
- the workflow feels like screen-hopping instead of editing
- the product risks becoming a feature pile instead of a usable interview-to-sequence tool

## 2. Product goal

Build a simple, context-first editorial workstation for interview-driven sequence generation.

The TUI should support this loop:
1. ingest transcript and Premiere XML
2. ask the model to summarize the transcript/interview
3. let the user enter the creative ask
4. generate a first pass of candidate bites with exact timecodes
5. let the user inspect/select/delete/question/regenerate in place as many times as needed
6. export importable Premiere XML

## 3. Core product principle

This is not a chatbot with editing extras.
This is an editorial tool.

The UI should optimize for:
- source awareness
- editorial intent
- iterative sequence shaping
- low-friction export

## 4. Required workflow

### Step 1: Ingest
User loads:
- transcript
- Premiere XML

### Step 2: Orient
Model reads the transcript and produces:
- a concise summary of what the interview contains
- major themes / sections / likely useful arcs

### Step 3: Direct
User provides the creative ask, e.g.:
- what the project is
- target sequence length
- desired story shape / emotional arc
- intended use of the output XML

Example:
"This is a CEO talking about his solar panel company. I need a 5-7 minute sequence of cohesive bites that tell a story, starting inspiring, then technical, then ending with an insightful resolution."

### Step 4: Generate v1
Model generates a first-pass sequence plan using transcript-derived bites with exact timecodes.

The user can then:
- inspect bites
- delete bites
- ask about specific bites
- ask for another full regeneration
- replace/reselect as needed

This iteration loop can happen any number of times.

### Step 5: Export
The user exports an importable Premiere XML.

## 5. UX direction

The Go TUI should pivot from a screen-stack to a main editorial workspace.

### Main workspace must keep visible
At minimum, the working view should keep these visible together:
- transcript context
- transcript summary
- creative ask
- candidate bites
- selected sequence
- status/errors/export path

### Generate should happen from the working context
Not from an isolated board screen detached from transcript/brief context.

### Chat should be inline, not the center of the product
Chat is a tool for:
- summarization
- asking about a bite
- regenerating a pass
- clarifying why the model chose something

It should not dominate the product structure.

## 6. Non-goals

Do not add more product surface area unless it directly supports the loop above.

Out of scope for this branch unless absolutely needed:
- session autosave / resume
- doctor / health panel
- broad visual polish
- release-readiness docs
- extra wizard screens
- non-editorial “assistant mode” concepts
- moving validation/model/export authority into Go

## 7. Authority split

Python remains authoritative for:
- model calls
- transcript parsing
- XML parsing
- sequence-plan validation
- XMEML generation

Go remains authoritative for:
- Bubble Tea UI
- subprocess orchestration
- NDJSON event handling
- layout/state/presentation of the editorial workspace

## 8. Reuse strategy from existing v2 workspace

Do not rewrite from scratch.
Take what is already working from the v2 workspace and reorganize it.

Expected reusable pieces:
- transcript ingestion/path handling
- XML ingestion/path handling
- current brief field handling
- current assistant chat state
- generation bridge calls
- plan hydration / board data payloads
- candidate/selected bite state
- export path and generation event state

Expected removals/de-emphasis:
- separate transcript-only workflow as a primary destination
- separate assistant-only workflow as a primary destination
- welcome screen as a meaningful part of daily operation
- excessive navigation burden between files/chat/board/bite/transcript screens

## 9. Proposed information architecture

### A. Setup state
Minimal setup interaction to load:
- transcript
- XML

### B. Main editorial workspace
Primary screen after setup.

Suggested regions:
- left: transcript excerpt / source context
- upper-right: transcript summary + creative ask
- center/right: candidate bites and selected sequence
- bottom: controls + status + export path + validation

### C. Optional detail/inspector behavior
A bite detail panel is fine, but it should support the main workspace rather than replace it.

## 10. Required user actions in workspace

Must support:
- summarize transcript
- edit creative ask
- generate v1
- regenerate full pass
- ask about selected bite
- delete bite
- replace bite
- export XML

Nice to have only if already mostly present:
- add candidate to selected sequence manually
- simple reorder if it already exists cleanly

## 11. Acceptance criteria

A first working version of this branch is complete when a user can:
1. load transcript and XML
2. request or view transcript summary
3. write/edit creative ask
4. generate v1 from the same workspace
5. see candidate bites with transcript/timecode context
6. delete / ask about / regenerate without losing working context
7. export importable Premiere XML

Additional acceptance constraints:
- transcript and creative ask remain visible enough during bite review
- no manual CLI after launch
- export still runs through Python validation
- no hidden destructive transitions between screens

## 12. Technical direction

### Prefer re-layout over new subsystems
The main work should be reorganizing current TUI state/layout into the correct editorial flow.

### Prefer one dominant workspace over many destinations
If separate screens remain temporarily, the main flow should still feel like one workspace, not a wizard.

### Preserve deterministic backend contract
Do not break:
- bridge tests
- generation NDJSON events
- export validation path

## 13. Suggested implementation sequence

1. create branch and keep this effort isolated
2. audit current model.go/UI flow and identify reusable working pieces
3. define the new main workspace layout
4. make transcript summary a first-class action/state
5. reframe brief as creative ask in UI copy and working flow
6. make generate/regenerate/actions operate from the main workspace
7. keep transcript + ask + board visible in the same working context
8. preserve export path and existing backend authority
9. run Go + Python verification

## 14. Testing expectations

Minimum verification:
- cd go-tui && go test ./...
- relevant Python bridge tests
- make test if changes touch end-to-end flow
- manual TUI check:
  1. load transcript
  2. load XML
  3. summarize transcript
  4. enter creative ask
  5. generate
  6. iterate on bites
  7. export XML

## 15. Definition of success

Success is not “more features in the TUI.”

Success is:
- the app feels like a simple editorial workstation
- the user can stay in one working context
- the interview, the ask, and the current cut are all legible while making decisions
- exporting Premiere XML feels like the natural endpoint of that loop
