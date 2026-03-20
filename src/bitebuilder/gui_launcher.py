from __future__ import annotations

from bitebuilder.gui_support import tkinter_unavailable_message


def main() -> None:
    try:
        from bitebuilder.gui import main as gui_main
    except ModuleNotFoundError as exc:
        if exc.name == "_tkinter":
            raise SystemExit(tkinter_unavailable_message()) from exc
        raise

    gui_main()
