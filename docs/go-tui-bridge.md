# Go TUI bridge

This bridge gives the Go TUI a stable, non-server way to inspect
BiteBuilder state and ask the existing Python backend for model-assistant help
without importing Python internals or mutating output files. It is intentionally
request/response JSON over a Python subprocess for setup/media/plan/transcript/
summary/bite screens and for the lightweight `assistant` creative-ask helper.
Generation and export use the documented NDJSON subprocess event stream.

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
python bitebuilder.py --go-tui-bridge summary \
  --transcript interview.txt \
  --xml premiere-export.xml
python bitebuilder.py --go-tui-bridge assistant \
  --transcript interview.txt \
  --xml premiere-export.xml \
  --brief "short proof point with a clear button"
python bitebuilder.py --go-tui-bridge assistant \
  --transcript interview.txt \
  --xml premiere-export.xml \
  --sequence-plan output/_sequence_plan.json \
  --brief "short proof point with a clear button" \
  --refine-instruction "why this bite?" \
  --selected-bites-json '{"selected_bites":[{"bite_id":"bite-001","segment_index":0,"tc_in":"00:00:00:00","tc_out":"00:00:02:00","text":"..."}]}'
python bitebuilder.py --go-tui-export \
  --transcript interview.txt \
  --xml premiere-export.xml \
  --sequence-plan output/_sequence_plan.json \
  --selected-bites-json '{"selected_bites":[{"bite_id":"bite-001","segment_index":0,"tc_in":"00:00:00:00","tc_out":"00:00:02:00"}]}'
```

The normal Python TUI remains unchanged:

```bash
python bitebuilder.py --tui
```

`--go-tui-bridge` bypasses the normal banner and human-readable CLI output so a
Go caller can treat stdout as JSON only.

## Runtime authority boundary

The setup response declares a `capabilities.runtime_boundary` object so the
Go TUI can display and regression-test the ownership split. Python remains
authoritative for `model_calls`, `sequence_plan_refinement`,
`sequence_plan_validation`, and `xmeml_generation`. The Go TUI role is
`bubble_tea_ui_and_subprocess_event_client`: it renders Bubble Tea state,
launches the Python subprocess, and consumes JSON/NDJSON stdout events.

## Selection-aware workspace reuse contract

The prototype intentionally reuses these backend/bridge entrypoints instead of
inventing Go-side business logic:

- `summary`: Python parses transcript/XML, calls the configured model, and
  returns `data.summary_text`; Go stores and renders that text in the workspace.
- `--go-tui-generate`: Python runs the first-pass pipeline and emits NDJSON
  `artifact` events for the sequence plan and XML; Go displays progress and then
  hydrates candidate/selected board state from the `plan` bridge.
- `plan`: Python validates/hydrates the sequence plan and returns
  `data.board.candidates`, `data.board.selected`, and `data.sequence_plan_path`;
  Go uses those fields as the editable workspace board.
- `assistant`: Python performs selection-aware model reasoning over the current
  creative ask, summary, selected-bite text/timecodes, and transcript context
  that Go passes through `--brief`.
- `--go-tui-export`: Go sends current selected-board intent via
  `--selected-bites-json`; Python applies, validates, writes the selected-board
  sequence-plan artifact, and renders the final XMEML.

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
| `summary` | `--transcript`, `--xml` | Send transcript/XML context to the configured Python model client and return one plain-text interview summary for the editorial workspace. |
| `plan` | `--transcript`, `--xml`, `--sequence-plan` | Validate and hydrate a sequence plan, returning option summaries and display text. |
| `bite` | `--transcript`, `--xml`, `--sequence-plan` | Return one bite and its transcript segment for a detail viewport. |
| `assistant` | `--transcript`, `--xml`, optional `--brief`, optional `--sequence-plan`, optional `--selected-bites-json`, optional `--refine-instruction` | Send parsed transcript/XML context to the configured Python model client and return a suggested creative-ask rewrite plus story beats; when selected bites are supplied, include their exact text/timecodes and the editor question so the response can reason about the current selection. |

Optional read-only selectors:

- `--bridge-start-index <int>`: first transcript segment index for viewport operations.
- `--bridge-count <int>`: maximum transcript segments returned; minimum is coerced to `1`.
- `--bridge-query <text>`: speaker/text substring search for transcript viewport operations.
- `--option-id <id>`: sequence-plan option selector for `plan`/`bite`; defaults to the first option.
- `--bridge-bite-id <id>`: exact bite id selector for `bite`.
- `--bridge-segment-index <int>`: select the first bite that references a transcript segment index.
- `--bridge-selected-position <int>`: one-based selected bite selector for `bite`.
- `--selected-bites-json <json>`: selected-board context for selection-aware `assistant`, and selected-board intent for final `--go-tui-export`.
- `--refine-instruction <text>`: editor question/instruction for selection-aware `assistant`, and refinement instruction for `--go-tui-refine`.

When no bite selector is supplied, `bite` returns the first selected bite, or the
first bite if an option has no selected bites.

## Mutation boundary

The request/response bridge does not call `run_pipeline`,
`render_sequence_plan`, `refine_sequence_plan`, or any builder edit function.
Setup/media/plan/transcript/bite only read supplied files, parse/validate them
in memory, and print JSON. The `summary` and `assistant` operations additionally
call the configured Python model client (`generate_text`) but still do not render
XML, edit a sequence plan, or write output files. Selection-aware `assistant`
calls may include selected-board JSON; Python only uses it to enrich the model
prompt with current bite text/timecodes and returns that same selection context
in the response envelope.

The NDJSON export command is the mutation boundary for final XML output. The Go
TUI may pass current selected-board intent as `--selected-bites-json`, but Python
applies that intent, validates transcript/timecode bounds, writes any revised
exportable plan artifact, and renders XMEML. Go must not write generated plan or
XML artifacts directly.
