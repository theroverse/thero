from __future__ import annotations

import datetime
import os
import shutil
import subprocess
from pathlib import Path


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def timestamp() -> str:
    return datetime.datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )


def run_command(
command: list[str],
*,
cwd: Path | None = None,
check: bool = False,
capture: bool = True,
text: bool = True,
input_text: str | None = None,
timeout: float | None = None,
) -> subprocess.CompletedProcess:
    """
    Execute a command reliably on Windows and Unix-like systems.

    Windows installs npm/Claude CLI launchers as .cmd files.
    Explicitly use the Windows launcher when necessary.
    """
    if not command:
        raise ValueError("Command cannot be empty.")

    executable = command[0]

    if os.name == "nt":
        windows_launchers = {
            "npx": "npx.cmd",
            "npm": "npm.cmd",
            "node": "node.exe",
            "claude": "claude.cmd",
        }

        executable = windows_launchers.get(executable, executable)
        command = [executable, *command[1:]]

    # Sem "encoding" explícito, o Windows decodifica stdout/stderr
    # usando a codepage do console (ex.: cp1252), corrompendo
    # acentos que o Claude retorna em UTF-8.
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        check=check,
        capture_output=capture,
        text=text,
        encoding="utf-8" if text else None,
        input=input_text,
        shell=False,
        timeout=timeout,
    )
