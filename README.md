# BiteBuilder

Local-first Python tooling for turning a transcript, a Premiere XML export, and a creative brief into bite-select sequences you can open in Premiere.

This repo is a rough v1 scaffold. It gives you:

- a Python package layout that keeps CLI and GUI flows on the same pipeline
- a localhost browser GUI for local/offline use
- transcript parsing, Premiere XML parsing, prompt construction, and Ollama wiring
- optional Claude Code provider support through your local Claude login or auth token override
- a placeholder XMEML sequence generator that can be refined against your reference doc
- checked-in technical docs for Premiere XML generation and local Claude-auth workflow

## Why Localhost UI for v1

A localhost browser UI keeps the GUI dependency-light and avoids Python build issues like missing Tk support. It is still a thin local wrapper around the same Python pipeline as the CLI.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Run the GUI:

```bash
bitebuilder-gui
```

That starts a local web server, prints a localhost URL, and attempts to open it in your browser.

The intended localhost flow is:

1. Drag in the transcript `.txt`
2. Drag in the Premiere stringout `.xml`
3. Write the story prompt
4. Choose `Ollama` or `Claude Code`
5. Generate the XML
6. Let the browser auto-download it, or provide an optional save path

Run the CLI:

```bash
bitebuilder generate \
  --transcript /path/to/transcript.txt \
  --premiere-xml /path/to/source.xml \
  --brief "Find a tight emotional arc for a 45 second short." \
  --provider ollama \
  --output /path/to/bitebuilder_selects.xml
```

Run the CLI with Claude Code instead of Ollama:

```bash
bitebuilder generate \
  --transcript /path/to/transcript.txt \
  --premiere-xml /path/to/source.xml \
  --brief "Find the sharpest 45 second story arc." \
  --provider claude-code \
  --model sonnet \
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

- transcript drag-and-drop
- Premiere XML drag-and-drop
- sequence title
- provider switch for Ollama or Claude Code
- local Ollama URL
- optional Claude command and auth token override
- creative brief box
- optional output path input with Windows-path support from WSL
- run button + log panel

The XML generator is still a practical placeholder. It emits a sequence-shaped XMEML file using parsed source clip metadata, but it has not yet been hardened against all Premiere edge cases from your technical reference.

## Local Claude Workflow

If you want to use Claude locally while working on this repo without setting up Anthropic API keys, use the Claude Code flow described in [docs/CLAUDE_AUTH_LOCAL_QUICKSTART.md](docs/CLAUDE_AUTH_LOCAL_QUICKSTART.md).

The current scaffold supports both:

- Ollama as the fully local inference backend
- Claude Code as a local CLI-backed provider using your saved Claude login or an optional auth token override
