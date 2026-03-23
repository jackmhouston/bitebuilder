# Codebase Index

## Runtime Flow
1. `bitebuilder.py` parses the transcript and Premiere XML.
2. `llm/prompts.py` builds the editorial prompt and validates the JSON reply.
3. `llm/ollama_client.py` sends the request to Ollama and applies Qwen thinking-mode controls.
4. `generator/xmeml.py` converts approved cuts into Premiere-importable XMEML.
5. The CLI writes one XML per edit option plus `_llm_response.json`.
6. `webapp.py` layers a local browser UI on top of the same pipeline with routed intake, context, copilot, and output pages plus the same chat and generation endpoints.

## Key Files

| Path | Purpose |
| --- | --- |
| `bitebuilder.py` | CLI entrypoint, argument parsing, orchestration, output writing |
| `webapp.py` | Flask UI and API routes for chat loops, model selection, and XML downloads |
| `templates/` and `static/` | Routed GUI shell, multi-step pages, shared styling, and browser-side draft state |
| `parser/transcript.py` | Parses transcript blocks into `TranscriptSegment` records |
| `parser/premiere_xml.py` | Extracts source metadata from Premiere XML |
| `generator/timecode.py` | Converts between timecode, frame counts, and Premiere ticks |
| `generator/xmeml.py` | Builds linked video + stereo audio XMEML sequences |
| `llm/prompts.py` | Houses the system prompt and JSON response validation |
| `llm/ollama_client.py` | Thin Ollama HTTP client with JSON parsing |
| `testing/solar-project-cut-down-1/` | Real transcript/XML fixture, preset manifest, PRD context, and reference outputs |
| `tests/test_pipeline.py` | Local smoke coverage for parsing, generation, and CLI orchestration |
| `tests/test_webapp.py` | API smoke coverage for the local GUI backend |

## External Dependencies
- Python 3.10+
- `requests`
- Ollama for real inference
- Premiere Pro for consuming generated XML

## Current Prototype Boundaries
- The real Solar fixture is checked in and includes known-good importable reference XMLs.
- The local GUI works for preset loading, chat loops, and generation, but still needs polish for dev-server workflow and assistive UX.
- Model reliability is still the main product risk; strict timecode validation catches bad outputs, but bite selection quality is not yet consistently autonomous.
