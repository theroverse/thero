"""Store de `~/.thero/config.json`: o que o usuario parametrizou na interface.

Regras que ja custaram tempo nesta maquina: ler com `utf-8-sig` (Set-Content
do PowerShell escreve BOM e o `json.loads` estrito morre), escrever SEM BOM e
escrever atomico (arquivo meio gravado + o fallback de corrompido viram
perda de escolha), e nao perder escolha do usuario ao evoluir o schema -- as
chaves de topo sao sobrepostas aos defaults, chave desconhecida preservada.
Campos novos DENTRO de uma entrada de `providers`/`agents` nao sao injetados:
quem consome essas listas le com `.get()` e default proprio.
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
        "limits": presets.default_limits(),
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
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    # Escrita atomica: `load()` devolve os defaults para arquivo corrompido,
    # entao uma gravacao interrompida no meio custaria as escolhas do usuario
    # na proxima abertura. os.replace() e atomico no Windows e no POSIX, 3.9+.
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(str(tmp), str(target))
    return target


def is_first_run(path: Optional[Path] = None) -> bool:
    return not (path or config_path()).exists()


# ---------------------------------------------------------------------------
# Caminho pontilhado do `--config` estilo git (Task 6b). So `limits` e
# escrevivel por linha de comando: `routing` e `preferences` sao lidos e
# gravados pelas telas, e `providers`/`agents` nem uma coisa nem outra por
# aqui -- sao listas de estruturas, e `providers` e onde mora qualquer nome
# de variavel de credencial (regra inegociavel 4 do plano).
# ---------------------------------------------------------------------------
WRITABLE_SECTIONS = ("limits",)
READABLE_SECTIONS = ("limits", "routing", "preferences")


def get_dotted(cfg: dict, path: str):
    """(encontrado, valor) para 'limits.local'. Nenhum dict/lista: folha
    escalar ou nada, porque `--get` promete uma linha imprimivel."""
    parts = path.split(".")
    if len(parts) != 2:
        return False, None
    node = cfg.get(parts[0])
    if not isinstance(node, dict) or parts[1] not in node:
        return False, None
    value = node[parts[1]]
    if isinstance(value, (dict, list)):
        return False, None
    return True, value


def set_dotted(cfg: dict, path: str, raw: str):
    """Aplica `limits.<tipo>=<int>` no dict em memoria e devolve o erro humano
    (ou None). NAO grava: quem chama decide quando persistir, para o
    read-modify-write ser uma operacao so."""
    parts = path.split(".")
    if len(parts) != 2 or parts[0] not in WRITABLE_SECTIONS:
        return ("%s nao se ajusta por linha de comando: use a interface "
                "(ou --config limits.local=4)" % path)
    section, key = parts
    if section == "limits":
        if key not in presets.LIMITS:
            return "tipo de modelo desconhecido: %s (validos: %s)" % (
                key, ", ".join(presets.LIMITS))
        # isdecimal e nao isdigit: isdigit() aceita sobrescrito (U+00B2) e
        # int("2") ali estouraria ValueError para fora da CLI.
        if not raw.lstrip("-").isdecimal():
            return "limits.%s so aceita numero inteiro" % key
        value = int(raw)
        if value < 1 or value > 64:
            return "limits.%s fica entre 1 e 64 (recebi %d)" % (key, value)
        node = dict(cfg.get(section) or {})
        node[key] = value
        cfg[section] = node
        return None
    return "escrita nao implementada para %s" % path


def iter_scalars(cfg: dict):
    """`chave=valor` ordenado, uma linha por folha escalar das seicoes que o
    terminal entende. E o render do `--config --list`; listas ficam de fora
    por decisao, nao por esquecimento (ver WRITABLE_SECTIONS acima)."""
    rows = []
    for section in READABLE_SECTIONS:
        node = cfg.get(section)
        if not isinstance(node, dict):
            continue
        for key, value in node.items():
            if isinstance(value, (dict, list)):
                continue
            rows.append("%s.%s=%s" % (section, key, value))
    return sorted(rows)
