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
- `tests/`: local fixtures and smoke tests that do not require Ollama.
- `docs/codebase-index.md`: quick architecture map.

## Commands
- `.venv/bin/python -m unittest discover -s tests -v`
- `.venv/bin/python bitebuilder.py --help`
- `.venv/bin/python webapp.py`
- `.venv/bin/python bitebuilder.py --transcript tests/fixtures/sample_transcript.txt --xml tests/fixtures/sample_premiere.xml --brief "45 second proof of concept" --output ./output`

## Constraints
- Real editorial generation requires Ollama running locally.
- The browser UI expects transcript and XML file contents to be provided from the client, not local server-side file paths.
- Transcript timecodes must match the LLM output exactly.
- The checked-in tests use mocked LLM output and synthetic fixtures, not real client media.

## Working Notes
- Keep XML generation deterministic where possible.
- Prefer adding fixture-backed tests over hardcoded machine-specific paths.
- Treat `output/` and `test_output/` as generated artifacts.
