from __future__ import annotations

"""
Registro único de capacidades do Theroverse expostas a agentes de IA.

Cada capacidade descreve uma ferramenta (Athena, Zeus ou o próprio
Thero) com: nome estável, descrição, *input schema* JSON (formato MCP)
e um construtor de ``argv`` que monta a chamada ao CLI correspondente.

Este módulo é a **fonte única de verdade**: tanto o servidor MCP
(``thero.mcp.server``) quanto o publicador de skills por agente
(``thero.publish``) leem daqui. Adicionar uma ferramenta = escrever uma
``Capability`` aqui; ela passa a aparecer no MCP e nos arquivos de skill
de Claude Code / OpenCode / Qoder sem duplicar contrato em quatro lugares.

Puro dado + montagem de argv: nenhuma chamada de rede aqui (os testes
verificam os ``argv`` montados, não execução real).
"""

import dataclasses
from typing import Any, Callable

# kind decide QUAL script o dispatcher invoca:
#   "athena" -> athena.py (resolvido pela athena_bridge)
#   "zeus"   -> zeus.py   (resolvido pela zeus_bridge)
#   "thero"  -> thero.py  (o próprio entry point)
ATHENA = "athena"
ZEUS = "zeus"
THERO = "thero"

# Argumento opcional presente em quase toda ferramenta: a pasta do
# projeto-alvo. Quando omitido, o subprocesso roda no cwd do servidor,
# que é o projeto atual do agente — então "./" já resolve certo.
_PATH_PROP = {
    "type": "string",
    "description": (
        "Pasta do projeto-alvo. Omita para usar o diretório atual de "
        "trabalho do agente."
    ),
}


@dataclasses.dataclass(frozen=True)
class Capability:
    name: str
    title: str
    description: str
    kind: str
    input_schema: dict[str, Any]
    # build_argv(arguments) -> lista de argv do CLI da ferramenta, SEM o
    # caminho do script (o dispatcher prepõe python + script).
    build_argv: Callable[[dict[str, Any]], list[str]]

    def as_mcp_tool(self) -> dict[str, Any]:
        """Formato de item em ``tools/list`` do protocolo MCP."""

        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


def _target_path(arguments: dict[str, Any]) -> str | None:
    return arguments.get("path")


def _argv_index(arguments: dict[str, Any]) -> list[str]:
    argv = ["index"]
    path = _target_path(arguments)
    if path:
        argv.append(path)
    if arguments.get("backend"):
        argv += ["--backend", str(arguments["backend"])]
    if arguments.get("model"):
        argv += ["--model", str(arguments["model"])]
    if arguments.get("max_files"):
        argv += ["--max-files", str(int(arguments["max_files"]))]
    if arguments.get("dry_run"):
        argv.append("--dry-run")
    if arguments.get("force"):
        argv.append("--force")
    return argv


def _argv_recall(arguments: dict[str, Any]) -> list[str]:
    argv = ["recall", str(arguments["query"])]
    path = _target_path(arguments)
    if path:
        argv.append(path)
    if arguments.get("k"):
        argv += ["--k", str(int(arguments["k"]))]
    return argv


def _argv_remember(arguments: dict[str, Any]) -> list[str]:
    argv = ["remember", str(arguments["kind"]), str(arguments["file"])]
    path = _target_path(arguments)
    if path:
        argv.append(path)
    return argv


def _argv_plan(arguments: dict[str, Any]) -> list[str]:
    argv = ["plan", str(arguments["task"])]
    path = _target_path(arguments)
    if path:
        argv.append(path)
    if arguments.get("context"):
        argv += ["--context", str(arguments["context"])]
    return argv


def _argv_audit(arguments: dict[str, Any]) -> list[str]:
    # Roda o fluxo de auditoria do próprio Thero (somente leitura no
    # projeto atual). Escreve CLAUDE_AUDIT.md na pasta de trabalho.
    return ["--audit-only"]


_CAPABILITIES: list[Capability] = [
    Capability(
        name="athena_index",
        title="Athena: indexar arquitetura",
        description=(
            "Gera/atualiza o índice de resumos recursivos do projeto "
            "(Athena). Re-resume só o que mudou via cache. Use para dar "
            "a uma IA uma visão do codebase sem reabrir arquivo por "
            "arquivo."
        ),
        kind=ATHENA,
        input_schema={
            "type": "object",
            "properties": {
                "path": _PATH_PROP,
                "backend": {
                    "type": "string",
                    "enum": ["auto", "local", "claude"],
                    "description": (
                        "'local' = Ollama offline; 'claude' = CLI "
                        "claude -p; 'auto' (padrão) decide por "
                        "disponibilidade."
                    ),
                },
                "model": {
                    "type": "string",
                    "description": "Modelo de resumo (alias Claude ou nome Ollama).",
                },
                "max_files": {
                    "type": "integer",
                    "description": "Elevar a trava de segurança de arquivos.",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Mostrar o que seria processado sem gastar chamadas.",
                },
                "force": {
                    "type": "boolean",
                    "description": "Ignorar cache e re-resumir tudo.",
                },
            },
        },
        build_argv=_argv_index,
    ),
    Capability(
        name="athena_recall",
        title="Athena: rechamar da memória",
        description=(
            "Busca por similaridade na memória local da Athena "
            "(.thero/memory): convenções, histórico e decisões "
            "arquiteturais já registradas. Cosseno quando Ollama está "
            "de pé, senão TF-IDF — sempre offline e determinístico."
        ),
        kind=ATHENA,
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Consulta a rechamar."},
                "path": _PATH_PROP,
                "k": {
                    "type": "integer",
                    "description": "Quantos resultados devolver (padrão 5).",
                },
            },
            "required": ["query"],
        },
        build_argv=_argv_recall,
    ),
    Capability(
        name="athena_remember",
        title="Athena: registrar na memória",
        description=(
            "Guarda o conteúdo de um arquivo na memória local da Athena "
            "como 'convention', 'history', 'decision' ou 'note' "
            "(dedupe por hash do conteúdo). Use para fixar decisões/"
            "convenções que devem ser relembradas depois."
        ),
        kind=ATHENA,
        input_schema={
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["convention", "history", "decision", "note"],
                    "description": "Tipo do registro de memória.",
                },
                "file": {
                    "type": "string",
                    "description": "Arquivo cujo conteúdo será guardado.",
                },
                "path": _PATH_PROP,
            },
            "required": ["kind", "file"],
        },
        build_argv=_argv_remember,
    ),
    Capability(
        name="zeus_plan",
        title="Zeus: planejar tarefa",
        description=(
            "Cruza uma tarefa descrita com o índice da Athena do "
            "projeto e produz um plano candidato (arquivos a ler/editar, "
            "ordem de execução), gravado em .claude/zeus-plan.md."
        ),
        kind=ZEUS,
        input_schema={
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Descrição da tarefa a planejar.",
                },
                "path": _PATH_PROP,
                "context": {
                    "type": "string",
                    "description": (
                        "Pasta a indexar para o contexto do plano (ex.: "
                        "raiz do monorepo), escrevendo o plano na pasta atual."
                    ),
                },
            },
            "required": ["task"],
        },
        build_argv=_argv_plan,
    ),
    Capability(
        name="thero_audit",
        title="Thero: auditar projeto",
        description=(
            "Audita o projeto atual (somente leitura) contra o sistema "
            "de engenharia configurado, escrevendo CLAUDE_AUDIT.md com "
            "achados classificados (CRITICAL/BUG/RISK/...). Exige o "
            "Claude Code autenticado."
        ),
        kind=THERO,
        input_schema={"type": "object", "properties": {}},
        build_argv=_argv_audit,
    ),
]

_BY_NAME = {cap.name: cap for cap in _CAPABILITIES}


def all_capabilities() -> list[Capability]:
    return list(_CAPABILITIES)


def get_capability(name: str) -> Capability | None:
    return _BY_NAME.get(name)
