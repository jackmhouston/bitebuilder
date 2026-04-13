"""No-dependency terminal UI for BiteBuilder's sequence build loop.

The curses layer is deliberately thin.  The stateful operations stay in
``TuiSession`` so they can be tested without launching an interactive terminal.
"""

from __future__ import annotations

import json
import os
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from llm.ollama_client import (
    DEFAULT_HOST,
    DEFAULT_MODEL,
    DEFAULT_THINKING_MODE,
    DEFAULT_TIMEOUT,
)


def _abspath(value: str | None) -> str:
    return os.path.abspath(os.path.expanduser(value or ""))


@dataclass
class TuiSession:
    """Mutable TUI session state backed by bitebuilder.py operations."""

    api: Any
    transcript_path: str | None = None
    xml_path: str | None = None
    plan_path: str | None = None
    output_dir: str = "./output"
    model: str = DEFAULT_MODEL
    host: str = DEFAULT_HOST
    timeout: int = DEFAULT_TIMEOUT
    thinking_mode: str = DEFAULT_THINKING_MODE
    option_id: str | None = None
    project_context: str = ""
    goal: str = ""
    max_bite_duration_seconds: float | None = None
    max_total_duration_seconds: float | None = None
    require_changed_selected_cuts: bool = False
    refinement_retries: int = 1
    transcript_text: str | None = None
    xml_text: str | None = None
    source: Any = None
    segments: list[Any] = field(default_factory=list)
    plan_payload: dict | None = None
    current_render: dict | None = None
    message: str = "Set transcript/XML paths, load a plan or run first pass."

    @classmethod
    def from_args(cls, args: Any, *, api: Any) -> "TuiSession":
        return cls(
            api=api,
            transcript_path=args.transcript,
            xml_path=args.xml,
            plan_path=getattr(args, "sequence_plan", None),
            output_dir=args.output,
            model=args.model,
            host=args.host,
            timeout=args.timeout,
            thinking_mode=args.thinking_mode,
            option_id=args.option_id,
            max_bite_duration_seconds=getattr(args, "max_bite_duration", None),
            max_total_duration_seconds=getattr(args, "max_total_duration", None),
            require_changed_selected_cuts=getattr(args, "require_changed_cuts", False),
            refinement_retries=getattr(args, "refinement_retries", 1),
            goal=args.brief or "",
        )

    def load_media(self) -> None:
        if not self.transcript_path or not self.xml_path:
            raise ValueError("Transcript and XML paths are required before loading.")
        self.transcript_text = self.api.read_text_file(_abspath(self.transcript_path))
        self.xml_text = self.api.read_text_file(_abspath(self.xml_path))
        self.source = self.api.parse_premiere_xml_safe(self.xml_text)
        try:
            self.segments = self.api.parse_transcript(
                self.transcript_text,
                strict=True,
                timebase=self.source.timebase,
                ntsc=self.source.ntsc,
            )
        except self.api.TranscriptValidationError as exc:
            raise self.api.BiteBuilderError(self.api.build_transcript_timecode_error(exc.errors)) from exc
        self.message = f"Loaded {len(self.segments)} transcript segments."

    def load_plan(self) -> None:
        if not self.plan_path:
            raise ValueError("Sequence plan path is required.")
        if not self.segments:
            self.load_media()
        text = self.api.read_text_file(_abspath(self.plan_path))
        self.plan_payload = json.loads(text)
        self._hydrate_plan_payload_text()
        self.api.SequencePlan.from_dict(self.plan_payload, transcript_segments=self.segments)
        self.message = f"Loaded plan: {_abspath(self.plan_path)}"

    def _hydrate_plan_payload_text(self) -> None:
        """Fill missing speaker/text fields from exact segment indexes for display."""
        if self.plan_payload is None:
            return
        for option in self.plan_payload.get("options", []):
            for bite in option.get("bites", []):
                segment_index = bite.get("segment_index")
                if not isinstance(segment_index, int) or segment_index < 0 or segment_index >= len(self.segments):
                    continue
                segment = self.segments[segment_index]
                bite.setdefault("speaker", segment.speaker)
                bite.setdefault("text", segment.text)

    def run_first_pass(self) -> None:
        if not self.goal.strip():
            raise ValueError("Goal / creative brief is required to run a first pass.")
        if not self.transcript_path or not self.xml_path:
            raise ValueError("Transcript and XML paths are required to run a first pass.")
        self.transcript_text = self.api.read_text_file(_abspath(self.transcript_path))
        self.xml_text = self.api.read_text_file(_abspath(self.xml_path))
        result = self.api.run_pipeline(
            transcript_text=self.transcript_text,
            xml_text=self.xml_text,
            brief=self.goal,
            options=1,
            model=self.model,
            output_dir=self.output_dir,
            host=self.host,
            timeout=self.timeout,
            project_context=self.project_context,
            thinking_mode=self.thinking_mode,
        )
        self.source = result["source"]
        self.segments = result["segments"]
        self.plan_path = result.get("sequence_plan_path")
        if not self.plan_path:
            raise ValueError("First pass did not produce _sequence_plan.json.")
        self.plan_payload = json.loads(self.api.read_text_file(self.plan_path))
        self._hydrate_plan_payload_text()
        self.message = f"First pass complete: {self.plan_path}"

    def current_plan(self):
        if self.plan_payload is None:
            return None
        return self.api.SequencePlan.from_dict(self.plan_payload, transcript_segments=self.segments)

    def summary_text(self) -> str:
        plan = self.current_plan()
        if plan is None:
            return "No sequence plan loaded yet."
        timebase = getattr(self.source, "timebase", 24)
        ntsc = getattr(self.source, "ntsc", True)
        return self.api.summarize_sequence_plan(plan, self.option_id, timebase=timebase, ntsc=ntsc)

    def transcript_text_for_view(self, *, query: str = "") -> str:
        if not self.segments:
            return "No transcript loaded yet."
        if query:
            return self.api._format_transcript_excerpt(self.segments, query=query, count=80)
        return self.api._format_transcript_excerpt(self.segments, start_index=0, count=len(self.segments))

    def _builder_dir(self) -> str:
        return os.path.join(self.output_dir, "tui-builder-session")

    def _write_rendered_edit(self, plan, *, action: str, summary: str) -> None:
        if self.plan_payload is None or self.transcript_text is None or self.xml_text is None or self.source is None:
            raise ValueError("Load media and a sequence plan before editing.")
        self.plan_payload, self.current_render = self.api._write_and_render_builder_plan(
            plan=plan,
            transcript_text=self.transcript_text,
            xml_text=self.xml_text,
            transcript_segments=self.segments,
            output_dir=self._builder_dir(),
            option_id=self.option_id,
            source=self.source,
            action=action,
            summary=summary,
            current_plan_payload=self.plan_payload,
        )
        self.plan_path = self.current_render["revision_path"]
        self.message = f"{summary} XML: {self.current_render['output_path']}"

    def add_segment(self, segment_index: int, position: int | None = None) -> None:
        plan = self.current_plan()
        if plan is None:
            raise ValueError("Load a sequence plan before adding a segment.")
        edited = self.api.add_segment_to_sequence_plan(
            plan,
            transcript_segments=self.segments,
            segment_index=segment_index,
            option_id=self.option_id,
            position=position,
            timebase=getattr(self.source, "timebase", 24),
            ntsc=getattr(self.source, "ntsc", True),
        )
        self._write_rendered_edit(edited, action="tui_add", summary=f"Added segment {segment_index}.")

    def delete_selected(self, selected_position: int) -> None:
        plan = self.current_plan()
        if plan is None:
            raise ValueError("Load a sequence plan before deleting a bite.")
        edited = self.api.remove_selected_bite_from_sequence_plan(
            plan,
            transcript_segments=self.segments,
            selected_position=selected_position,
            option_id=self.option_id,
            timebase=getattr(self.source, "timebase", 24),
            ntsc=getattr(self.source, "ntsc", True),
        )
        self._write_rendered_edit(edited, action="tui_delete", summary=f"Deleted selected bite {selected_position}.")

    def move_selected(self, from_position: int, to_position: int) -> None:
        plan = self.current_plan()
        if plan is None:
            raise ValueError("Load a sequence plan before moving a bite.")
        edited = self.api.move_selected_bite_in_sequence_plan(
            plan,
            transcript_segments=self.segments,
            from_position=from_position,
            to_position=to_position,
            option_id=self.option_id,
            timebase=getattr(self.source, "timebase", 24),
            ntsc=getattr(self.source, "ntsc", True),
        )
        self._write_rendered_edit(edited, action="tui_move", summary=f"Moved selected bite {from_position} to {to_position}.")

    def assistant_refine(self, instruction: str) -> None:
        if self.plan_payload is None or self.transcript_text is None or self.xml_text is None:
            raise ValueError("Load media and a sequence plan before assistant refinement.")
        result = self.api.refine_sequence_plan(
            sequence_plan_text=json.dumps(self.plan_payload),
            transcript_text=self.transcript_text,
            xml_text=self.xml_text,
            output_dir=self._builder_dir(),
            instruction=instruction,
            option_id=self.option_id,
            sequence_plan_path=self.plan_path,
            model=self.model,
            host=self.host,
            timeout=self.timeout,
            thinking_mode=self.thinking_mode,
            max_bite_duration_seconds=self.max_bite_duration_seconds,
            max_total_duration_seconds=self.max_total_duration_seconds,
            require_changed_selected_cuts=self.require_changed_selected_cuts,
            refinement_retries=self.refinement_retries,
        )
        self.current_render = result
        self.plan_path = result["revision_path"]
        self.plan_payload = result["sequence_plan"].to_dict()
        self._hydrate_plan_payload_text()
        self.message = f"Assistant revision rendered: {result['output_path']}"


def _safe_addstr(stdscr: Any, y: int, x: int, text: str, attr: int = 0) -> None:
    max_y, max_x = stdscr.getmaxyx()
    if y < 0 or y >= max_y or x >= max_x:
        return
    try:
        stdscr.addnstr(y, max(0, x), text, max(0, max_x - max(0, x) - 1), attr)
    except Exception:
        return


def _fit_line(text: str, width: int) -> str:
    """Fit a status/path line with a visible middle ellipsis instead of silent cutoff."""
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= 4:
        return text[:width]
    keep = max(1, (width - 3) // 2)
    return f"{text[:keep]}...{text[-(width - 3 - keep):]}"


def _wrap_panel_lines(text: str, width: int) -> list[str]:
    """Wrap panel text to terminal width while preserving readable indentation."""
    if width <= 1:
        return [""]
    wrapped_lines: list[str] = []
    for raw_line in text.splitlines() or [""]:
        if not raw_line:
            wrapped_lines.append("")
            continue
        leading = len(raw_line) - len(raw_line.lstrip(" "))
        subsequent_indent = " " * min(leading + 2, max(0, width - 1))
        wrapper = textwrap.TextWrapper(
            width=max(8, width),
            subsequent_indent=subsequent_indent,
            break_long_words=False,
            break_on_hyphens=False,
            replace_whitespace=False,
            drop_whitespace=True,
        )
        wrapped = wrapper.wrap(raw_line)
        wrapped_lines.extend(wrapped or [""])
    return wrapped_lines


def _prompt(stdscr: Any, curses: Any, label: str, default: str = "") -> str:
    max_y, max_x = stdscr.getmaxyx()
    prompt = f"{label}"
    if default:
        prompt += f" [{default}]"
    prompt += ": "
    curses.echo()
    try:
        stdscr.move(max_y - 1, 0)
        stdscr.clrtoeol()
        _safe_addstr(stdscr, max_y - 1, 0, prompt)
        raw = stdscr.getstr(max_y - 1, min(len(prompt), max_x - 2), max(1, max_x - len(prompt) - 2))
    finally:
        curses.noecho()
    value = raw.decode("utf-8", errors="ignore").strip()
    return value or default


def _prompt_int(stdscr: Any, curses: Any, label: str, default: int | None = None) -> int:
    raw_default = "" if default is None else str(default)
    value = _prompt(stdscr, curses, label, raw_default)
    return int(value)


def _list_dir(path: str, suffixes: tuple[str, ...]) -> list[Path]:
    root = Path(path).expanduser()
    if not root.exists() or not root.is_dir():
        root = Path.cwd()
    entries = []
    for child in root.iterdir():
        if child.name.startswith("."):
            continue
        if child.is_dir() or child.name.lower().endswith(suffixes):
            entries.append(child)
    return sorted(entries, key=lambda item: (not item.is_dir(), item.name.lower()))


def _pick_file(stdscr: Any, curses: Any, *, start_dir: str, suffixes: tuple[str, ...]) -> str | None:
    cwd = Path(start_dir or os.getcwd()).expanduser()
    if cwd.is_file():
        cwd = cwd.parent
    selected = 0
    top = 0
    while True:
        entries = [cwd.parent] + _list_dir(str(cwd), suffixes)
        stdscr.erase()
        _safe_addstr(stdscr, 0, 0, f"Select file ({', '.join(suffixes)}). Enter=open/select, q=cancel", curses.A_BOLD)
        _safe_addstr(stdscr, 1, 0, str(cwd))
        height, _ = stdscr.getmaxyx()
        limit = max(1, height - 3)
        if selected < top:
            top = selected
        if selected >= top + limit:
            top = selected - limit + 1
        visible = entries[top: top + limit]
        for offset, entry in enumerate(visible):
            row = offset + 2
            absolute_index = top + offset
            label = ".." if absolute_index == 0 else entry.name + ("/" if entry.is_dir() else "")
            attr = curses.A_REVERSE if absolute_index == selected else 0
            _safe_addstr(stdscr, row, 0, label, attr)
        key = stdscr.getch()
        if key in {ord("q"), 27}:
            return None
        if key == curses.KEY_UP:
            selected = max(0, selected - 1)
        elif key == curses.KEY_DOWN:
            selected = min(len(entries) - 1, selected + 1)
        elif key in {10, 13, curses.KEY_ENTER}:
            choice = entries[selected]
            if choice.is_dir():
                cwd = choice
                selected = 0
                top = 0
            else:
                return str(choice)


def _draw_text_panel(stdscr: Any, title: str, text: str, *, y: int, x: int, h: int, w: int, scroll: int, curses: Any) -> None:
    _safe_addstr(stdscr, y, x, _fit_line(title, w - 1), curses.A_BOLD)
    lines = _wrap_panel_lines(text, max(8, w - 1))
    for offset, line in enumerate(lines[scroll: scroll + max(0, h - 1)], start=1):
        _safe_addstr(stdscr, y + offset, x, line, 0)


def _draw(stdscr: Any, curses: Any, session: TuiSession, transcript_query: str, transcript_scroll: int, plan_scroll: int) -> None:
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    header_1 = "BiteBuilder TUI | T/TXT X/XML P/plan L/load N/first-pass A/assistant"
    header_2 = "+ add  - delete  M move  / search  O output  G goal  C context  Q quit"
    _safe_addstr(stdscr, 0, 0, _fit_line(header_1, width - 1), curses.A_REVERSE)
    _safe_addstr(stdscr, 1, 0, _fit_line(header_2, width - 1), curses.A_REVERSE)
    _safe_addstr(stdscr, 2, 0, _fit_line(f"TXT: {session.transcript_path or '-'}", width - 1))
    _safe_addstr(stdscr, 3, 0, _fit_line(f"XML: {session.xml_path or '-'}", width - 1))
    _safe_addstr(stdscr, 4, 0, _fit_line(f"Plan: {session.plan_path or '-'}", width - 1))
    _safe_addstr(stdscr, 5, 0, _fit_line(f"Out: {session.output_dir} | Model: {session.model}", width - 1))
    _safe_addstr(stdscr, 6, 0, _fit_line(f"Status: {session.message}", width - 1))
    panel_y = 8
    panel_h = max(4, height - panel_y - 1)
    transcript = session.transcript_text_for_view(query=transcript_query)
    summary = session.summary_text()
    if width < 120:
        transcript_h = max(4, panel_h // 2)
        plan_h = max(4, panel_h - transcript_h - 1)
        _draw_text_panel(
            stdscr,
            "Transcript (Up/Down scroll)",
            transcript,
            y=panel_y,
            x=0,
            h=transcript_h,
            w=width,
            scroll=transcript_scroll,
            curses=curses,
        )
        _draw_text_panel(
            stdscr,
            "Sequence Plan ([/] scroll)",
            summary,
            y=panel_y + transcript_h + 1,
            x=0,
            h=plan_h,
            w=width,
            scroll=plan_scroll,
            curses=curses,
        )
    else:
        left_w = max(48, width // 2)
        right_w = max(40, width - left_w - 1)
        _draw_text_panel(stdscr, "Transcript (Up/Down scroll)", transcript, y=panel_y, x=0, h=panel_h, w=left_w, scroll=transcript_scroll, curses=curses)
        _draw_text_panel(stdscr, "Sequence Plan ([/] scroll)", summary, y=panel_y, x=left_w + 1, h=panel_h, w=right_w, scroll=plan_scroll, curses=curses)
    stdscr.refresh()


def _run_curses(stdscr: Any, curses: Any, session: TuiSession) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)
    transcript_scroll = 0
    plan_scroll = 0
    transcript_query = ""
    while True:
        _draw(stdscr, curses, session, transcript_query, transcript_scroll, plan_scroll)
        key = stdscr.getch()
        try:
            if key in {ord("q"), ord("Q")}:
                return
            if key == curses.KEY_UP:
                transcript_scroll = max(0, transcript_scroll - 1)
            elif key == curses.KEY_DOWN:
                transcript_scroll += 1
            elif key == ord("["):
                plan_scroll = max(0, plan_scroll - 1)
            elif key == ord("]"):
                plan_scroll += 1
            elif key == ord("t"):
                session.transcript_path = _prompt(stdscr, curses, "Transcript path", session.transcript_path or "")
            elif key == ord("x"):
                session.xml_path = _prompt(stdscr, curses, "Premiere XML path", session.xml_path or "")
            elif key == ord("p"):
                session.plan_path = _prompt(stdscr, curses, "Sequence plan path", session.plan_path or "")
            elif key == ord("T"):
                picked = _pick_file(stdscr, curses, start_dir=session.transcript_path or os.getcwd(), suffixes=(".txt",))
                if picked:
                    session.transcript_path = picked
            elif key == ord("X"):
                picked = _pick_file(stdscr, curses, start_dir=session.xml_path or os.getcwd(), suffixes=(".xml",))
                if picked:
                    session.xml_path = picked
            elif key == ord("P"):
                picked = _pick_file(stdscr, curses, start_dir=session.plan_path or session.output_dir, suffixes=(".json",))
                if picked:
                    session.plan_path = picked
            elif key in {ord("o"), ord("O")}:
                session.output_dir = _prompt(stdscr, curses, "Output directory", session.output_dir)
            elif key in {ord("g"), ord("G")}:
                session.goal = _prompt(stdscr, curses, "Goal / creative brief", session.goal)
            elif key in {ord("c"), ord("C")}:
                session.project_context = _prompt(stdscr, curses, "Project context", session.project_context)
            elif key in {ord("l"), ord("L")}:
                session.load_media()
                if session.plan_path:
                    session.load_plan()
            elif key in {ord("n"), ord("N")}:
                session.run_first_pass()
            elif key in {ord("a"), ord("A")}:
                instruction = _prompt(stdscr, curses, "Assistant instruction", "make the narrative more cohesive")
                session.assistant_refine(instruction)
            elif key == ord("+"):
                segment_index = _prompt_int(stdscr, curses, "Transcript segment_index to add")
                position_raw = _prompt(stdscr, curses, "Insert at selected bite # (blank=end)", "")
                position = int(position_raw) if position_raw.strip() else None
                session.add_segment(segment_index, position)
            elif key in {ord("-"), ord("d"), ord("D")}:
                selected_position = _prompt_int(stdscr, curses, "Selected bite # to delete")
                session.delete_selected(selected_position)
            elif key in {ord("m"), ord("M")}:
                from_position = _prompt_int(stdscr, curses, "Move selected bite #")
                to_position = _prompt_int(stdscr, curses, "Move to selected #")
                session.move_selected(from_position, to_position)
            elif key == ord("/"):
                transcript_query = _prompt(stdscr, curses, "Search transcript", transcript_query)
                transcript_scroll = 0
        except Exception as exc:
            session.message = f"ERROR: {exc}"


def run_tui(args: Any, *, api: Any) -> TuiSession:
    """Run the interactive curses TUI and return the final session state."""
    import curses

    session = TuiSession.from_args(args, api=api)
    curses.wrapper(lambda stdscr: _run_curses(stdscr, curses, session))
    return session
