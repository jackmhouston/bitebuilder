from __future__ import annotations

import queue
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from bitebuilder.models import GenerationRequest
from bitebuilder.pipeline import run_generation

BG = "#0b1020"
PANEL = "#121a2f"
TEXT = "#edf2ff"
MUTED = "#98a5c4"
ACCENT = "#55e0c6"
ACCENT_ALT = "#ffb454"
ENTRY_BG = "#0f1730"


class BiteBuilderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("BiteBuilder")
        self.geometry("1180x760")
        self.minsize(980, 640)
        self.configure(bg=BG)

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.is_running = False

        self.transcript_var = tk.StringVar()
        self.xml_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.title_var = tk.StringVar(value="BiteBuilder Selects")
        self.model_var = tk.StringVar(value="gemma3:12b")
        self.ollama_var = tk.StringVar(value="http://127.0.0.1:11434")
        self.dry_run_var = tk.BooleanVar(value=False)

        self._configure_style()
        self._build_layout()
        self.after(100, self._pump_events)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=TEXT)
        style.configure(
            "Panel.TFrame",
            background=PANEL,
            relief="flat",
        )
        style.configure("App.TLabel", background=PANEL, foreground=MUTED, font=("TkDefaultFont", 10))
        style.configure(
            "Title.TLabel",
            background=BG,
            foreground=TEXT,
            font=("TkDefaultFont", 18, "bold"),
        )
        style.configure(
            "Hero.TLabel",
            background=BG,
            foreground=ACCENT,
            font=("TkDefaultFont", 10, "bold"),
        )
        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground="#08111f",
            borderwidth=0,
            focuscolor=ACCENT,
            padding=(14, 10),
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#6fead2"), ("disabled", "#33415f")],
            foreground=[("disabled", "#92a0bf")],
        )
        style.configure(
            "Ghost.TButton",
            background=PANEL,
            foreground=TEXT,
            bordercolor="#233154",
            padding=(12, 9),
        )
        style.map("Ghost.TButton", background=[("active", "#17223d")])
        style.configure(
            "App.TCheckbutton",
            background=PANEL,
            foreground=TEXT,
        )

    def _build_layout(self) -> None:
        outer = ttk.Frame(self, style="Panel.TFrame", padding=18)
        outer.pack(fill="both", expand=True, padx=18, pady=18)

        header = tk.Frame(outer, bg=BG)
        header.pack(fill="x", pady=(0, 16))
        ttk.Label(header, text="Local-first bite selects for Premiere", style="Hero.TLabel").pack(anchor="w")
        ttk.Label(header, text="BiteBuilder", style="Title.TLabel").pack(anchor="w", pady=(4, 4))

        summary = tk.Label(
            header,
            text="Transcript + Premiere XML + brief in. Sequence XML out. The GUI stays thin and uses the same pipeline as the CLI.",
            bg=BG,
            fg=MUTED,
            justify="left",
            wraplength=980,
        )
        summary.pack(anchor="w")

        body = tk.Frame(outer, bg=BG)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        form_panel = tk.Frame(body, bg=PANEL, highlightbackground="#233154", highlightthickness=1)
        form_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        log_panel = tk.Frame(body, bg=PANEL, highlightbackground="#233154", highlightthickness=1)
        log_panel.grid(row=0, column=1, sticky="nsew")

        self._build_form(form_panel)
        self._build_log_panel(log_panel)

    def _build_form(self, parent: tk.Frame) -> None:
        container = tk.Frame(parent, bg=PANEL)
        container.pack(fill="both", expand=True, padx=18, pady=18)
        container.grid_columnconfigure(1, weight=1)

        row = 0
        row = self._path_field(container, row, "Transcript .txt", self.transcript_var, self._pick_transcript)
        row = self._path_field(container, row, "Premiere XML", self.xml_var, self._pick_xml)
        row = self._path_field(container, row, "Output XML", self.output_var, self._pick_output)

        row = self._entry_field(container, row, "Sequence Title", self.title_var)
        row = self._entry_field(container, row, "Ollama Model", self.model_var)
        row = self._entry_field(container, row, "Ollama URL", self.ollama_var)

        ttk.Label(container, text="Creative Brief", style="App.TLabel").grid(
            row=row, column=0, sticky="nw", pady=(14, 6)
        )
        self.brief_text = tk.Text(
            container,
            height=12,
            bg=ENTRY_BG,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground="#24345a",
            wrap="word",
            padx=10,
            pady=10,
        )
        self.brief_text.grid(row=row, column=1, sticky="nsew", padx=(12, 12), pady=(14, 6))
        row += 1

        controls = tk.Frame(container, bg=PANEL)
        controls.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        controls.grid_columnconfigure(0, weight=1)

        ttk.Checkbutton(
            controls,
            text="Dry run only",
            variable=self.dry_run_var,
            style="App.TCheckbutton",
        ).grid(row=0, column=0, sticky="w")

        action_row = tk.Frame(controls, bg=PANEL)
        action_row.grid(row=0, column=1, sticky="e")
        ttk.Button(action_row, text="Prefill Output", style="Ghost.TButton", command=self._prefill_output).pack(
            side="left", padx=(0, 10)
        )
        self.generate_button = ttk.Button(
            action_row,
            text="Generate XML",
            style="Accent.TButton",
            command=self._start_generation,
        )
        self.generate_button.pack(side="left")

    def _build_log_panel(self, parent: tk.Frame) -> None:
        container = tk.Frame(parent, bg=PANEL)
        container.pack(fill="both", expand=True, padx=18, pady=18)

        tk.Label(
            container,
            text="Run Log",
            bg=PANEL,
            fg=TEXT,
            font=("TkDefaultFont", 14, "bold"),
        ).pack(anchor="w")
        tk.Label(
            container,
            text="Keep this open while you iterate on prompts, matching logic, and XML output.",
            bg=PANEL,
            fg=MUTED,
            wraplength=360,
            justify="left",
        ).pack(anchor="w", pady=(6, 14))

        self.log_text = ScrolledText(
            container,
            bg="#08111f",
            fg="#b8ffef",
            insertbackground=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground="#24345a",
            wrap="word",
            font=("TkFixedFont", 10),
        )
        self.log_text.pack(fill="both", expand=True)
        self.log_text.insert("end", "Ready.\n")
        self.log_text.configure(state="disabled")

    def _path_field(
        self,
        parent: tk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        command,
    ) -> int:
        ttk.Label(parent, text=label, style="App.TLabel").grid(row=row, column=0, sticky="w", pady=(10, 6))
        entry = tk.Entry(
            parent,
            textvariable=variable,
            bg=ENTRY_BG,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground="#24345a",
        )
        entry.grid(row=row, column=1, sticky="ew", padx=(12, 12), pady=(10, 6))
        ttk.Button(parent, text="Browse", style="Ghost.TButton", command=command).grid(
            row=row,
            column=2,
            sticky="e",
            pady=(10, 6),
        )
        return row + 1

    def _entry_field(self, parent: tk.Frame, row: int, label: str, variable: tk.StringVar) -> int:
        ttk.Label(parent, text=label, style="App.TLabel").grid(row=row, column=0, sticky="w", pady=(10, 6))
        entry = tk.Entry(
            parent,
            textvariable=variable,
            bg=ENTRY_BG,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground="#24345a",
        )
        entry.grid(row=row, column=1, columnspan=2, sticky="ew", padx=(12, 0), pady=(10, 6))
        return row + 1

    def _pick_transcript(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if path:
            self.transcript_var.set(path)
            self._prefill_output()

    def _pick_xml(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("XML files", "*.xml"), ("All files", "*.*")])
        if path:
            self.xml_var.set(path)

    def _pick_output(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".xml",
            filetypes=[("XML files", "*.xml"), ("All files", "*.*")],
        )
        if path:
            self.output_var.set(path)

    def _prefill_output(self) -> None:
        transcript = self.transcript_var.get().strip()
        if not transcript:
            return
        transcript_path = Path(transcript)
        suggested = transcript_path.with_name(f"{transcript_path.stem}_bitebuilder.xml")
        self.output_var.set(str(suggested))

    def _start_generation(self) -> None:
        if self.is_running:
            return
        try:
            request = self._build_request()
        except ValueError as exc:
            messagebox.showerror("Missing input", str(exc))
            return

        self.is_running = True
        self.generate_button.configure(state="disabled")
        self._append_log("Starting generation...\n", color=ACCENT_ALT)

        worker = threading.Thread(target=self._run_worker, args=(request,), daemon=True)
        worker.start()

    def _build_request(self) -> GenerationRequest:
        transcript_path = self.transcript_var.get().strip()
        xml_path = self.xml_var.get().strip()
        output_path = self.output_var.get().strip()
        brief = self.brief_text.get("1.0", "end").strip()

        if not transcript_path:
            raise ValueError("Choose a transcript .txt file.")
        if not xml_path:
            raise ValueError("Choose a Premiere XML export.")
        if not output_path:
            raise ValueError("Choose an output file location.")
        if not brief:
            raise ValueError("Write a creative brief.")

        return GenerationRequest(
            transcript_path=Path(transcript_path).expanduser().resolve(),
            premiere_xml_path=Path(xml_path).expanduser().resolve(),
            output_path=Path(output_path).expanduser().resolve(),
            brief=brief,
            sequence_title=self.title_var.get().strip() or "BiteBuilder Selects",
            model=self.model_var.get().strip() or "gemma3:12b",
            ollama_url=self.ollama_var.get().strip() or "http://127.0.0.1:11434",
            dry_run=self.dry_run_var.get(),
        )

    def _run_worker(self, request: GenerationRequest) -> None:
        try:
            result = run_generation(request, logger=lambda message: self.events.put(("log", message)))
            self.events.put(("done", result))
        except Exception as exc:  # pragma: no cover - GUI safety net
            details = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            self.events.put(("error", details))

    def _pump_events(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break

            if kind == "log":
                self._append_log(f"{payload}\n")
            elif kind == "done":
                self.is_running = False
                self.generate_button.configure(state="normal")
                result = payload
                self._append_log(
                    f"Completed {result.selected_count} selections into {result.output_path}\n",
                    color=ACCENT_ALT,
                )
                if result.warnings:
                    for warning in result.warnings:
                        self._append_log(f"Warning: {warning}\n", color="#ffd38a")
                messagebox.showinfo("Done", f"Wrote {result.output_path}")
            elif kind == "error":
                self.is_running = False
                self.generate_button.configure(state="normal")
                self._append_log(f"Error: {payload}\n", color="#ff8f8f")
                messagebox.showerror("Generation failed", str(payload))

        self.after(100, self._pump_events)

    def _append_log(self, text: str, color: str | None = None) -> None:
        self.log_text.configure(state="normal")
        if color:
            tag = f"color_{color}"
            if tag not in self.log_text.tag_names():
                self.log_text.tag_configure(tag, foreground=color)
            self.log_text.insert("end", text, tag)
        else:
            self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")


def main() -> None:
    app = BiteBuilderApp()
    app.mainloop()


if __name__ == "__main__":
    main()

