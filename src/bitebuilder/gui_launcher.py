from __future__ import annotations


def main() -> None:
    try:
        from bitebuilder.gui import main as gui_main
    except ModuleNotFoundError as exc:
        if exc.name == "_tkinter":
            raise SystemExit(
                "Tkinter is not available in this Python build. Install Python with Tk support or use the CLI."
            ) from exc
        raise

    gui_main()
