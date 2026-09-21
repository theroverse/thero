from __future__ import annotations

from unittest.mock import patch

import pytest

from thero.cli import main, parse_args
from thero.settings import DEFAULT_COMMAND_NAME


def set_argv(monkeypatch, *args):
    monkeypatch.setattr("sys.argv", ["thero.py", *args])


# ---------------------------------------------------------------------------
# parse_args
# ---------------------------------------------------------------------------


def test_parse_args_defaults(monkeypatch):
    set_argv(monkeypatch)

    args = parse_args()

    assert args.skills_only is False
    assert args.merge_only is False
    assert args.audit is False
    assert args.audit_only is False
    assert args.install_command is None
    assert args.local is False
    assert args.index is False
    assert args.plan is None
    assert args.check is False
    assert args.update is False


@pytest.mark.parametrize(
    "flag,attr",
    [
        ("--skills-only", "skills_only"),
        ("--merge-only", "merge_only"),
        ("--audit", "audit"),
        ("--audit-only", "audit_only"),
        ("--local", "local"),
        ("--index", "index"),
        ("--check", "check"),
        ("--update", "update"),
    ],
)
def test_parse_args_boolean_flags(monkeypatch, flag, attr):
    set_argv(monkeypatch, flag)

    args = parse_args()

    assert getattr(args, attr) is True


def test_parse_args_install_command_without_name(monkeypatch):
    set_argv(monkeypatch, "--install-command")

    args = parse_args()

    assert args.install_command == ""


def test_parse_args_install_command_with_name(monkeypatch):
    set_argv(monkeypatch, "--install-command", "mycmd")

    args = parse_args()

    assert args.install_command == "mycmd"


def test_parse_args_plan_with_task(monkeypatch):
    set_argv(monkeypatch, "--plan", "do the thing")

    args = parse_args()

    assert args.plan == "do the thing"
    assert args.plan_context is None


def test_parse_args_plan_with_context(monkeypatch):
    set_argv(
        monkeypatch, "--plan", "do the thing", "--plan-context", "/some/monorepo"
    )

    args = parse_args()

    assert args.plan_context == "/some/monorepo"


def test_parse_args_combines_local_with_other_flags(monkeypatch):
    set_argv(monkeypatch, "--skills-only", "--local")

    args = parse_args()

    assert args.skills_only is True
    assert args.local is True


# ---------------------------------------------------------------------------
# main() dispatch — every branch mocked below this point
# ---------------------------------------------------------------------------


MODULE = "thero.cli"


def _patch_all(**overrides):
    """
    Patch every downstream dependency main() might call, defaulting to
    permissive/successful behavior, so each test only overrides what it
    needs to assert on.
    """
    defaults = dict(
        run_athena_index=True,
        run_zeus_plan=True,
        validate_environment=True,
        check_skills=True,
        update_skills=True,
        command_exists=True,
        install_all_skills=None,
        merge_claude_md=None,
        ensure_claude_dir=None,
        install_global_command=None,
        audit_project=None,
        print_audit_workflow=None,
        print_summary=None,
        prompt_command_name="thero",
    )
    defaults.update(overrides)

    patchers = {
        name: patch(f"{MODULE}.{name}", return_value=value)
        for name, value in defaults.items()
    }
    return patchers


def _start_all(patchers):
    mocks = {name: p.start() for name, p in patchers.items()}
    return mocks


def _stop_all(patchers):
    for p in patchers.values():
        p.stop()


@pytest.fixture
def mocks():
    patchers = _patch_all()
    started = _start_all(patchers)
    yield started
    _stop_all(patchers)


def test_main_index_success_returns_without_exit(tmp_path, monkeypatch, mocks):
    set_argv(monkeypatch, "--index")

    main(tmp_path / "thero.py")

    mocks["run_athena_index"].assert_called_once()


def test_main_index_failure_exits(tmp_path, monkeypatch):
    set_argv(monkeypatch, "--index")

    with patch(f"{MODULE}.run_athena_index", return_value=False):
        with pytest.raises(SystemExit) as exc_info:
            main(tmp_path / "thero.py")

    assert exc_info.value.code == 1


def test_main_plan_success_returns_without_exit(tmp_path, monkeypatch, mocks):
    set_argv(monkeypatch, "--plan", "do the thing")

    main(tmp_path / "thero.py")

    mocks["run_zeus_plan"].assert_called_once_with(
        tmp_path / "thero.py", "do the thing", context=None
    )


def test_main_plan_forwards_plan_context(tmp_path, monkeypatch, mocks):
    set_argv(
        monkeypatch, "--plan", "do the thing", "--plan-context", "/some/monorepo"
    )

    main(tmp_path / "thero.py")

    mocks["run_zeus_plan"].assert_called_once_with(
        tmp_path / "thero.py", "do the thing", context="/some/monorepo"
    )


def test_main_plan_failure_exits(tmp_path, monkeypatch):
    set_argv(monkeypatch, "--plan", "do the thing")

    with patch(f"{MODULE}.run_zeus_plan", return_value=False):
        with pytest.raises(SystemExit) as exc_info:
            main(tmp_path / "thero.py")

    assert exc_info.value.code == 1


def test_main_check_exits_when_environment_invalid(tmp_path, monkeypatch):
    set_argv(monkeypatch, "--check")

    with patch(f"{MODULE}.validate_environment", return_value=False), patch(
        f"{MODULE}.check_skills"
    ) as mock_check:
        with pytest.raises(SystemExit) as exc_info:
            main(tmp_path / "thero.py")

    assert exc_info.value.code == 1
    mock_check.assert_not_called()


def test_main_check_exits_when_check_skills_fails(tmp_path, monkeypatch):
    set_argv(monkeypatch, "--check")

    with patch(f"{MODULE}.validate_environment", return_value=True), patch(
        f"{MODULE}.check_skills", return_value=False
    ):
        with pytest.raises(SystemExit) as exc_info:
            main(tmp_path / "thero.py")

    assert exc_info.value.code == 1


def test_main_check_success(tmp_path, monkeypatch, mocks):
    set_argv(monkeypatch, "--check")

    main(tmp_path / "thero.py")

    mocks["check_skills"].assert_called_once_with(True)


def test_main_update_exits_when_environment_invalid(tmp_path, monkeypatch):
    set_argv(monkeypatch, "--update")

    with patch(f"{MODULE}.validate_environment", return_value=False):
        with pytest.raises(SystemExit) as exc_info:
            main(tmp_path / "thero.py")

    assert exc_info.value.code == 1


def test_main_update_exits_when_update_skills_fails(tmp_path, monkeypatch):
    set_argv(monkeypatch, "--update")

    with patch(f"{MODULE}.validate_environment", return_value=True), patch(
        f"{MODULE}.update_skills", return_value=False
    ):
        with pytest.raises(SystemExit) as exc_info:
            main(tmp_path / "thero.py")

    assert exc_info.value.code == 1


def test_main_update_success(tmp_path, monkeypatch, mocks):
    set_argv(monkeypatch, "--update")

    main(tmp_path / "thero.py")

    mocks["update_skills"].assert_called_once_with(True)


def test_main_install_command_with_explicit_name_skips_prompt(tmp_path, monkeypatch, mocks):
    set_argv(monkeypatch, "--install-command", "mycmd")

    main(tmp_path / "thero.py")

    mocks["prompt_command_name"].assert_not_called()
    mocks["install_global_command"].assert_called_once_with(
        "mycmd", tmp_path / "thero.py", local=False
    )


def test_main_install_command_without_name_prompts(tmp_path, monkeypatch, mocks):
    set_argv(monkeypatch, "--install-command")

    main(tmp_path / "thero.py")

    mocks["prompt_command_name"].assert_called_once_with(DEFAULT_COMMAND_NAME)
    mocks["install_global_command"].assert_called_once_with(
        "thero", tmp_path / "thero.py", local=False
    )


def test_main_install_command_local(tmp_path, monkeypatch, mocks):
    set_argv(monkeypatch, "--install-command", "mycmd", "--local")

    main(tmp_path / "thero.py")

    mocks["install_global_command"].assert_called_once_with(
        "mycmd", tmp_path / "thero.py", local=True
    )


def test_main_audit_only_exits_when_environment_invalid(tmp_path, monkeypatch):
    set_argv(monkeypatch, "--audit-only")

    with patch(f"{MODULE}.validate_environment", return_value=False), patch(
        f"{MODULE}.audit_project"
    ) as mock_audit:
        with pytest.raises(SystemExit) as exc_info:
            main(tmp_path / "thero.py")

    assert exc_info.value.code == 1
    mock_audit.assert_not_called()


def test_main_audit_only_runs_audit_and_workflow(tmp_path, monkeypatch, mocks):
    set_argv(monkeypatch, "--audit-only")

    main(tmp_path / "thero.py")

    mocks["audit_project"].assert_called_once()
    mocks["print_audit_workflow"].assert_called_once()
    mocks["validate_environment"].assert_called_once_with(require_claude=True)


def test_main_merge_only_exits_when_environment_invalid(tmp_path, monkeypatch):
    set_argv(monkeypatch, "--merge-only")

    with patch(f"{MODULE}.validate_environment", return_value=False), patch(
        f"{MODULE}.merge_claude_md"
    ) as mock_merge:
        with pytest.raises(SystemExit) as exc_info:
            main(tmp_path / "thero.py")

    assert exc_info.value.code == 1
    mock_merge.assert_not_called()


def test_main_merge_only_success(tmp_path, monkeypatch, mocks):
    set_argv(monkeypatch, "--merge-only")

    main(tmp_path / "thero.py")

    mocks["validate_environment"].assert_called_once_with(require_claude=True)
    mocks["ensure_claude_dir"].assert_called_once()
    mocks["merge_claude_md"].assert_called_once()


def test_main_default_flow_exits_when_environment_invalid(tmp_path, monkeypatch):
    set_argv(monkeypatch)

    with patch(f"{MODULE}.validate_environment", return_value=False):
        with pytest.raises(SystemExit) as exc_info:
            main(tmp_path / "thero.py")

    assert exc_info.value.code == 1


def test_main_default_flow_installs_skills_merges_and_installs_command(
    tmp_path, monkeypatch, mocks
):
    set_argv(monkeypatch)

    main(tmp_path / "thero.py")

    mocks["install_all_skills"].assert_called_once_with(tmp_path / "thero.py", True)
    mocks["merge_claude_md"].assert_called_once()
    mocks["install_global_command"].assert_called_once_with(
        "thero", tmp_path / "thero.py", local=False
    )
    mocks["print_summary"].assert_called_once()


def test_main_default_flow_warns_when_claude_missing_but_continues(
    tmp_path, monkeypatch, mocks
):
    set_argv(monkeypatch)
    mocks["command_exists"].return_value = False

    main(tmp_path / "thero.py")

    mocks["merge_claude_md"].assert_not_called()
    mocks["install_global_command"].assert_called_once()


def test_main_skills_only_skips_merge_and_command(tmp_path, monkeypatch, mocks):
    set_argv(monkeypatch, "--skills-only")

    main(tmp_path / "thero.py")

    mocks["install_all_skills"].assert_called_once()
    mocks["merge_claude_md"].assert_not_called()
    mocks["install_global_command"].assert_not_called()
    mocks["print_summary"].assert_called_once()


def test_main_default_flow_with_audit_flag_runs_audit(tmp_path, monkeypatch, mocks):
    set_argv(monkeypatch, "--audit")

    main(tmp_path / "thero.py")

    mocks["audit_project"].assert_called_once()
    mocks["print_audit_workflow"].assert_called_once()


def test_main_local_targets_project_folder(tmp_path, monkeypatch, mocks):
    monkeypatch.chdir(tmp_path)
    set_argv(monkeypatch, "--local")

    main(tmp_path / "thero.py")

    mocks["install_all_skills"].assert_called_once_with(tmp_path / "thero.py", False)
    mocks["install_global_command"].assert_called_once_with(
        "thero", tmp_path / "thero.py", local=True
    )


# ---------------------------------------------------------------------------
# --mcp / --publish
# ---------------------------------------------------------------------------


def test_parse_args_mcp_and_publish_defaults(monkeypatch):
    set_argv(monkeypatch)

    args = parse_args()

    assert args.mcp is False
    assert args.publish is False
    assert args.publish_agent == "all"
    assert args.publish_out is None


def test_parse_args_publish_agent(monkeypatch):
    set_argv(monkeypatch, "--publish", "--publish-agent", "claude,qoder")

    args = parse_args()

    assert args.publish is True
    assert args.publish_agent == "claude,qoder"


def test_main_mcp_starts_server_and_returns(tmp_path, monkeypatch):
    set_argv(monkeypatch, "--mcp")

    with patch("thero.mcp.server.serve") as mock_serve, patch(
        f"{MODULE}.install_all_skills"
    ) as mock_install:
        main(tmp_path / "thero.py")

    mock_serve.assert_called_once_with(tmp_path / "thero.py")
    # MCP não pode disparar nenhum passo do fluxo de instalação.
    mock_install.assert_not_called()


def test_main_publish_writes_for_resolved_agents(tmp_path, monkeypatch):
    set_argv(monkeypatch, "--publish", "--publish-agent", "claude")

    out = tmp_path / "pub"
    set_argv(monkeypatch, "--publish", "--publish-agent", "claude", "--publish-out", str(out))

    with patch("thero.publish.installer.publish") as mock_publish, patch(
        "thero.publish.installer.serve_command", return_value="python thero.py --mcp"
    ):
        main(tmp_path / "thero.py")

    kwargs = mock_publish.call_args.kwargs
    assert kwargs["agents"] == ["claude"]
    assert kwargs["out_dir"] == out
    assert mock_publish.call_args.args[0] == tmp_path / "thero.py"


def test_main_publish_rejects_unknown_agent_exits(tmp_path, monkeypatch):
    set_argv(monkeypatch, "--publish", "--publish-agent", "bogus")

    with pytest.raises(SystemExit) as exc_info:
        main(tmp_path / "thero.py")

    assert exc_info.value.code == 1
