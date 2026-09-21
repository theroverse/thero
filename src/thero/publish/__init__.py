"""Publicador first-party: gera skills/comandos do Theroverse por agente.

Motor da descoberta em texto (complemento ao servidor MCP): lê o registro
de capacidades e escreve SKILL.md (Claude Code / Qoder) e comandos
(OpenCode) nos diretórios nativos de cada agente.
"""

from thero.publish.installer import (
    base_dir_for,
    publish,
    resolve_agents,
    serve_command,
)

__all__ = ["base_dir_for", "publish", "resolve_agents", "serve_command"]
