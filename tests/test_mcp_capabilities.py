from __future__ import annotations

from thero.mcp import capabilities


def test_registry_exposes_athena_zeus_thero():
    names = {cap.name for cap in capabilities.all_capabilities()}

    assert names == {
        "athena_index",
        "athena_recall",
        "athena_remember",
        "zeus_plan",
        "thero_audit",
    }


def test_get_capability_returns_by_name():
    cap = capabilities.get_capability("zeus_plan")

    assert cap is not None
    assert cap.kind == capabilities.ZEUS


def test_get_capability_unknown_returns_none():
    assert capabilities.get_capability("nao_existe") is None


def test_every_capability_has_valid_mcp_tool_shape():
    for cap in capabilities.all_capabilities():
        tool = cap.as_mcp_tool()
        assert set(tool) == {"name", "title", "description", "inputSchema"}
        assert tool["inputSchema"]["type"] == "object"


def test_argv_index_builds_full_command():
    cap = capabilities.get_capability("athena_index")
    argv = cap.build_argv(
        {
            "path": "/proj",
            "backend": "local",
            "model": "llama3.2",
            "max_files": 1000,
            "dry_run": True,
            "force": True,
        }
    )

    assert argv[:2] == ["index", "/proj"]
    assert "--backend" in argv and "local" in argv
    assert "--model" in argv and "llama3.2" in argv
    assert "--max-files" in argv and "1000" in argv
    assert "--dry-run" in argv
    assert "--force" in argv


def test_argv_index_minimal_defaults():
    cap = capabilities.get_capability("athena_index")
    argv = cap.build_argv({})

    assert argv == ["index"]


def test_argv_recall_requires_query_positional():
    cap = capabilities.get_capability("athena_recall")
    argv = cap.build_argv({"query": "como funciona o cache", "k": 3})

    assert argv == ["recall", "como funciona o cache", "--k", "3"]


def test_argv_remember_orders_kind_and_file():
    cap = capabilities.get_capability("athena_remember")
    argv = cap.build_argv({"kind": "decision", "file": "adr.md", "path": "/p"})

    assert argv == ["remember", "decision", "adr.md", "/p"]


def test_argv_plan_maps_task_and_context():
    cap = capabilities.get_capability("zeus_plan")
    argv = cap.build_argv({"task": "criar a nave", "context": "/mono"})

    assert argv == ["plan", "criar a nave", "--context", "/mono"]


def test_argv_audit_is_flag_only():
    cap = capabilities.get_capability("thero_audit")
    assert cap.build_argv({}) == ["--audit-only"]
