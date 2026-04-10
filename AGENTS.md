# BiteBuilder Agent Guide

## Goal
BiteBuilder turns a timecoded interview transcript, a Premiere Pro XML export, and a creative brief into importable Premiere XML sequences.

## Repo Shape
- `bitebuilder.py`: CLI entrypoint and orchestration flow.
- `webapp.py`: local Flask UI for file upload, chat loops, and sequence generation.
- `parser/`: transcript parsing and Premiere XML metadata extraction.
- `generator/`: timecode math and XMEML sequence generation.
- `llm/`: prompt templates and Ollama HTTP client.
- `templates/` and `static/`: browser UI assets.
- `docs/codebase-index.md`: quick architecture map.

## Commands
- `.venv/bin/python bitebuilder.py --help`
- `.venv/bin/python webapp.py`
- `.venv/bin/python bitebuilder.py --transcript /path/to/transcript.txt --xml /path/to/source.xml --brief "45 second proof of concept" --output ./output`

## Constraints
- Real editorial generation requires Ollama running locally.
- The browser UI expects transcript and XML file contents to be provided from the client, not local server-side file paths.
- Transcript timecodes must match the LLM output exactly.

## Working Notes
- Keep XML generation deterministic where possible.
- Treat `output/` as generated artifacts.


## Behavioral Guidelines

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.