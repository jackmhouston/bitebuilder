# Go TUI bridge

This bridge gives the Go TUI a stable, non-server way to inspect
BiteBuilder state and ask the existing Python backend for model-assistant help
without importing Python internals or mutating output files. It is intentionally
request/response JSON over a Python subprocess for setup/media/plan/transcript/
bite screens and for the lightweight `assistant` creative-brief rewrite. Future
model-backed sequence generation progress should use an NDJSON subprocess event
stream after that transport is documented in the Phase 4 ADR.

## Command shape

Use `bitebuilder.py` with `--go-tui-bridge` (aliases:
`--go-tui-bridge-command`, `--bridge-command`). The command prints exactly one
JSON envelope to stdout and exits with status `0` for success or `1` for a
structured error.

```bash
python bitebuilder.py --go-tui-bridge setup
python bitebuilder.py --go-tui-bridge media \
  --transcript interview.txt \
  --xml premiere-export.xml
python bitebuilder.py --go-tui-bridge plan \
  --transcript interview.txt \
  --xml premiere-export.xml \
  --sequence-plan output/_sequence_plan.json
python bitebuilder.py --go-tui-bridge assistant \
  --transcript interview.txt \
  --xml premiere-export.xml \
  --brief "short proof point with a clear button"
```

The normal Python TUI remains unchanged:

```bash
python bitebuilder.py --tui
```

`--go-tui-bridge` bypasses the normal banner and human-readable CLI output so a
Go caller can treat stdout as JSON only.

## Envelope contract

Successful response:

```json
{
  "ok": true,
  "schema_version": "go_tui_bridge.v1",
  "operation": "setup",
  "data": {}
}
```

Error response:

```json
{
  "ok": false,
  "schema_version": "go_tui_bridge.v1",
  "operation": "media",
  "error": {
    "code": "INPUT-NOT-FOUND",
    "type": "missing_transcript_file",
    "message": "Input file not found: interview.txt",
    "expected_input_format": "Path to an existing UTF-8 file.",
    "next_action": "Verify the path is correct and re-run.",
    "recoverable": false,
    "stage": "input",
    "details": {}
  }
}
```

All bridge errors use the existing BiteBuilder structured error shape inside the
outer envelope. Invalid bridge operations are reported as JSON instead of using
`argparse` choices so stdout remains machine-readable.

## Operations

| Operation | Required args | Purpose |
| --- | --- | --- |
| `setup` | none | Return bridge capabilities, defaults, and supplied path args for the welcome/setup screen. |
| `media` | `--transcript`, `--xml` | Parse transcript and Premiere XML, then return source metadata and a transcript window. |
| `transcript` | `--transcript`, `--xml` | Return a transcript viewport for path/file selection and search screens. |
| `plan` | `--transcript`, `--xml`, `--sequence-plan` | Validate and hydrate a sequence plan, returning option summaries and display text. |
| `bite` | `--transcript`, `--xml`, `--sequence-plan` | Return one bite and its transcript segment for a detail viewport. |
| `assistant` | `--transcript`, `--xml`, optional `--brief` | Send parsed transcript/XML context to the configured Python model client and return a suggested creative-brief rewrite plus story beats. |

Optional read-only selectors:

- `--bridge-start-index <int>`: first transcript segment index for viewport operations.
- `--bridge-count <int>`: maximum transcript segments returned; minimum is coerced to `1`.
- `--bridge-query <text>`: speaker/text substring search for transcript viewport operations.
- `--option-id <id>`: sequence-plan option selector for `plan`/`bite`; defaults to the first option.
- `--bridge-bite-id <id>`: exact bite id selector for `bite`.
- `--bridge-segment-index <int>`: select the first bite that references a transcript segment index.
- `--bridge-selected-position <int>`: one-based selected bite selector for `bite`.

When no bite selector is supplied, `bite` returns the first selected bite, or the
first bite if an option has no selected bites.

## Mutation boundary

The bridge does not call `run_pipeline`, `render_sequence_plan`,
`refine_sequence_plan`, or any builder edit function. Setup/media/plan/
transcript/bite only read supplied files, parse/validate them in memory, and
print JSON. The `assistant` operation additionally calls the configured Python
model client (`generate_text`) to produce a creative-brief rewrite, but still
does not render XML, edit a sequence plan, or write output files. This keeps the
Go TUI safe while allowing live model-assistant testing before the
future NDJSON generation transport is implemented.
