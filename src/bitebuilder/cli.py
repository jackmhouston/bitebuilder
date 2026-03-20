from __future__ import annotations

import argparse
from pathlib import Path

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
    generate.add_argument(
        "--provider",
        choices=("ollama", "claude-code"),
        default="ollama",
        help="LLM provider for selection passes.",
    )
    generate.add_argument("--title", default="BiteBuilder Selects", help="Generated sequence title.")
    generate.add_argument(
        "--model",
        help="Model name or alias. Defaults to gemma3:12b for Ollama and sonnet for Claude Code.",
    )
    generate.add_argument("--ollama-url", default="http://127.0.0.1:11434", help="Ollama base URL.")
    generate.add_argument(
        "--claude-command",
        default="claude",
        help="Claude Code executable path when using provider=claude-code.",
    )
    generate.add_argument(
        "--claude-auth-token",
        help="Optional ANTHROPIC_AUTH_TOKEN override passed to Claude Code.",
    )
    generate.add_argument("--dry-run", action="store_true", help="Skip Ollama and use local heuristics.")
    gui = subparsers.add_parser("gui", help="Launch the localhost web UI.")
    gui.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    gui.add_argument("--port", type=int, default=8765, help="Port to bind. Use 0 for a random free port.")
    gui.add_argument("--no-browser", action="store_true", help="Do not automatically open a browser.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "gui":
        from bitebuilder.gui import main as gui_main

        gui_args: list[str] = ["--host", args.host, "--port", str(args.port)]
        if args.no_browser:
            gui_args.append("--no-browser")
        gui_main(gui_args)
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
        provider=args.provider,
        sequence_title=args.title,
        model=args.model,
        ollama_url=args.ollama_url,
        claude_command=args.claude_command,
        claude_auth_token=args.claude_auth_token,
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
