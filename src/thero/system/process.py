from __future__ import annotations

import datetime
import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterator


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def timestamp() -> str:
    return datetime.datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )


WINDOWS_LAUNCHERS = {
    "npx": "npx.cmd",
    "npm": "npm.cmd",
    "node": "node.exe",
    "claude": "claude.cmd",
}


def _with_windows_launcher(command: list[str]) -> list[str]:
    """npm/Claude instalam .cmd no PATH; sem o executavel certo o
    CreateProcess falha no Windows e nao existe subprocess que sobreviva a
    isso. Fora do Windows (ou com argv vazio) a lista passa intacta."""
    if os.name != "nt" or not command:
        return list(command)
    return [WINDOWS_LAUNCHERS.get(command[0], command[0]), *command[1:]]


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

    command = _with_windows_launcher(command)

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


def stream_command(
    command: list[str],
    *,
    cwd: Path | None = None,
) -> Iterator[tuple]:
    """
    Roda `command` e produz ('out', linha) durante a execucao e ('exit',
    codigo) no fim.

    stderr vai para o mesmo fluxo (npm e ollama escrevem progresso la).
    `encoding="utf-8"` explicito: no Windows o padrao e a codepage do
    console, que corrompe acento. Nunca levanta: quem chama e a ponte da
    Task 8, e excecao para fora viraria traceback no canal JSON.
    """
    if not command:
        yield ("out", "comando vazio")
        yield ("exit", 2)
        return

    argv = _with_windows_launcher(command)

    try:
        popen = subprocess.Popen(
            argv,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            shell=False,
        )
    except OSError as exc:
        yield ("out", "nao consegui rodar %s: %s" % (argv[0], exc))
        yield ("exit", 127)
        return

    with popen:
        for line in popen:
            line = line.rstrip("\r\n")
            if line:
                yield ("out", line)
        yield ("exit", popen.wait())
