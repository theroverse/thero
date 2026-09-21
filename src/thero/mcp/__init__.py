"""Servidor MCP (Model Context Protocol) do Theroverse.

Expõe Athena, Zeus e Thero como *tools* faladas por qualquer agente que
implemente MCP (Claude Code, OpenCode, Qoder, Cursor...). Um único
registro por agente basta para o agente chamar as três ferramentas.

- ``capabilities``: fonte única de verdade das ferramentas.
- ``server``: loop JSON-RPC 2.0 sobre stdio (newline-delimited), stdlib only.
"""

from thero.mcp.capabilities import (
    ATHENA,
    Capability,
    THERO,
    ZEUS,
    all_capabilities,
    get_capability,
)

__all__ = [
    "ATHENA",
    "Capability",
    "THERO",
    "ZEUS",
    "all_capabilities",
    "get_capability",
]
