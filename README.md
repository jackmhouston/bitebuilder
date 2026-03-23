# BiteBuilder

BiteBuilder turns a timecoded interview transcript, a Premiere Pro XML export, and a creative brief into importable Premiere Pro XML sequences.

It supports:

- a CLI for direct local runs
- a local Flask app for upload, copilot chat, and export
- deterministic XML generation and fixture-backed tests

Real editorial selection still depends on a local Ollama model. The checked-in tests use mocked LLM output and synthetic fixtures, not real client media.

## Requirements

- Python 3.10+
- `requests`
- [Ollama](https://ollama.com) for live generation
- Adobe Premiere Pro for importing generated XML

Optional for browser smoke tests:

- Node.js
- `npm install`

## Repo Layout

- `bitebuilder.py`: CLI entrypoint and orchestration flow
- `webapp.py`: local Flask UI for upload, chat loops, and sequence generation
- `parser/`: transcript parsing and Premiere XML metadata extraction
- `generator/`: timecode math and XMEML sequence generation
- `llm/`: prompt templates and Ollama HTTP client
- `templates/` and `static/`: browser UI assets
- `tests/`: fixture-backed Python tests plus Playwright browser smoke tests
- `docs/codebase-index.md`: quick architecture map

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

If you want to run the Playwright smoke suite:

```bash
npm install
```

For live LLM runs:

```bash
ollama serve
```

The default local model is `qwen3:8b`.

## CLI Usage

Inspect the interface:

```bash
.venv/bin/python bitebuilder.py --help
```

Run a fixture-backed example:

```bash
.venv/bin/python bitebuilder.py \
  --transcript tests/fixtures/sample_transcript.txt \
  --xml tests/fixtures/sample_premiere.xml \
  --brief "45 second proof of concept" \
  --output ./output
```

Typical usage:

```bash
.venv/bin/python bitebuilder.py \
  --transcript interview_transcript.txt \
  --xml premiere_export.xml \
  --brief "45 second proof of concept, start with objections, pivot to operating upside, end inspiring" \
  --output ./output
```

CLI defaults:

- `--options 3`
- `--model qwen3:8b`
- `--output ./output`
- `--host http://127.0.0.1:11434`
- `--timeout 180`
- `--thinking-mode auto`

For Qwen models, `--thinking-mode on` enables explicit reasoning and `--thinking-mode off` forces no-think behavior.

## Web App

Run the local server:

```bash
.venv/bin/python webapp.py
```

Then open `http://127.0.0.1:8000`.

The current browser workflow is:

1. Upload
2. Validate
3. Preview/Confirm
4. Generate
5. Download

Important constraint: the web UI expects transcript and Premiere XML contents to be uploaded from the browser client. It does not take local server-side file paths as inputs during normal use.

The copilot page is intentionally simplified. It keeps transcript, brief, suggestion, and accepted-plan context visible, but the old copilot model/timeout controls are no longer part of the UI.

If a server-side preset exists under `testing/`, the UI can preload transcript, XML, brief, and related context for local development.

## Determinism And Validation

BiteBuilder is strict about reproducibility and transcript matching:

- transcript timecodes must match the LLM output exactly
- every returned `tc_in` and `tc_out` is validated against transcript boundaries
- XML generation should stay deterministic where possible

Selection requests are controlled by:

- `BITEBUILDER_SELECTION_TEMPERATURE` default `0.0`
- `BITEBUILDER_SELECTION_SEED` default `0`

Example:

```bash
export BITEBUILDER_SELECTION_TEMPERATURE=0.0
export BITEBUILDER_SELECTION_SEED=0
.venv/bin/python bitebuilder.py --transcript transcript.txt --xml export.xml --brief "..."
```

## Tests

Run the Python suite:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Run the Playwright smoke suite:

```bash
npm run test:playwright
```

The browser smoke coverage currently includes:

- bite card rendering
- copilot page smoke coverage
- layout margin checks
- siderail cleanup checks

## Transcript Format

```text
HH:MM:SS:FF - HH:MM:SS:FF
Speaker 1
Dialogue text goes here...

HH:MM:SS:FF - HH:MM:SS:FF
Speaker 2
More dialogue...
```

## How It Works

1. Parse transcript blocks into exact timecode segments.
2. Parse the Premiere XML export for source media metadata.
3. Build the editorial prompt and send it to Ollama.
4. Validate returned timecodes against the transcript.
5. Generate one importable XMEML sequence per edit option.
6. Import the XML into Premiere and refine there.

## Premiere Import

1. Generate one or more XML sequences with BiteBuilder.
2. In Premiere Pro, open `File > Import`.
3. Select the generated `.xml` file or files.
4. Each XML imports as a sequence with linked video and stereo audio clips.

## Notes

- `output/` and `test_output/` are generated artifacts.
- The checked-in tests are designed to be machine-independent and fixture-backed.
- `docs/codebase-index.md` is the fastest architecture reference if you are orienting yourself in the repo.
