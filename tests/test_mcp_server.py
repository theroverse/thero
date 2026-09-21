from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from thero.mcp import server

ENTRY = Path("/repo/thero/thero.py")
PROJ = Path("/work/proj")
# thero.py real (raiz do repo), para o teste de subprocess ponta-a-ponta.
THERO_ENTRY = Path(__file__).resolve().parents[1] / "thero.py"


def _fake_result(returncode=0, stdout="", stderr=""):
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


# -- initialize / ping / tools/list -----------------------------------------


def test_initialize_returns_protocol_and_server_info():
    resp = server.handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        entry_path=ENTRY,
        project_dir=PROJ,
    )

    assert resp["id"] == 1
    assert resp["result"]["protocolVersion"] == server.PROTOCOL_VERSION
    assert resp["result"]["capabilities"] == {"tools": {}}
    assert resp["result"]["serverInfo"]["name"] == "theroverse"


def test_notification_without_id_gets_no_response():
    resp = server.handle_request(
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        entry_path=ENTRY,
        project_dir=PROJ,
    )

    assert resp is None


def test_tools_list_returns_all_capabilities():
    resp = server.handle_request(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        entry_path=ENTRY,
        project_dir=PROJ,
    )
    names = {t["name"] for t in resp["result"]["tools"]}

    assert "athena_recall" in names
    assert "zeus_plan" in names
    assert "thero_audit" in names


def test_unknown_method_returns_jsonrpc_error():
    resp = server.handle_request(
        {"jsonrpc": "2.0", "id": 3, "method": "metodo/bogus"},
        entry_path=ENTRY,
        project_dir=PROJ,
    )

    assert resp["error"]["code"] == -32601


# -- tools/call dispatch -----------------------------------------------------


def test_tools_call_success_returns_stdout():
    def runner(script, argv, cwd):
        return _fake_result(returncode=0, stdout="achou 3 mem\u00f3rias")

    with patch(
        "thero.integrations.athena_bridge.find_athena_script",
        return_value=Path("/repo/athena/athena.py"),
    ):
        resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "athena_recall", "arguments": {"query": "x"}},
            },
            entry_path=ENTRY,
            project_dir=PROJ,
            runner=runner,
        )

    result = resp["result"]
    assert result["isError"] is False
    assert result["content"][0]["text"] == "achou 3 mem\u00f3rias"


def test_tools_call_propagates_nonzero_exit_as_error():
    def runner(script, argv, cwd):
        return _fake_result(returncode=2, stdout="", stderr="boom")

    with patch(
        "thero.integrations.athena_bridge.find_athena_script",
        return_value=Path("/repo/athena/athena.py"),
    ):
        text, is_error = server.dispatch_tool(
            "athena_index",
            {},
            entry_path=ENTRY,
            project_dir=PROJ,
            runner=runner,
        )

    assert is_error is True
    assert "exit 2" in text and "boom" in text


def test_tools_call_unknown_tool_is_error():
    text, is_error = server.dispatch_tool(
        "nao_existe",
        {},
        entry_path=ENTRY,
        project_dir=PROJ,
        runner=lambda *a: _fake_result(),
    )

    assert is_error is True
    assert "desconhecida" in text


def test_dispatch_uses_injected_runner_for_athena_kind():
    seen = {}

    def runner(script, argv, cwd):
        seen["script"] = script
        seen["argv"] = argv
        seen["cwd"] = cwd
        return _fake_result(stdout="ok")

    with patch(
        "thero.integrations.athena_bridge.find_athena_script",
        return_value=Path("/repo/athena/athena.py"),
    ):
        text, is_error = server.dispatch_tool(
            "athena_remember",
            {"kind": "note", "file": "f.md"},
            entry_path=ENTRY,
            project_dir=PROJ,
            runner=runner,
        )

    assert is_error is False
    assert seen["script"] == Path("/repo/athena/athena.py")
    assert seen["argv"] == ["remember", "note", "f.md"]
    assert seen["cwd"] == PROJ


def test_dispatch_thero_kind_uses_entry_path_as_script():
    captured = {}

    def runner(script, argv, cwd):
        captured["script"] = script
        return _fake_result(stdout="relatorio")

    text, is_error = server.dispatch_tool(
        "thero_audit",
        {},
        entry_path=ENTRY,
        project_dir=PROJ,
        runner=runner,
    )

    assert is_error is False
    assert captured["script"] == ENTRY


def test_dispatch_missing_script_returns_clean_error():
    with patch(
        "thero.integrations.zeus_bridge.find_zeus_script",
        return_value=None,
    ):
        text, is_error = server.dispatch_tool(
            "zeus_plan",
            {"task": "x"},
            entry_path=ENTRY,
            project_dir=PROJ,
            runner=lambda *a: _fake_result(),
        )

    assert is_error is True
    assert "localizar" in text


def test_dispatch_runner_oserror_becomes_clean_error():
    def runner(script, argv, cwd):
        raise OSError("python nao encontrado")

    text, is_error = server.dispatch_tool(
        "thero_audit",
        {},
        entry_path=ENTRY,
        project_dir=PROJ,
        runner=runner,
    )

    assert is_error is True
    assert "python nao encontrado" in text


# -- canal UTF-8 (regressão: codepage local não pode corromper acentos) ------


def test_force_utf8_makes_stream_emit_utf8_regardless_of_locale():
    # Simula um stdout em cp1252 (codepage típica de Windows) e exige que
    # _force_utf8 o reconverta para UTF-8: o travessão (U+2014) e o 'é'
    # devem sair como bytes UTF-8 válidos, não como 0x97/0xE9 locais.
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")

    server._force_utf8(stream)
    stream.write("memória — pé")
    stream.flush()

    assert raw.getvalue().decode("utf-8") == "memória — pé"


def test_force_utf8_tolerates_streams_without_reconfigure():
    # StringIO (usado em testes/capture) não tem reconfigure: deve ignorar
    # em silêncio em vez de estourar.
    server._force_utf8(io.StringIO())


def test_mcp_stdio_emits_decodable_utf8_end_to_end():
    # Roda o servidor real como um cliente MCP faria e exige que o stdout
    # decodifique como UTF-8 com os acentos das descrições intactos.
    payload = (
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n"
    )
    proc = subprocess.run(
        [sys.executable, str(THERO_ENTRY), "--mcp"],
        input=payload.encode("utf-8"),
        capture_output=True,
        # Sem PYTHONIOENCODING: o filho herda a codepage local (cp1252 no
        # Windows). Só o _force_utf8 do servidor garante UTF-8 no canal —
        # sem o fix, o travessão vira 0x97 e o decode abaixo estoura.
    )

    stdout = proc.stdout.decode("utf-8")  # UnicodeDecodeError aqui = regressão
    msg = json.loads(stdout.strip().splitlines()[-1])
    descs = {t["name"]: t["description"] for t in msg["result"]["tools"]}

    assert "memória" in descs["athena_recall"]
