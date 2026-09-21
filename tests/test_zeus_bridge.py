from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from thero.integrations.zeus_bridge import (
    ZEUS_PATH_ENV_VAR,
    find_zeus_script,
    run_zeus_plan,
)


def test_env_var_takes_priority_when_file_exists(tmp_path, monkeypatch):
    zeus_script = tmp_path / "custom" / "zeus.py"
    zeus_script.parent.mkdir(parents=True)
    zeus_script.write_text("# entry", encoding="utf-8")
    monkeypatch.setenv(ZEUS_PATH_ENV_VAR, str(zeus_script))

    result = find_zeus_script(tmp_path / "thero" / "thero.py")

    assert result == zeus_script


def test_env_var_pointing_to_missing_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv(ZEUS_PATH_ENV_VAR, str(tmp_path / "nope.py"))

    result = find_zeus_script(tmp_path / "thero" / "thero.py")

    assert result is None


def test_falls_back_to_sibling_folder(tmp_path, monkeypatch):
    monkeypatch.delenv(ZEUS_PATH_ENV_VAR, raising=False)
    root = tmp_path / "myscripts"
    (root / "zeus").mkdir(parents=True)
    zeus_script = root / "zeus" / "zeus.py"
    zeus_script.write_text("# entry", encoding="utf-8")
    entry_path = root / "thero" / "thero.py"
    entry_path.parent.mkdir(parents=True)

    result = find_zeus_script(entry_path)

    assert result == zeus_script


def test_falls_back_to_ensure_tool_repo_when_no_sibling(tmp_path, monkeypatch):
    monkeypatch.delenv(ZEUS_PATH_ENV_VAR, raising=False)
    entry_path = tmp_path / "thero" / "thero.py"
    entry_path.parent.mkdir(parents=True)

    with patch(
        "thero.integrations.zeus_bridge.ensure_tool_repo",
        return_value=tmp_path / "managed" / "zeus.py",
    ) as mock_ensure:
        result = find_zeus_script(entry_path)

    assert result == tmp_path / "managed" / "zeus.py"
    mock_ensure.assert_called_once()


def test_run_zeus_plan_returns_false_when_script_not_found(tmp_path):
    with patch(
        "thero.integrations.zeus_bridge.find_zeus_script", return_value=None
    ), patch("thero.integrations.zeus_bridge.run_command") as mock_run:
        result = run_zeus_plan(tmp_path / "thero.py", "do the thing")

    assert result is False
    mock_run.assert_not_called()


def test_run_zeus_plan_builds_correct_command(tmp_path):
    zeus_script = tmp_path / "zeus.py"

    with patch(
        "thero.integrations.zeus_bridge.find_zeus_script",
        return_value=zeus_script,
    ), patch(
        "thero.integrations.zeus_bridge.run_command",
        return_value=MagicMock(returncode=0),
    ) as mock_run:
        result = run_zeus_plan(tmp_path / "thero.py", "do the thing")

    assert result is True
    called_command = mock_run.call_args.args[0]
    assert called_command[0] == sys.executable
    assert called_command[1] == str(zeus_script)
    assert called_command[2] == "plan"
    assert called_command[3] == "do the thing"


def test_run_zeus_plan_omits_context_flag_by_default(tmp_path):
    zeus_script = tmp_path / "zeus.py"

    with patch(
        "thero.integrations.zeus_bridge.find_zeus_script",
        return_value=zeus_script,
    ), patch(
        "thero.integrations.zeus_bridge.run_command",
        return_value=MagicMock(returncode=0),
    ) as mock_run:
        run_zeus_plan(tmp_path / "thero.py", "do the thing")

    called_command = mock_run.call_args.args[0]
    assert "--context" not in called_command


def test_run_zeus_plan_forwards_context_flag(tmp_path):
    zeus_script = tmp_path / "zeus.py"

    with patch(
        "thero.integrations.zeus_bridge.find_zeus_script",
        return_value=zeus_script,
    ), patch(
        "thero.integrations.zeus_bridge.run_command",
        return_value=MagicMock(returncode=0),
    ) as mock_run:
        run_zeus_plan(
            tmp_path / "thero.py",
            "do the thing",
            context="/some/monorepo",
        )

    called_command = mock_run.call_args.args[0]
    assert called_command[-2:] == ["--context", "/some/monorepo"]


def test_run_zeus_plan_propagates_failure_returncode(tmp_path):
    with patch(
        "thero.integrations.zeus_bridge.find_zeus_script",
        return_value=tmp_path / "zeus.py",
    ), patch(
        "thero.integrations.zeus_bridge.run_command",
        return_value=MagicMock(returncode=1),
    ):
        result = run_zeus_plan(tmp_path / "thero.py", "task")

    assert result is False
