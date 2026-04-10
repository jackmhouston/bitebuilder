# `src/bitebuilder/` Inventory and Disposition

This inventory records the duplicate `src/bitebuilder/` package during the current stabilization window. The canonical runtime remains the top-level app documented in `docs/canonical-runtime-proof.md`: `bitebuilder.py`, `webapp.py`, `parser/`, `generator/`, and `llm/`.

No files in `src/bitebuilder/` were deleted, migrated, or made canonical in this tranche. Treat the tree as quarantined reference material until a follow-up migration/removal decision is approved.

| File | Current contents | Recommended disposition |
| --- | --- | --- |
| `src/bitebuilder/__init__.py` | Package marker with `__version__ = "0.1.0"`. | Remove later if the duplicate package is retired; otherwise update only as part of an approved `src/` migration. |
| `src/bitebuilder/__main__.py` | Module entrypoint delegating to `bitebuilder.cli.main`. | Remove later with the duplicate package, or port deliberately if packaging moves to `src/`. |
| `src/bitebuilder/cli.py` | Older packaged CLI around `GenerationRequest` and `run_generation`. | Archive/remove later after confirming no installer or docs still reference the package entrypoint; do not merge into top-level `bitebuilder.py` piecemeal. |
| `src/bitebuilder/gui.py` | Older standalone HTTP GUI/server with embedded HTML and request preparation helpers. | Archive/remove later after comparing any still-useful UX/request-normalization ideas against canonical `webapp.py`; do not make it a second UI runtime. |
| `src/bitebuilder/gui_launcher.py` | Thin wrapper that launches `bitebuilder.gui.main`. | Remove later with `gui.py` unless an approved `src/` migration keeps the packaged GUI. |
| `src/bitebuilder/models.py` | Dataclasses for the older packaged pipeline (`TranscriptSegment`, `PremiereProject`, `GenerationRequest`, etc.). | Remove later with the duplicate pipeline, or port as part of a single explicit domain-model migration. |
| `src/bitebuilder/pipeline.py` | Older generation pipeline wiring transcript parsing, Premiere XML parsing, LLM selection, and XMEML rendering. | Archive/remove later after validating canonical top-level behavior covers required flows; do not run both pipelines in parallel. |
| `src/bitebuilder/premiere_xml_parser.py` | Simpler Premiere XML parser producing packaged `PremiereProject`/`SourceClip` models. | Remove later or use only as reference while maintaining canonical `parser/premiere_xml.py`. |
| `src/bitebuilder/transcript_parser.py` | Simpler transcript parser for bracket/inline second-based time ranges. | Remove later or use only as reference while maintaining canonical `parser/transcript.py`. |
| `src/bitebuilder/xmeml_generator.py` | Simpler XMEML renderer using packaged models. | Remove later or use only as reference while maintaining canonical `generator/xmeml.py`. |
| `src/bitebuilder/prompts.py` | Older prompt builder for `GenerationRequest`/`TranscriptDocument`/`PremiereProject`. | Remove later or use only as reference while maintaining canonical `llm/prompts.py`. |
| `src/bitebuilder/ollama_client.py` | Minimal Ollama JSON client using `requests`. | Remove later or use only as reference; canonical Ollama behavior lives in `llm/ollama_client.py`. |
| `src/bitebuilder/claude_client.py` | Claude Code CLI JSON helper used by the packaged pipeline. | Decide explicitly in follow-up: port if Claude provider support is still desired in the canonical app, otherwise archive/remove with the duplicate package. |

## Follow-up recommendation

1. Search docs, packaging metadata, and scripts for `src.bitebuilder`, `bitebuilder.cli`, and `bitebuilder.gui` references before removal.
2. If no live references remain, archive or delete `src/bitebuilder/` in one dedicated follow-up change with regression tests passing before and after.
3. If any feature from this tree is still required, port it into the canonical top-level modules first, with tests, then remove the duplicate implementation.
