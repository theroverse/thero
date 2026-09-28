from __future__ import annotations

from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"

GLOBAL_CLAUDE_MD = CLAUDE_DIR / "CLAUDE.md"

BACKUP_PREFIX = "CLAUDE.md.backup"

AUDIT_FILENAME = "CLAUDE_AUDIT.md"

SKILLS_FAILED_FILENAME = "SKILLS_INSTALL_FAILED.md"

DEFAULT_COMMAND_NAME = "thero"

# Mantido como "setup_claude" por compatibilidade: perfis do
# PowerShell que ja tinham o comando instalado (antes do projeto se
# chamar "thero") sao migrados automaticamente ao reconhecer este
# marcador, em vez de duplicar o bloco.
COMMAND_MARKER_START = "# >>> setup_claude global command >>>"

COMMAND_MARKER_END = "# <<< setup_claude global command <<<"

# --- config store da interface (estreando junto com a GUI) --------------
# Path.home() e resolvido no import: por isso toda funcao que le/escreve
# aceita `path=`/`base=` explicito -- os testes injetam tmp_path, ja que o
# conftest faz monkeypatch do HOME DEPOIS do import.
THERO_DIR = Path.home() / ".thero"

# Skills vivem no territorio do Claude Code (mesma base do instalador);
# a quarentena das removidas fica na pasta do Thero.
SKILLS_BASE_GLOBAL = CLAUDE_DIR / "skills"

SKILLS_QUARANTINE_DIRNAME = "skills"

# Bloco de ambiente no $PROFILE: e como ATHENA_OLLAMA_HOST/MODEL (athena/src/
# athena/settings.py) e SENTINEL_OLLAMA_HOST/MODEL (sentinel/src/sentinel/
# settings.py:205-243) chegam de fato a qualquer processo lancado do terminal.
# Marcadores proprios, diferentes dos do
# comando global, para um upsert nao comer o outro.
ENV_MARKER_START = "# >>> thero env >>>"

ENV_MARKER_END = "# <<< thero env <<<"

# Unico host aceito pela sonda de modelos locais (mesma regra do Sentinel).
OLLAMA_DEFAULT_HOST = "http://127.0.0.1:11434"

OLLAMA_PROBE_TIMEOUT = 3
