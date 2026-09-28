"""Retrato do ambiente, em dados -- o texto cru do `validate_environment()`
do CLI nao serve para a interface.

Usado por: tela Status, checklist de pre-requisitos do onboarding e o
`host-ready` da ponte. `found` e "o executavel esta no PATH"; `ok` e "ele
responde" -- os dois sao diferentes nesta maquina (npx existe e quebra), e a
interface mostra essa diferenca em vez de um check verde mentiroso.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from thero import config as config_store
from thero.settings import DEFAULT_COMMAND_NAME
from thero.system.process import run_command

_TOOLS = ("node", "npx", "claude", "git")

# Segundos por sonda de versao. A ponte e um loop de stdio, entao uma sonda sem
# teto congela a janela inteira.
VERSION_TIMEOUT = 10


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def _first_line(command: list) -> str:
    """Primeira linha nao vazia de `<cmd> --version` ('' se silenciar ou travar)."""
    try:
        result = run_command(command + ["--version"], timeout=VERSION_TIMEOUT)
    except subprocess.TimeoutExpired:
        return ""
    out = (result.stdout or "") if result.returncode == 0 else (result.stderr or "")
    for line in out.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _ollama_probe() -> dict:
    # Import tardio: envreport e escrito antes de localmodels (Task 3) e os
    # testes desta tarefa trocam esta funcao, entao ela nunca roda aqui.
    from thero import localmodels

    info = localmodels.status()
    return {
        "up": bool(info["up"]),
        "host": info["base"],
        "models": info["models"],
        "error": info["error"],
    }


def _profile_path() -> Optional[Path]:
    if platform.system() != "Windows":
        return None
    from thero.shell_command.windows import resolve_powershell_profile

    try:
        return resolve_powershell_profile()
    except Exception:  # noqa: BLE001 - conforto, nunca motivo de falha na GUI
        return None


def _command_installed(profile: Optional[Path]) -> bool:
    if profile is None or not Path(profile).exists():
        return False
    try:
        text = Path(profile).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return DEFAULT_COMMAND_NAME in text


def _count_skills(skills_base: Path) -> int:
    if not skills_base.is_dir():
        return 0
    return sum(1 for folder in sorted(skills_base.iterdir())
               if folder.is_dir() and (folder / "SKILL.md").exists())


def snapshot(
    entry_path: Path,
    *,
    home: Optional[Path] = None,
    config_path: Optional[Path] = None,
    scope: str = "global",
) -> dict:
    home = Path(home) if home else Path.home()
    claude_dir = home / ".claude"
    skills_base = claude_dir / "skills"
    claude_md = claude_dir / "CLAUDE.md"
    cfg_path = Path(config_path) if config_path else config_store.config_path()

    tools: dict = {}
    for name in _TOOLS:
        found = bool(_which(name))
        detail = ""
        ok = False
        if found:
            try:
                line = _first_line([name])
            except Exception as exc:  # noqa: BLE001 - fronteira: nunca derrubar a GUI
                line = ""
                detail = str(exc)
            if line.lower().startswith("error"):
                detail = line
            elif line:
                ok = True
                detail = line
            else:
                detail = detail or "sem saida de --version"
        tools[name] = {"found": found, "ok": ok, "detail": detail}

    try:
        ollama = _ollama_probe()
    except Exception as exc:  # noqa: BLE001
        ollama = {"up": False, "host": "", "models": [], "error": str(exc)}

    exists = claude_md.exists()
    md_bytes = claude_md.stat().st_size if exists else 0
    backups = sorted(claude_dir.glob("CLAUDE.md.backup*")) if claude_dir.is_dir() else []
    profile = _profile_path()

    return {
        "app": "thero",
        "entry": str(entry_path),
        "scope": scope,
        "firstRun": not cfg_path.exists(),
        "configPath": str(cfg_path),
        "python": "%d.%d.%d" % sys.version_info[:3],
        "platform": platform.system(),
        "commandName": DEFAULT_COMMAND_NAME,
        "commandInstalled": _command_installed(profile),
        "profilePath": str(profile) if profile else "",
        "claudeDir": str(claude_dir),
        "claudeMd": {"exists": exists, "bytes": md_bytes, "backups": len(backups)},
        "skills": {"base": str(skills_base), "installed": _count_skills(skills_base)},
        "tools": tools,
        "ollama": {"up": bool(ollama.get("up")),
                   "host": ollama.get("host", ""),
                   "modelCount": len(ollama.get("models", [])),
                   "error": ollama.get("error", "")},
    }
