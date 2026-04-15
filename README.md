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

- the browser workspace at `/workspace` is the current best interactive surface for shaping a cut
- the Python core remains authoritative for transcript parsing, exact timecode validation, shortlist/generation logic, and XMEML export
- the Go TUI remains in the repo as a paused prototype surface while UI/UX work is focused on the web workspace
- deterministic validation around transcript boundaries, timecode math, and sequence generation stays central regardless of surface

## Canonical Codepath

The current canonical application path is the top-level Python core plus the local browser workspace:

- `webapp.py` for the current selection-first workspace flow
- `bitebuilder.py` for CLI entrypoints and orchestration
- `parser/`, `generator/`, and `llm/` for authoritative parsing, validation, prompting, and export logic
- `templates/` and `static/` for the active browser UI

The duplicate `src/bitebuilder/` package has been inventoried in `docs/src-bitebuilder-inventory.md` and removed from the active tree. The Go TUI under `go-tui/` is currently on hold; product and UX decisions should treat the browser workspace as the primary interactive surface.

## Screenshot Plan

Add one strong UI screenshot near the top of this README.

Target shot:

- the browser workspace at `/workspace`
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
- The browser workspace expects transcript and XML contents to be uploaded from the client.
- Multi-source combine support is currently safest when paired XMLs reference the same underlying source media timeline.
- Future refinement should continue to operate on a structured sequence-plan artifact instead of hiding editorial state behind wizard-like flows.

## Run Locally

Preferred local entrypoint:

- Browser workspace: `make workspace`, then open `http://127.0.0.1:8000/workspace`
- Browser launcher shortcut: `./bin/bitebuilder` or `./bin/bitebuilder workspace` (starts the local server, then open `http://127.0.0.1:8000/workspace`)

Other useful entrypoints:

- CLI help: `.venv/bin/python bitebuilder.py --help`
- Guided CLI: `.venv/bin/python bitebuilder.py --guided`
- Go TUI prototype on hold: `make tui`

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
make workspace
```

## Tonight MVP Smoke

Use the browser workspace as the preferred interactive surface. Use the CLI/core path for deterministic XML smoke checks. The Go TUI remains in the repo for reference, but active UI/UX work is focused on the webapp.

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

Then `bitebuilder` starts the browser workspace server; open `http://127.0.0.1:8000/workspace` in your browser. Use `bitebuilder tui` only for the paused Go TUI prototype, and `bitebuilder model`
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
