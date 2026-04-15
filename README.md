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
- Real editorial generation requires a local model runtime (Gemma 4 via llama-server by default; Ollama is still supported).
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

## Tonight MVP Smoke

Use the CLI/core path as the supported quick-start surface. The browser UI is
available for local exploration, but it is best-effort unless you also run the
Flask smoke below.

Set up a local environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

For fast local testing, use the repo launcher:

```bash
make print-alias
alias bitebuilder="$PWD/bin/bitebuilder"
bitebuilder smoke
```

Then `bitebuilder` opens the Go TUI after checking/starting the configured local
model runtime. `bitebuilder tui` skips model startup, and `bitebuilder model`
only starts/checks the model. If your model is not already running, set one of:

```bash
export BITEBUILDER_MODEL_PATH=/path/to/model.gguf
# or
export BITEBUILDER_MODEL_COMMAND='llama-server --host 127.0.0.1 --port 18084 --model /path/to/model.gguf'
```

Run the deterministic no-model XML smoke. This uses tracked sanitized fixtures
and does not require Ollama:

```bash
.venv/bin/python bitebuilder.py \
  --sequence-plan tests/fixtures/tonight_mvp/sequence_plan.json \
  --transcript tests/fixtures/tonight_mvp/transcript.txt \
  --xml tests/fixtures/tonight_mvp/source.xmeml \
  --output ./output/tonight-smoke
```

For live editorial generation, start the configured local model runtime first,
then run either the guided CLI or a direct generation:

```bash
.venv/bin/python bitebuilder.py --guided
```

```bash
.venv/bin/python bitebuilder.py \
  --transcript /path/to/transcript.txt \
  --xml /path/to/source.xml \
  --brief "45 second proof of concept with a clear hook and strong close" \
  --output ./output/live-test
```

Optional Flask route smoke:

```bash
.venv/bin/python - <<'PY'
import webapp
client = webapp.app.test_client()
for path in [
    "/",
    "/project/brief",
    "/project/chat",
    "/project/generate",
    "/project/export",
    "/project/logs",
    "/api/models",
]:
    resp = client.get(path)
    assert resp.status_code < 500, (path, resp.status_code)
print("flask smoke ok")
PY
```

CLI example:

```bash
.venv/bin/python bitebuilder.py \
  --transcript /path/to/transcript.txt \
  --xml /path/to/source.xml \
  --brief "45 second proof of concept" \
  --output ./output
```
