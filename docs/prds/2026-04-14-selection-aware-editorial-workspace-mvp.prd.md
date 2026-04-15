# BiteBuilder MVP PRD: Selection-Aware Editorial Workspace Prototype

Date: 2026-04-14
Branch: feat/selection-aware-editorial-workspace-prototype

## Product decision
Do not keep incrementally patching the old TUI flow.
Do not rewrite the backend.

Build a fresh working prototype of the app shell around the proven backend pieces.

## Goal
Create a simple selection-aware editorial workspace prototype that lets an editor:
1. ingest transcript + source XML
2. summarize interview material
3. enter a creative ask
4. generate a first pass of bites
5. select bites and talk to the model about those selections
6. replace/delete/regenerate in context
7. export importable Premiere XML

## Why this branch exists
The backend has already proven useful:
- transcript parsing
- XML parsing
- sequence-plan generation
- exact timecode handling
- deterministic XML export

The current weakness is the UI interaction model.
The old TUI still behaves too much like a wizard / screen stack.
This prototype should instead behave like an editorial workstation.

## Product principle
This is not a chatbot with editing extras.
This is a selection-aware editorial copilot.

The key capability is:
- selecting one or more bites in the workspace
- asking the model about that selection
- feeding selected-bite context back to the model
- getting usable editorial revisions back

Think:
- source context
- current cut
- editorial ask
- model iteration
all in one working surface

## Scope
Build the minimum prototype that proves the interaction model.

## Must-have workflow
1. Load transcript and source XML
2. Request transcript/interview summary
3. Enter/edit creative ask
4. Generate V1 bite pass
5. View candidate bites and selected sequence together
6. Select one or more bites
7. Ask the model about the current selection
8. Delete or replace bites
9. Regenerate full pass if needed
10. Export Premiere XML

## Must-have UI regions
Single main workspace with persistent context.

At minimum keep visible or one-keystroke accessible within the same workspace:
- transcript/source excerpt panel
- transcript summary panel
- creative ask panel
- candidate bites panel
- selected sequence panel
- status / validation / export path area

## Must-have interactions
- select candidate or selected bites
- selection state is explicit in UI
- ask the model about selected bite(s)
- regenerate using current creative ask
- replace selected bite from candidates
- delete selected bite
- export current selected sequence

## Selection-aware model behavior
When the user asks about selected bites, the model should receive:
- selected bite text/timecodes
- current creative ask
- nearby transcript context if needed
- current sequence state if relevant

Example prompts the UI should support naturally:
- why this bite?
- replace this with something less negative
- make this opening more visionary
- give me a better closing than this
- extend the technical middle using the technician only
- regenerate around these constraints

## Backend rule
Python remains authoritative for:
- model calls
- transcript parsing
- XML parsing
- sequence-plan validation
- XMEML generation

Go remains authoritative for:
- workspace UI
- selection state
- subprocess orchestration
- NDJSON event handling
- rendering and interaction

## Reuse strategy
Reuse existing working backend and bridge pieces.
Do not rebuild from scratch what already works.

Expected reusable pieces:
- bitebuilder.py generation/refinement/export behavior
- transcript/XML file ingestion logic
- sequence-plan structure
- generation and plan hydration bridge operations
- candidate/selected bite representations
- export path and validation handling

Expected fresh work:
- new workspace-centered UI layout
- selection-aware state model
- selection-aware model prompt flow
- simplified navigation and actions

## Non-goals
Not part of this prototype unless directly required:
- full persistence/autosave
- release readiness / docs package
- health/doctor panels
- broad visual polish
- general-purpose chat productization
- account/cloud systems
- backend rewrite

## Acceptance criteria
This prototype is successful when an editor can:
1. ingest transcript + XML
2. see a transcript summary
3. write a creative ask
4. generate a V1 sequence
5. select bites in the UI
6. ask the model about selected bites
7. delete / replace / regenerate in context
8. export Premiere XML

And the workflow feels like one editorial workspace, not like hopping between disconnected screens.

## MVP quality bar
- simple
- fast
- selection-aware
- editorially useful
- deterministic export preserved

## Main blocker to respect
Do not call the prototype successful unless current selected-board edits and replacements still flow through to Python-backed XML export correctly.
