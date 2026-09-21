from __future__ import annotations

"""
Servidor MCP sobre stdio, em stdlib pura (json + sys + subprocess).

O protocolo MCP é JSON-RPC 2.0 com uma mensagem por linha (newline-
delimited). Este loop trata os métodos que um cliente MCP precisa para
descobrir e chamar as ferramentas do Theroverse:

- ``initialize``  → anuncia tools-capabilities + informações do servidor
- ``tools/list``  → devolve o catálogo vindo de ``capabilities``
- ``tools/call``  → despacha para o CLI da ferramenta (athena.py /
  zeus.py / thero.py), capturando stdout/stderr como texto da tool

``serve()`` lê de ``sys.stdin`` e escreve em ``sys.stdout``. Toda a
lógica de uma requisição está isolada em ``handle_request`` (função pura
de dict→dict), o que permite testar initialize/tools/list/tools/call sem
subir pipes reais. O subprocesso de ferramenta é injetável via
``runner`` para os mesmos testes não tocarem rede nem discos alheios.
"""

import json
import sys
from pathlib import Path
from typing import Any, Callable

from thero.mcp import capabilities
from thero.system.process import run_command

# Versão do protocolo que suportamos (amplo aceite nos clientes MCP).
PROTOCOL_VERSION = "2024-11-05"

SERVER_INFO = {
    "name": "theroverse",
    "title": "Theroverse — Athena · Zeus · Thero",
    "version": "1.0.0",
}

# assinatura do runner: (script: Path, argv: list[str], cwd: Path) -> CompletedProcess
Runner = Callable[[Path, list[str], Path], Any]


class ToolError(Exception):
    """Erro de despacho reportado como resultado is_error=True (não raise)."""


def _resolve_script(kind: str, entry_path: Path) -> Path | None:
    """Localiza o script da ferramenta via bridges (com clone gerenciado)."""

    if kind == capabilities.ATHENA:
        from thero.integrations.athena_bridge import find_athena_script

        return find_athena_script(entry_path)

    if kind == capabilities.ZEUS:
        from thero.integrations.zeus_bridge import find_zeus_script

        return find_zeus_script(entry_path)

    # THERO: o próprio entry point que está servindo o MCP.
    return entry_path


def _default_runner(script: Path, argv: list[str], cwd: Path) -> Any:
    return run_command(
        [sys.executable, str(script), *argv],
        cwd=cwd,
        capture=True,
        text=True,
    )


def dispatch_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    entry_path: Path,
    project_dir: Path,
    runner: Runner | None = None,
) -> tuple[str, bool]:
    """
    Executa uma ferramenta e devolve ``(texto, is_error)``.

    Nunca levanta para erros esperados (tool desconhecida, script
    ausente, CLI retornou !=0): o MCP quer isso como resultado com
    ``isError`` para o agente ler e reagir.
    """

    cap = capabilities.get_capability(name)

    if cap is None:
        return f"Ferramenta desconhecida: {name!r}", True

    runner = runner or _default_runner
    script = _resolve_script(cap.kind, entry_path)

    if script is None:
        return (
            f"Não foi possível localizar o script para '{name}' "
            f"(kind={cap.kind}). Rode 'thero --index' uma vez num "
            "terminal interativo para permitir o clone gerenciado, "
            "ou defina THERO_ATHENA_PATH/THERO_ZEUS_PATH.",
            True,
        )

    try:
        argv = cap.build_argv(arguments or {})
    except (KeyError, ValueError, TypeError) as exc:
        return f"Argumentos inválidos para '{name}': {exc}", True

    try:
        result = runner(script, argv, project_dir)
    except OSError as exc:  # ex.: executável ausente
        return f"Falha ao executar '{name}': {exc}", True

    stdout = (getattr(result, "stdout", "") or "").strip()
    stderr = (getattr(result, "stderr", "") or "").strip()
    returncode = getattr(result, "returncode", 0)

    if returncode == 0:
        return (stdout or "(concluído sem saída)"), False

    detail = stdout or stderr or "(sem saída)"
    return f"[exit {returncode}] {detail}", True


def _tool_content(text: str, is_error: bool) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def handle_request(
    request: dict[str, Any],
    *,
    entry_path: Path,
    project_dir: Path,
    runner: Runner | None = None,
) -> dict[str, Any] | None:
    """
    Processa UMA requisição JSON-RPC. Devolve o envelope de resposta, ou
    ``None`` para notificações (mensagens sem ``id`` → sem resposta).
    """

    method = request.get("method")
    req_id = request.get("id")
    params = request.get("params") or {}

    def result(payload: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "result": payload}

    def error(code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        }

    # Notificações (sem id): não exigem resposta.
    if req_id is None:
        return None

    if method == "initialize":
        return result(
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            }
        )

    if method == "ping":
        return result({})

    if method == "tools/list":
        return result(
            {"tools": [cap.as_mcp_tool() for cap in capabilities.all_capabilities()]}
        )

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        text, is_error = dispatch_tool(
            tool_name,
            arguments,
            entry_path=entry_path,
            project_dir=project_dir,
            runner=runner,
        )
        return result(_tool_content(text, is_error))

    return error(-32601, f"Método não suportado: {method!r}")


def _force_utf8(*streams: Any) -> None:
    """
    Garante que o canal JSON-RPC fale UTF-8, qualquer que seja a
    codepage local do processo.

    Escrevemos as respostas com ``ensure_ascii=False`` (título e
    descrições levam acentos/ travessões). Sem isto, num Windows em
    cp1252/cp850 o ``print`` codificaria esses caracteres em bytes que
    um cliente MCP (que decodifica UTF-8, como manda a spec) leria
    corrompidos. ``reconfigure`` existe no ``TextIOWrapper`` (3.7+); se
    o stream já estiver redirecionado (ex.: StringIO em testes), ignoramos.
    """

    for stream in streams:
        reconfigure = getattr(stream, "reconfigure", None)

        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def _write(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def serve(
    entry_path: Path,
    *,
    project_dir: Path | None = None,
    runner: Runner | None = None,
) -> None:
    """
    Loop stdio: lê JSON-RPC linha a linha de ``sys.stdin`` até EOF,
    respondendo cada requisição em ``sys.stdout``. Logs vão para stderr
    para não contaminar o canal JSON-RPC.
    """

    project_dir = project_dir or Path.cwd()

    # UTF-8 no canal JSON-RPC (stdout/stdin) e no log (stderr), para que
    # os acentos das descrições sobrevivam ao pipe em qualquer codepage.
    _force_utf8(sys.stdout, sys.stdin, sys.stderr)

    sys.stderr.write(
        f"[theroverse mcp] pronto em {project_dir} "
        f"({len(capabilities.all_capabilities())} tools)\n"
    )
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()

        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"JSON inválido: {exc}"},
                }
            )
            continue

        response = handle_request(
            request,
            entry_path=entry_path,
            project_dir=project_dir,
            runner=runner,
        )

        if response is not None:
            _write(response)
