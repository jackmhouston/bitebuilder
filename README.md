# BiteBuilder

Local-first Python tooling for turning a transcript, a Premiere XML export, and a creative brief into bite-select sequences you can open in Premiere.

This repo is a rough v1 scaffold. It gives you:

- a Python package layout that keeps CLI and GUI flows on the same pipeline
- a simple Tkinter desktop GUI for local/offline use
- transcript parsing, Premiere XML parsing, prompt construction, and Ollama wiring
- a placeholder XMEML sequence generator that can be refined against your reference doc
- checked-in technical docs for Premiere XML generation and local Claude-auth workflow

## Why Tkinter for v1

Tkinter keeps the GUI dependency-free and easy to run on the same machine as Ollama. For a first internal tool, that matters more than polish.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

If `bitebuilder-gui` later reports that Tkinter is unavailable, recreate the virtualenv with a Tk-enabled interpreter instead of a Homebrew Python build without `_tkinter`. On this WSL setup, that means:

```bash
rm -rf .venv
/usr/bin/python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Run the GUI:

```bash
bitebuilder-gui
```

If your Python build does not include Tk support, the GUI launcher will print a concrete interpreter suggestion when it can detect one.

Run the CLI:

```bash
bitebuilder generate \
  --transcript /path/to/transcript.txt \
  --premiere-xml /path/to/source.xml \
  --brief "Find a tight emotional arc for a 45 second short." \
  --output /path/to/bitebuilder_selects.xml
```

If Ollama is not available, or if you want a safe scaffold pass first, use:

```bash
bitebuilder generate \
  --transcript /path/to/transcript.txt \
  --premiere-xml /path/to/source.xml \
  --brief "Rough narrative pass" \
  --dry-run
```

## Docs

- [Premiere XML Technical Reference](docs/Premiere_XML_Generation_Technical_Reference.md)
- [Claude Auth Local Quickstart](docs/CLAUDE_AUTH_LOCAL_QUICKSTART.md)

## Project Layout

```text
src/bitebuilder/
  cli.py
  gui.py
  models.py
  transcript_parser.py
  premiere_xml_parser.py
  prompts.py
  ollama_client.py
  xmeml_generator.py
  pipeline.py
```

## Current State

The GUI is intentionally simple:

- transcript file picker
- Premiere XML picker
- sequence title
- local Ollama model + URL
- creative brief box
- output file picker
- run button + log panel

The XML generator is still a practical placeholder. It emits a sequence-shaped XMEML file using parsed source clip metadata, but it has not yet been hardened against all Premiere edge cases from your technical reference.

## Local Claude Workflow

If you want to use Claude locally while working on this repo without setting up Anthropic API keys, use the Claude account login flow described in [docs/CLAUDE_AUTH_LOCAL_QUICKSTART.md](docs/CLAUDE_AUTH_LOCAL_QUICKSTART.md).

That quickstart is for your local coding workflow around this repo. The BiteBuilder runtime in this scaffold still uses Ollama as its model backend.
