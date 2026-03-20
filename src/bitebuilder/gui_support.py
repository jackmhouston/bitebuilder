from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def tkinter_unavailable_message() -> str:
    lines = [
        f"Tkinter is not available in this Python build: {sys.executable}",
    ]
    suggested_python = _find_tk_enabled_python()
    if suggested_python is None:
        lines.append("Install Python with Tk support or use the CLI.")
        return "\n".join(lines)

    lines.extend(
        [
            "",
            "Use a Tk-enabled interpreter to recreate the virtualenv, for example:",
            "  deactivate",
            "  rm -rf .venv",
            f"  {suggested_python} -m venv .venv",
            "  source .venv/bin/activate",
            "  pip install -e .",
            "  bitebuilder-gui",
        ]
    )
    return "\n".join(lines)


def _find_tk_enabled_python() -> str | None:
    current = Path(sys.executable).resolve()
    candidates = [
        "/usr/bin/python3.12",
        "/usr/bin/python3",
        "python3.12",
        "python3",
    ]
    for candidate in candidates:
        resolved = _resolve_python(candidate)
        if resolved is None:
            continue
        if Path(resolved).resolve() == current:
            continue
        if _has_tkinter(resolved):
            return resolved
    return None


def _resolve_python(candidate: str) -> str | None:
    if candidate.startswith("/"):
        return candidate if Path(candidate).exists() else None
    return shutil.which(candidate)


def _has_tkinter(python_executable: str) -> bool:
    try:
        subprocess.run(
            [python_executable, "-c", "import tkinter"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    return True
