"""Store de `~/.thero/config.json`: o que o usuario parametrizou na interface.

Regras que ja custaram tempo nesta maquina: ler com `utf-8-sig` (Set-Content
do PowerShell escreve BOM e o `json.loads` estrito morre), escrever SEM BOM, e
nunca perder escolha do usuario ao evoluir o schema -- merge chave a chave
sobre os defaults, chave desconhecida preservada.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from thero import presets

CONFIG_VERSION = 1


def config_path() -> Path:
    """Path efetivo do config, resolvido NA CHAMADA: o conftest remapeia HOME
    depois do import, entao a constante congelada em thero.settings nao vale
    para teste nenhum."""
    root = os.environ.get("USERPROFILE") or os.environ.get("HOME")
    base = Path(root) if root else Path.home()
    return base / ".thero" / "config.json"


def default_config() -> dict:
    return {
        "version": CONFIG_VERSION,
        "providers": presets.default_providers(),
        "agents": presets.default_agents(),
        "routing": presets.default_routing(),
        "preferences": {"scope": "global"},
    }


def load(path: Optional[Path] = None) -> dict:
    target = path or config_path()
    cfg = default_config()
    if not target.exists():
        return cfg
    try:
        stored = json.loads(target.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError):
        return cfg
    if not isinstance(stored, dict):
        return cfg
    for key, value in stored.items():
        cfg[key] = value
    cfg["version"] = CONFIG_VERSION
    return cfg


def save(cfg: dict, path: Optional[Path] = None) -> Path:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(cfg)
    payload["version"] = CONFIG_VERSION
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def is_first_run(path: Optional[Path] = None) -> bool:
    return not (path or config_path()).exists()
