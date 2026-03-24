# Ralph Progress Log

This file tracks progress across iterations. Agents update this file
after each iteration and it's included in prompts for context.

## Codebase Patterns (Study These First)

*Add reusable patterns discovered during development here.*

### Reusable Pattern: Local rendering passes with optional block-aware parsing
- Keep a small helper (`renderWithSegmentChips`) for existing `[N]` chip rendering.
- In the parent renderer, parse raw chat content into prose blocks and special blocks before running the shared chip renderer, so new block structures can coexist without changing existing behavior.
- Use `String#split("\\n")` and a dedicated block regex when you need to detect line-based markdown-ish sections in chat output.

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
