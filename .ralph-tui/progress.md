# Ralph Progress Log

This file tracks progress across iterations. Agents update this file
after each iteration and it's included in prompts for context.

## Codebase Patterns (Study These First)

*Add reusable patterns discovered during development here.*

### Reusable Pattern: Force chat re-render in Playwright via page state mutation
- For UI rendering smoke checks on the copilot page, preload synthetic chat payload in `localStorage`, navigate, then mutate `window.state` in-browser and call `window.renderAll()` (or `renderChat()` fallback) to validate chat rendering behavior deterministically without issuing backend requests.

### Reusable Pattern: Playwright computed-style assertions
- Validate spacing with `getComputedStyle` + numeric parsing instead of string equality to tolerate unit formatting differences (`px` values and fractional pixels).
- Reuse a short page bootstrap assertion (`expect(locator('.app-shell')).toBeVisible()`) before style reads so the layout test is deterministic across routes.

### Reusable Pattern: Local rendering passes with optional block-aware parsing
- Keep a small helper (`renderWithSegmentChips`) for existing `[N]` chip rendering.
- In the parent renderer, parse raw chat content into prose blocks and special blocks before running the shared chip renderer, so new block structures can coexist without changing existing behavior.
- Use `String#split("\\n")` and a dedicated block regex when you need to detect line-based markdown-ish sections in chat output.

### Reusable Pattern: Remove page-only UI by decoupling render bindings
- Keep global state fields for compatibility, but only bind them to nodes that are guaranteed to exist on the current page by guarding DOM access and dropping event listeners for removed controls.
- When a control is removed from one view, delete both binding and listener paths together to prevent stale references/undefined variables during page render.

## [2026-03-24] - US-002
- Removed the copilot siderail model configuration section from `templates/copilot.html`, leaving Transcript/Brief/Suggestion/Keep-for-generate cards only.
- Removed all JS reads/writes and event wiring for `modelSelect`, `thinkingModeSelect`, `timeoutInput`, and `checkModelsButton` from `static/app.js` and removed dead model-population logic tied to deleted nodes.
- Added `tests/playwright/siderail_cleanup.spec.js` to assert copilot has no `#modelSelect`, `#timeoutInput`, `#thinkingModeSelect`, or `#checkModelsButton` elements and capture console errors on page load.
- Kept `state.model`, `state.thinkingMode`, and `state.timeout` in state for API payload compatibility.
- **Learnings:**
  - Patterns discovered
    - Render and event wiring are page-agnostic; guard removed controls by deleting their selectors and listener branches wherever defined, even if helpers remain unused.
    - Targeted null checks in Playwright (`locator(...).toHaveCount(0)`) are a stable way to assert UI cleanup across templates and avoids page-specific selectors.
- Gotchas encountered
    - `populateModelSelect()` was still called in the render cycle after removing node references, which would have caused runtime failures when `modelSelect` was no longer defined; removing both call sites and function avoided this.
    - `fetchModels()` and model status updates still referenced removed status DOM nodes; these references needed to be removed even though model discovery logic itself can remain as dead code.
---

## [2026-03-24] - US-004
- Revalidated and finalized the full copilot smoke test story with no Python regressions.
- Files changed:
  - `tests/playwright/copilot_smoke.spec.js` (existing implementation aligned to acceptance checks)
  - `package.json` (Playwright script aligned to `npx playwright test`)
  - `playwright.config.js` (`headless` now CI-gated)
  - `.ralph-tui/progress.md` (append)
- **Learnings:**
  - Patterns discovered
    - Seeding `bitebuilder.studio.draft.v2` before navigation plus a forced `window.renderAll()` re-render is the most deterministic path for copilot rendering assertions.
    - CLI behavior can differ across environments (`playwright` global vs `npx playwright`) so script should prefer the CI-compatible explicit invocation.
  - Gotchas encountered
    - Local `playwright` CLI in this environment does not support `test`, so script compatibility required adjustment.
---

## [2026-03-24] - US-004
- Added `tests/playwright/copilot_smoke.spec.js` to run an end-to-end copilot UI smoke pass across combined UX changes from US-001 through US-003.
- The test navigates to `/project/copilot`, verifies page title/heading context, asserts `#modelSelect` and `#timeoutInput` are absent, checks `.app-shell` left padding is at least `24px`, injects a synthetic assistant bite block message, triggers a rerender via `window.state` and `renderAll()`, and verifies a `.bite-card` renders with `border-left-style: solid`.
- Confirmed required Playwright scaffolding (`playwright.config.js`, `test:playwright` script, dependency) already existed from prior work and was reused unchanged for this story.
- **Learnings:**
  - Patterns discovered
    - Reusing `page.addInitScript` to seed `bitebuilder.studio.draft.v2` creates deterministic chat fixtures without network interaction.
    - `window.renderAll()` is a reliable, low-flake way to force UI recomputation after in-browser state mutation for Playwright assertions.
  - Gotchas encountered
    - The copilot route is both `/project/chat` and `/project/copilot`; using the alias route keeps the test aligned with user-facing naming while still hitting existing template logic.
---

## [2026-03-24] - US-003
- Increased layout breathing room in `static/app.css` by updating `.app-shell` max-width to `1100px`, `.app-shell` padding to `24px`, `.panel-grid` gap to `20px`, `.message` padding with top/bottom set to `12px`, and `.chat-log` horizontal breathing room.
- Updated responsive behavior to `@media (max-width: 1060px)` to align with the widened shell.
- Added `tests/playwright/layout_margins.spec.js` with assertions for `.app-shell` left padding and `.message` top padding on `/project/chat`, plus a spot-check load test for `/project/intake`, `/project/generate`, and `/project/export`.
- Kept existing Playwright setup and selectors unchanged for compatibility with existing UI templates.
- **Learnings:**
  - Patterns discovered
    - Playwright CSS assertions are more robust when converting computed values with `parseFloat` and comparing minimum thresholds.
    - For pages where a `.message` may be absent initially, creating a temporary probe message in `.chat-log` allows style assertions without waiting for chat history to render.
  - Gotchas encountered
    - `.chat-log` already had generic padding from an earlier shared selector block, so explicit `.chat-log` padding needed a deliberate override to enforce the intended horizontal spacing.
---

## [2026-03-24] - US-001
- Implemented bite recommendation card rendering in `static/app.js` by parsing bold bite-block headers first, then rendering each detected block into `<div class="bite-card">` and running the existing segment-chip renderer on normal prose and card subsections (quote/why text).
- Added new visual styling in `static/app.css`:
  - `.bite-card` with blue tint, blue-left border, padding, rounded corners, spacing, and compact font.
  - `.bite-card-label` pill styling matching the requested background, color, size, and rounding.
- Added Playwright scaffolding for `tests/playwright/bite_cards.spec.js` and `playwright.config.js`, plus `package.json` `test:playwright` script and `@playwright/test` dev dependency declaration for running `playwright test`.
- Added `tests/playwright/bite_cards.spec.js` assertions for:
  - `.bite-card` rendering
  - `border-left-color` being `rgb(36, 88, 196)`
  - pill text matching the block label.
- **Learnings:**
  - Patterns discovered
    - Preserve existing chip behavior by extracting chip-only logic into a helper first, then layering block parsing around it.
    - Keep regex parsing line-based for minimal intrusion into existing renderer contracts.
  - Gotchas encountered
    - This environment cannot fetch npm/pypi packages (network DNS resolution failures), so Playwright dependency installation via CLI was blocked; `playwright` binary is preinstalled, but `@playwright/test` module is not currently available locally.
---
