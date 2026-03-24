# PRD: BiteBuilder Conversational Edit Workspace

## 1. Introduction/Overview

BiteBuilder already has the core XML generation logic, transcript parsing, shortlist building, and project JSON save/load support. The current web UX is the bottleneck. The editor has to front-load too much manual context, the chat surface feels detached from bite selection, and the final assembly/export flow does not feel like one continuous editorial loop.

This PRD reshapes the existing `Upload -> Write -> Chat -> Generate` web flow into a guided conversational editing workspace. After transcript upload, Premiere XML upload, and one short brief, BiteBuilder should infer a short project-understanding summary, show that summary back to the user for confidence, then let the user refine the cut through natural-language chat. Assistant replies should stay readable as normal prose while highlighting transcript bite references as selectable inline chips. Accepted guidance, section-specific corrections, saved bites, rejected bites, and the working A>B assembly order should stay connected from chat through final XML export.

The goal is not a distributed product or a media-review platform. The goal is a local, effective editorial copilot for one editor that feels like it understands the project, remembers direction, and helps shape a cut into an importable Premiere XML sequence.

## 2. Goals

- Reduce up-front typing to transcript upload, XML upload, and one short brief.
- Generate a confidence-building summary of the project before deeper chat begins.
- Keep assistant responses natural-language-first while making referenced bites directly actionable.
- Let the user save, reject, revise, and carry forward editorial direction without repetitive retyping.
- Keep the working A>B bite order visible and editable through export.
- Reuse and extend the existing local JSON project save/load system instead of replacing it.
- Preserve existing XML generation and timecode behavior while making the UX materially better.

## 3. User Stories

### US-001: Generate a project-understanding summary from uploaded material
**Description:** As an editor, I want BiteBuilder to infer a short summary from the transcript, XML, and one brief so I do not have to type a full project context memo before the model can help.

**Priority:** P1

**Acceptance Criteria:**
- [ ] Add an intake summary generation path that accepts transcript text, XML text, and one short brief.
- [ ] The returned understanding is a short paragraph written in editorial language, not a raw field dump.
- [ ] The summary can be generated without requiring the user to fill the long-form project context field first.
- [ ] Summary generation failures return recoverable error text and do not corrupt existing project state.
- [ ] Tests pass.
- [ ] Typecheck passes.

### US-002: Replace context-heavy intake with guided brief plus summary review
**Description:** As an editor, I want the intake step to ask for only the minimum necessary input and then show me what the model thinks the project is about before I move into chat.

**Priority:** P1  
**Depends on:** US-001

**Acceptance Criteria:**
- [ ] The intake flow requires transcript upload, XML upload, project title, and one short brief before the user continues.
- [ ] The long project-context textarea is removed from the required first-run path.
- [ ] The intake screen displays the generated short summary and lets the user approve or lightly edit it before chat.
- [ ] The primary continue action stays disabled until the required inputs are present and the summary has either been reviewed or explicitly skipped.
- [ ] Existing preset loading still hydrates the intake flow correctly.
- [ ] Verify in browser using dev-browser skill.
- [ ] Tests pass.
- [ ] Typecheck passes.

### US-003: Persist approved summary and intake metadata in project JSON files
**Description:** As an editor, I want the inferred summary and intake decisions saved with the project so I can stop rebuilding context every time I reopen a cut.

**Priority:** P1  
**Depends on:** US-001

**Acceptance Criteria:**
- [ ] Exported `.bitebuilder-project.json` files include the generated summary, approved summary text, brief, and related intake metadata.
- [ ] Loading a saved project restores the summary review state without data loss.
- [ ] Loading older project JSON files that do not have the new fields still works.
- [ ] The save/load behavior remains local-file-based and does not require a backend database.
- [ ] Tests pass.
- [ ] Typecheck passes.

### US-004: Render assistant replies as natural language with selectable bite chips
**Description:** As an editor, I want the assistant to answer in normal prose while highlighting referenced bites inline so I can keep useful selections without switching mental modes.

**Priority:** P1

**Acceptance Criteria:**
- [ ] Assistant replies continue to render as readable natural language paragraphs.
- [ ] Transcript segment references inside assistant replies render as visually distinct inline chips or buttons.
- [ ] Clicking an inline bite chip updates the saved state for that bite without clearing the current chat thread.
- [ ] Inline chip styling reflects the bite state at render time, including neutral, kept, opening, banned, and lane states when relevant.
- [ ] The interaction remains keyboard accessible.
- [ ] Verify in browser using dev-browser skill.
- [ ] Tests pass.
- [ ] Typecheck passes.

### US-005: Add response-level save, reject, and revise actions
**Description:** As an editor, I want to tell the copilot “keep this direction,” “that hook does not work,” or “be more creative” directly from the response I am looking at so iteration feels fast and grounded.

**Priority:** P1  
**Depends on:** US-004

**Acceptance Criteria:**
- [ ] Each assistant response exposes actions to save the response as guidance, reject or supersede it, and continue iterating from that response.
- [ ] Rejecting or revising a response captures lightweight correction text tied to that response instead of forcing the user to restate all context.
- [ ] The next chat request includes the approved guidance and the latest correction text in a deterministic way.
- [ ] The chat log visually distinguishes current guidance from superseded guidance.
- [ ] Verify in browser using dev-browser skill.
- [ ] Tests pass.
- [ ] Typecheck passes.

### US-006: Add a section-notes side panel for editorial memory
**Description:** As an editor, I want corrections and accepted guidance to accumulate in a side panel by section so I can steer hook, middle, and ending decisions without retyping them every turn.

**Priority:** P1  
**Depends on:** US-005

**Acceptance Criteria:**
- [ ] The chat screen includes a side panel with at least `Global`, `Hook`, `Middle`, and `Ending` note buckets.
- [ ] The user can save text from a chat response into one of these buckets or type directly into the side panel.
- [ ] Saved section notes are shown separately from freeform project notes.
- [ ] Subsequent chat and generation requests include the saved section notes in a stable prompt order.
- [ ] Side-panel content persists in the existing local project JSON save/load flow.
- [ ] Verify in browser using dev-browser skill.
- [ ] Tests pass.
- [ ] Typecheck passes.

### US-007: Unify bite state across chat, transcript, shortlist, and manual assembly
**Description:** As an editor, I want a bite I save or reject in one place to immediately mean the same thing everywhere else so the tool feels coherent.

**Priority:** P1  
**Depends on:** US-004

**Acceptance Criteria:**
- [ ] Saving or rejecting a bite from chat updates the same source-of-truth state used by the transcript browser, candidate shortlist, accepted plan, and manual lane.
- [ ] A bite cannot end up simultaneously marked kept and banned.
- [ ] Opening, must-use, kept, banned, locked, and lane states remain internally consistent after repeated edits.
- [ ] The app does not create a second independent state model just for chat-selected bites.
- [ ] Verify in browser using dev-browser skill.
- [ ] Tests pass.
- [ ] Typecheck passes.

### US-008: Turn the chat screen into the primary refinement workspace
**Description:** As an editor, I want the chat step to feel like the main place where the cut gets shaped, not just a text box before the real work begins.

**Priority:** P2  
**Depends on:** US-002, US-004, US-006, US-007

**Acceptance Criteria:**
- [ ] The chat screen presents the chat log, project-understanding summary, section-notes side panel, and the most relevant saved bite state in one coherent layout.
- [ ] The page shows the current project title, brief, approved summary, selected model, and core chat actions without requiring navigation away from the screen.
- [ ] The staged navigation remains `Upload -> Write -> Chat -> Generate`, but the chat page becomes the main refinement step.
- [ ] The layout remains usable on the current local browser UI without introducing media playback.
- [ ] Verify in browser using dev-browser skill.
- [ ] Tests pass.
- [ ] Typecheck passes.

### US-009: Make the working assembly board reflect the real A>B cut order
**Description:** As an editor, I want the generate step to show the current working bite order clearly so I can refine the actual sequence that will become XML.

**Priority:** P2  
**Depends on:** US-007

**Acceptance Criteria:**
- [ ] The working assembly view clearly shows the current A>B bite order that will feed export.
- [ ] The user can add, remove, reorder, and lock bites in the assembly without losing accepted chat guidance.
- [ ] Each bite in the working order shows enough context to identify why it is there, such as speaker, timecode, and selection rationale when available.
- [ ] The UI clearly distinguishes the manual assembly from candidate suggestions.
- [ ] Verify in browser using dev-browser skill.
- [ ] Tests pass.
- [ ] Typecheck passes.

### US-010: Tighten export around the visible working outcome
**Description:** As an editor, I want the final export step to feel like the natural end of the same editing loop, not a separate tool that ignores the choices I just made.

**Priority:** P2  
**Depends on:** US-009

**Acceptance Criteria:**
- [ ] The export area clearly shows the exact working order that will be passed into XML generation.
- [ ] The user can return from export to chat or assembly and keep the current project state intact.
- [ ] The result view explains how the exported cut relates to recent chat direction and saved guidance.
- [ ] XML generation continues to use the existing generator and timecode logic, with only adapter-level changes allowed for the new UX flow.
- [ ] Verify in browser using dev-browser skill.
- [ ] Tests pass.
- [ ] Typecheck passes.

### US-011: Feed approved summary and section notes into all model-facing flows
**Description:** As an editor, I want the same approved project understanding and section guidance to influence chat, shortlist building, and final generation so the tool does not feel forgetful.

**Priority:** P2  
**Depends on:** US-001, US-006

**Acceptance Criteria:**
- [ ] Chat prompt construction uses the approved summary, section notes, saved response guidance, and recent message history.
- [ ] Candidate shortlist generation uses the approved summary and section notes in addition to the brief.
- [ ] Final generation uses the same approved summary and section notes so the export path honors the chat workflow.
- [ ] Prompt assembly keeps a deterministic field order so saved projects replay predictably.
- [ ] Tests pass.
- [ ] Typecheck passes.

### US-012: Add regression coverage for the conversational editing loop
**Description:** As a maintainer, I want fixture-backed coverage for the new UX state and prompt wiring so the workflow can evolve without silently breaking.

**Priority:** P2  
**Depends on:** US-003, US-005, US-006, US-007, US-011

**Acceptance Criteria:**
- [ ] Add or update fixture-backed tests for summary generation state, chat bite-chip rendering inputs, section-note persistence, and project JSON round-tripping.
- [ ] Existing smoke tests continue to run without a live Ollama dependency.
- [ ] At least one test verifies that new saved-project fields are backward compatible with older project JSON files.
- [ ] Tests pass.
- [ ] Typecheck passes.

## 4. Functional Requirements

- FR-1: The system must accept transcript text, Premiere XML text, project title, and one short brief as the minimum guided-intake input.
- FR-2: The system must generate a short inferred project-understanding summary from the uploaded materials plus brief.
- FR-3: The system must let the user review and optionally edit the inferred summary before moving into deeper chat.
- FR-4: The system must store the approved summary in client project state and reuse it in later chat, shortlist, and export flows.
- FR-5: Assistant replies must remain natural-language-first while rendering referenced transcript segment indexes as inline actionable bite chips.
- FR-6: The user must be able to save or reject editorial direction at the response level without rewriting the full brief.
- FR-7: The system must support section-specific editorial notes inside the chat workflow, including at minimum `Global`, `Hook`, `Middle`, and `Ending`.
- FR-8: The system must keep bite selection state synchronized across chat, transcript browser, shortlist, accepted-plan views, and manual assembly.
- FR-9: The system must preserve a clear working A>B assembly order that the user can edit before export.
- FR-10: The export step must use the visible working order and explain the relationship between the output and the accepted direction.
- FR-11: The project JSON save/load flow must round-trip all new intake, guidance, section-note, and assembly fields.
- FR-12: The system must remain local-first and file-based, with no required backend persistence layer.
- FR-13: Error states for summary generation, chat, shortlist refresh, and export must be recoverable without forcing a full restart of the project.
- FR-14: Existing XML generation and timecode math must remain deterministic and must not be rewritten as part of this feature.

## 5. Non-Goals (Out of Scope)

- Adding media playback, waveform sync, or live video preview.
- Adding user accounts, multi-user collaboration, or cloud project storage.
- Rewriting transcript parsing or low-level Premiere XML generation logic beyond adapter changes needed for the UX.
- Redesigning the CLI flow as part of this PRD.
- Turning BiteBuilder into a general-purpose NLE.

## 6. Design Considerations

- Keep the current staged flow structure, but make the intake and chat stages much smarter and more connected.
- The summary should be short and confidence-building, not a large dashboard of tags and metadata.
- Assistant responses should look like natural prose first; bite chips should feel embedded inside the prose rather than bolted on underneath it.
- The side panel should act like editorial memory: easy to save into, easy to scan, and clearly separated by section.
- The generate/export step should visually communicate an A>B cut order, not just a list of machine-selected clips.
- The product is local and personal-use oriented, so clarity and speed matter more than enterprise settings or permissions.

## 7. Technical Considerations

- Reuse the existing `static/app.js` state model and `.bitebuilder-project.json` export/load behavior rather than introducing a new persistence system.
- Preserve compatibility with older saved project files that do not contain the new fields.
- Prefer new backend endpoints or small prompt-builder extensions over broad refactors of XML generation code.
- Existing segment index handling already powers inline chat chip parsing; extend that model rather than inventing a new bite-reference format.
- Keep prompt-field ordering deterministic so repeated runs from the same saved project behave predictably.
- Add fixture-backed tests rather than machine-specific or live-Ollama-only coverage.

## 8. Success Metrics

- A user can go from upload to first useful chat turn with only a short brief and no long-form project context block.
- The user can understand why the tool thinks it understands the project before the main chat loop begins.
- The user can save or reject bites and editorial direction directly from chat without hunting through the transcript for the same segments.
- The working assembly stays synchronized with chat-driven decisions and exports to a valid Premiere XML sequence.
- Saving and reloading the project restores the conversational editing state closely enough that work can resume without reconstruction.

## 9. Open Questions

- Should the summary be generated automatically as soon as the brief is entered, or only when the user explicitly asks BiteBuilder to analyze the project?
- Should saved response-level guidance stay as plain text only, or should the app also tag it by intent in a later phase?
- Should section-note buckets stay fixed to `Global`, `Hook`, `Middle`, and `Ending`, or become user-configurable later?