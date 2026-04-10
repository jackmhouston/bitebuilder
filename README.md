# BiteBuilder

> Active development.

BiteBuilder is a local-first editorial copilot for turning a timecoded interview transcript, source timeline metadata, and a creative brief into draft XML sequences for NLE ingest.

The current export target is Premiere/XMEML, but the product idea is broader than Premiere: speed up bite selection, narrative shaping, and first-pass assembly for interview-driven editing workflows.

## What It Does

- parses timecoded transcripts into exact selectable segments
- uses a local model to propose structured bite selections against a brief
- validates returned timecodes against the source transcript
- generates draft sequence XML for import and refinement in an NLE
- supports both a CLI flow and a local browser-based copilot flow

## Why It Matters

BiteBuilder is a compact product and systems project at the intersection of:

- editorial workflow design
- deterministic validation around LLM output
- practical local-first tooling
- human-in-the-loop creative software

## Current State

- working local prototype with routed upload, validation, preview, generate, and download steps
- copilot UI for transcript-aware prompting and bite review
- deterministic validation around transcript boundaries and sequence generation

## Canonical Codepath

The current canonical application path is the top-level app:

- `bitebuilder.py` for the CLI pipeline
- `webapp.py` for the local Flask UI
- `parser/`, `generator/`, and `llm/` for supporting logic

The alternate `src/bitebuilder/` package is not the active runtime path for this prototype and should be treated as inactive until an explicit migration plan lands.

## Screenshot Plan

Add one strong UI screenshot near the top of this README.

Target shot:

- the copilot UI
- step navigation visible
- one realistic assistant response rendered as bite cards
- brief and transcript context visible in the side panel
- clean browser crop with minimal dev noise

Deliverables:

- `docs/screenshots/bitebuilder-hero.png` for the README
- a tighter crop for portfolio or employment materials

## Workflow

1. Ingest a timecoded transcript and source XML metadata.
2. Shape the editorial direction with a concise brief.
3. Ask the copilot for hooks, arcs, and candidate bite selections.
4. Validate selected timecodes against the source transcript.
5. Export draft XML and continue refinement in the edit system.

## Notes

- The current interchange format is Premiere XML/XMEML.
- Real editorial generation requires a local Ollama model.
- The browser UI expects transcript and XML contents to be uploaded from the client.

## Run Locally

Canonical local entrypoints:

- Web UI: `.venv/bin/python webapp.py`
- CLI: `.venv/bin/python bitebuilder.py --help`

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python webapp.py
```

CLI example:

```bash
.venv/bin/python bitebuilder.py \
  --transcript /path/to/transcript.txt \
  --xml /path/to/source.xml \
  --brief "45 second proof of concept" \
  --output ./output
```
