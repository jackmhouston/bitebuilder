# PRD: Ingest-First Copilot Workflow

## Introduction

BiteBuilder currently behaves like two different products inside the same workflow. Area 3 Chat only sees a reduced view of project context, while Area 4 Generate rebuilds its own understanding later. This creates a split-brain UX: the user uploads files, writes a brief, chats about editorial direction, then still has to manually transfer intent into generation.

This feature creates one continuous copilot workflow. As soon as the user has provided the transcript, Premiere XML contents, creative brief, and optional project context, the system should run an ingest pass that produces a concise project synopsis and an initial suggested edit plan. That ingest result becomes the shared context for the first chat response and for later generation, so Chat and Generate operate from the same editorial state.

The immediate product goal is to fix continuity and trust without requiring a full rewrite of the XML generation pipeline. A future UI merge between Areas 3 and 4 should remain possible, but this PRD focuses first on unified context and a cleaner handoff.

## Goals

- Auto-ingest project materials once the user has supplied the core inputs required to work.
- Seed the first chat response with a project synopsis grounded in the uploaded transcript and the user brief.
- Generate an initial suggested plan before any XML generation starts.
- Ensure Generate always inherits the latest accepted plan and project notes from Chat without manual transfer steps.
- Make the current multi-step UI feel like one continuous workflow even if the screens remain separate in the short term.
- Preserve deterministic XML generation behavior and existing transcript timecode constraints.

## User Stories

### US-001: Auto-ingest when the project is ready
**Description:** As an editor, I want BiteBuilder to analyze the uploaded project as soon as the required inputs are present so that I start with useful context instead of an empty chat.

**Acceptance Criteria:**
- [ ] When transcript contents, XML contents, and creative brief are present, the app automatically starts an ingest pass without requiring a Generate action.
- [ ] If project context is present, it is included in the ingest input.
- [ ] The ingest pass does not create output XML files.
- [ ] The UI shows a visible ingest status: idle, running, complete, or failed.
- [ ] Typecheck or test suite relevant to this change passes.
- [ ] Verify in browser using dev-browser skill

### US-002: Show a synopsis before the first chat turn
**Description:** As an editor, I want the copilot to open with a project synopsis so that I can confirm the system understood the material before I start refining the cut.

**Acceptance Criteria:**
- [ ] A concise synopsis appears after ingest completes and before the user sends the first manual chat message.
- [ ] The synopsis is based on the user brief, project context, and a model-made transcript summary.
- [ ] The synopsis is stored in shared session state and survives navigation between the current app areas.
- [ ] If ingest fails, the UI shows a retry action and a plain-language error.
- [ ] Typecheck or test suite relevant to this change passes.
- [ ] Verify in browser using dev-browser skill

### US-003: Seed chat with an initial suggested plan
**Description:** As an editor, I want the system to propose a starting edit plan right after ingest so that I can react to something concrete instead of starting from scratch.

**Acceptance Criteria:**
- [ ] Ingest produces an initial suggested plan alongside the synopsis.
- [ ] The first chat response references that suggested plan instead of behaving like a cold start.
- [ ] The user can accept, reject, or revise the suggested plan from the chat workspace.
- [ ] The accepted version is clearly distinguished from the suggested version in the UI state.
- [ ] Typecheck or test suite relevant to this change passes.
- [ ] Verify in browser using dev-browser skill

### US-004: Carry one shared editorial state into Generate
**Description:** As an editor, I want Generate to use the same accepted plan and notes I established in Chat so that I do not have to repeat decisions.

**Acceptance Criteria:**
- [ ] Generate reads the latest accepted plan from shared state automatically.
- [ ] Generate includes user-authored project notes and synopsis context in its request payload.
- [ ] The user does not need to manually re-keep or re-enter plan content before generating.
- [ ] If no accepted plan exists yet, Generate falls back to the latest suggested plan and makes that fallback visible in the UI.
- [ ] Typecheck or test suite relevant to this change passes.
- [ ] Verify in browser using dev-browser skill

### US-005: Refresh context when the brief changes
**Description:** As an editor, I want the copilot context to refresh when I materially change the brief or project notes so that later chat and generation stay aligned with the new direction.

**Acceptance Criteria:**
- [ ] Editing the brief or project context marks the current synopsis and plan as stale.
- [ ] The user can explicitly rerun ingest after changing direction.
- [ ] The UI shows whether the current synopsis and plan are fresh or stale.
- [ ] Regeneration after a refresh uses the new ingest outputs rather than stale ones.
- [ ] Typecheck or test suite relevant to this change passes.
- [ ] Verify in browser using dev-browser skill

### US-006: Preserve generation determinism and editorial traceability
**Description:** As a developer, I want ingest artifacts and generation inputs to be explicit so that the workflow is easier to debug without weakening XML output reliability.

**Acceptance Criteria:**
- [ ] The system stores the current synopsis, suggested plan, accepted plan, and project notes as separate fields in session state.
- [ ] Generation logs or debug payloads make it clear which of those fields were used for a given run.
- [ ] The ingest flow does not alter transcript timecodes, parsed segments, or XML source metadata.
- [ ] Existing fixture-backed tests remain valid or are updated with deterministic expectations.
- [ ] Typecheck or test suite relevant to this change passes.

## Functional Requirements

1. `FR-1`: The system must detect a "project ready" state when transcript contents, XML contents, and creative brief have been provided in the browser workflow.
2. `FR-2`: When the project becomes ready, the system must automatically run an ingest pass before any XML generation begins.
3. `FR-3`: The ingest pass must use the creative brief, optional project context, and the transcript content to produce a model-made transcript summary.
4. `FR-4`: The ingest pass must produce a concise project synopsis derived from the brief, project context, and transcript summary.
5. `FR-5`: The ingest pass must produce an initial suggested edit plan that the user can later accept or revise.
6. `FR-6`: The first chat response after ingest must be grounded in the stored synopsis and suggested plan rather than a truncated transcript preview alone.
7. `FR-7`: Project notes entered by the user must be sent to the model in both chat and generation flows.
8. `FR-8`: The application must maintain one shared editorial state containing at least transcript summary, synopsis, suggested plan, accepted plan, project notes, and freshness metadata.
9. `FR-9`: The Generate flow must automatically consume the latest accepted plan when present.
10. `FR-10`: If no accepted plan exists, the Generate flow must explicitly fall back to the latest suggested plan and surface that fact to the user.
11. `FR-11`: The UI must show ingest status, last refresh time, and whether the current editorial context is fresh or stale.
12. `FR-12`: Editing the brief or project context after ingest must mark the editorial context stale until the user refreshes it.
13. `FR-13`: The ingest flow must not write output XML files or trigger final sequence generation by itself.
14. `FR-14`: The system must preserve transcript timecodes exactly as parsed and must not introduce ingest-time mutations that break downstream validation.
15. `FR-15`: The implementation must work with the existing browser constraint that transcript and XML contents are uploaded from the client, not loaded from server-local paths.
16. `FR-16`: The design must support a future single-workspace UI without requiring another rewrite of context storage and handoff behavior.

## Non-Goals

- Replacing the existing XML generation engine or timecode validation rules.
- Automatically producing a final XML cut during the ingest step.
- Building long-term cross-project memory or a multi-project asset library.
- Solving multi-user collaboration, version history, or remote project syncing.
- Redesigning the entire web app visual system in this phase.

## Design Considerations

- The short-term UI may remain split across the current Chat and Generate areas, but it must behave like one continuous workflow.
- The synopsis should be visible and easy to scan, because the user selected synopsis-first output rather than a detailed editorial map.
- Suggested plan and accepted plan should be visibly distinct to avoid ambiguity about what Generate will use.
- Project notes should feel real, not decorative; if the user edits them, the UI should show that they affect model context.
- A future merged workspace should be easier once shared editorial state exists; do not hard-code assumptions that Chat and Generate will stay separate forever.

## Technical Considerations

- The current split likely requires coordinated changes in [webapp.py](/home/dietrich001/bitebuilder/webapp.py), [static/app.js](/home/dietrich001/bitebuilder/static/app.js), [bitebuilder.py](/home/dietrich001/bitebuilder/bitebuilder.py), and [llm/prompts.py](/home/dietrich001/bitebuilder/llm/prompts.py).
- The ingest step should be a distinct server-side operation with a predictable response shape so both chat and generate can consume the same artifacts.
- Shared editorial state should live in one canonical session structure instead of being reconstructed differently per route.
- Existing fixture-backed tests in [tests/test_webapp.py](/home/dietrich001/bitebuilder/tests/test_webapp.py) should be extended to cover ingest creation, stale-state behavior, and Generate inheritance.
- Real inference still depends on local Ollama, so local tests should continue to use mocked model output where possible.
- XML generation should stay deterministic and should only consume normalized accepted-plan inputs plus existing source metadata.

## Success Metrics

- The user reaches a grounded first copilot response without manually copying transcript context into chat.
- The user can move from upload to meaningful editorial feedback in one continuous flow with no manual transfer between Chat and Generate.
- Generate uses the same accepted plan seen in Chat in 100% of tested happy-path sessions.
- Sessions with project notes show those notes reflected in chat and generation payloads during fixture-backed tests.
- Users spend fewer manual steps preparing a first generation than in the current Area 3 to Area 4 flow.

## Open Questions

- Should the near-term product keep separate Chat and Generate screens with shared state, or should the next phase merge them into one workspace?
- Should ingest run immediately on readiness in every case, or should there be a low-resource opt-out for slower local models?
- Should the synopsis be regenerated automatically after every major brief edit, or only when the user explicitly requests refresh?
- Should the user be able to inspect the raw transcript summary behind the synopsis, or only see the higher-level synopsis?