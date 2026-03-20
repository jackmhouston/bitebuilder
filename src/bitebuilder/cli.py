from __future__ import annotations

import argparse
from pathlib import Path

from bitebuilder.gui_support import tkinter_unavailable_message
from bitebuilder.models import GenerationRequest
from bitebuilder.pipeline import run_generation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bitebuilder",
        description="Build transcript-driven bite-select Premiere XML sequences.",
    )
    subparsers = parser.add_subparsers(dest="command")

    generate = subparsers.add_parser("generate", help="Run the local selection pipeline.")
    generate.add_argument("--transcript", required=True, help="Path to transcript .txt file.")
    generate.add_argument("--premiere-xml", required=True, help="Path to source Premiere XML export.")
    generate.add_argument("--brief", help="Creative brief text.")
    generate.add_argument("--brief-file", help="Optional path to a text file with the brief.")
    generate.add_argument("--output", help="Where to write the generated XMEML file.")
    generate.add_argument("--title", default="BiteBuilder Selects", help="Generated sequence title.")
    generate.add_argument("--model", default="gemma3:12b", help="Ollama model name.")
    generate.add_argument("--ollama-url", default="http://127.0.0.1:11434", help="Ollama base URL.")
    generate.add_argument("--dry-run", action="store_true", help="Skip Ollama and use local heuristics.")

    subparsers.add_parser("gui", help="Launch the desktop GUI.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "gui":
        try:
            from bitebuilder.gui import main as gui_main
        except ModuleNotFoundError as exc:
            if exc.name == "_tkinter":
                raise SystemExit(tkinter_unavailable_message()) from exc
            raise

        gui_main()
        return 0

    if args.command != "generate":
        parser.print_help()
        return 1

    brief = _resolve_brief(args.brief, args.brief_file)
    transcript_path = Path(args.transcript).expanduser().resolve()
    output_path = _resolve_output_path(args.output, transcript_path)
    request = GenerationRequest(
        transcript_path=transcript_path,
        premiere_xml_path=Path(args.premiere_xml).expanduser().resolve(),
        brief=brief,
        output_path=output_path,
        sequence_title=args.title,
        model=args.model,
        ollama_url=args.ollama_url,
        dry_run=args.dry_run,
    )

    result = run_generation(request, logger=print)
    print(
        f"Completed {result.sequence_title} with {result.selected_count} selections -> {result.output_path}"
    )
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f"- {warning}")
    return 0


def _resolve_brief(brief: str | None, brief_file: str | None) -> str:
    if brief and brief_file:
        raise SystemExit("Use either --brief or --brief-file, not both.")
    if brief_file:
        return Path(brief_file).expanduser().resolve().read_text(encoding="utf-8").strip()
    if brief:
        return brief.strip()
    raise SystemExit("A creative brief is required via --brief or --brief-file.")


def _resolve_output_path(output: str | None, transcript_path: Path) -> Path:
    if output:
        return Path(output).expanduser().resolve()
    return transcript_path.with_name(f"{transcript_path.stem}_bitebuilder.xml")
