# Ralph Progress Log

This file tracks progress across iterations. Agents update this file
after each iteration and it's included in prompts for context.

## Codebase Patterns (Study These First)

*Add reusable patterns discovered during development here.*

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
