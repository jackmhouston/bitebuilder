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

- CLI/core pipeline is the current fundamentals focus: parse transcript + Premiere XML, validate exact transcript timecodes, call a local model, and generate XMEML
- Flask/copilot UI exists in the repo but is low-priority/inactive for the current fundamentals track
- deterministic validation around transcript boundaries, timecode math, and sequence generation

## Canonical Codepath

The current canonical application path is the top-level core:

- `bitebuilder.py` for the CLI pipeline
- `parser/`, `generator/`, and `llm/` for supporting logic

`webapp.py`, `templates/`, and `static/` remain in `main` for reference, but they are inactive/low-priority during the current fundamentals track. The duplicate `src/bitebuilder/` package has been inventoried in `docs/src-bitebuilder-inventory.md` and removed from the active tree.

## Screenshot Plan

Add one strong UI screenshot near the top of this README.

Target shot:

- the copilot UI (deferred while web UI is inactive/low-priority)
- step navigation visible
- one realistic assistant response rendered as bite cards
- brief and transcript context visible in the side panel
- clean browser crop with minimal dev noise

Deliverables:

- `docs/screenshots/bitebuilder-hero.png` for the README
- a tighter crop for portfolio or employment materials

## Workflow

1. Ingest a Premiere timecoded transcript and source XML metadata.
2. Shape editorial direction with project context, optional speaker names, and a concrete sequence goal.
3. Generate a structured sequence-plan artifact containing ordered bites, source segment references, rationales, and replacement/removal metadata.
4. Validate selected timecodes against the source transcript.
5. Export draft XMEML and continue refinement in the edit system.

## Notes

- The current interchange format is Premiere XML/XMEML.
- Real editorial generation requires a local Ollama model.
- The browser UI expects transcript and XML contents to be uploaded from the client, but it is inactive/low-priority for the current fundamentals track.
- Future refinement should operate on a structured sequence-plan artifact before adding chat/UI commands.

## Run Locally

Canonical local entrypoints for the fundamentals track:

- CLI help: `.venv/bin/python bitebuilder.py --help`
- Guided CLI: `.venv/bin/python bitebuilder.py --guided`

Inactive/low-priority UI entrypoint retained for reference:

- Web UI: `.venv/bin/python webapp.py`

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python bitebuilder.py --help
```

CLI example:

```bash
.venv/bin/python bitebuilder.py \
  --transcript /path/to/transcript.txt \
  --xml /path/to/source.xml \
  --brief "45 second proof of concept" \
  --output ./output
```
