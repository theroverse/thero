from pathlib import Path

from thero import envreport


class FakeWhich:
    def __init__(self, found):
        self.found = set(found)

    def __call__(self, name):
        return "/usr/bin/%s" % name if name in self.found else None


def _snap(tmp_path, monkeypatch, found, runner=None, ollama=None):
    monkeypatch.setattr(envreport, "_which", FakeWhich(found))
    monkeypatch.setattr(envreport, "_first_line",
                        runner or (lambda cmd: "%s ok" % cmd[0]))
    monkeypatch.setattr(envreport, "_ollama_probe",
                        lambda: ollama or {"up": False, "host": "", "models": [],
                                           "error": ""})
    monkeypatch.setattr(envreport, "_profile_path", lambda: None)
    skills = tmp_path / ".claude" / "skills"
    (skills / "react").mkdir(parents=True)
    (skills / "react" / "SKILL.md").write_text("# react", encoding="utf-8")
    (tmp_path / ".claude" / "CLAUDE.md").write_text("x" * 40, encoding="utf-8")
    return envreport.snapshot(entry_path=Path("thero.py"), home=tmp_path,
                              config_path=tmp_path / ".thero" / "config.json")


def test_reports_every_program_the_ui_asks_about(tmp_path, monkeypatch):
    s = _snap(tmp_path, monkeypatch, ["node", "npx", "claude"])
    assert {"node", "npx", "claude", "git"} <= set(s["tools"])
    assert s["tools"]["claude"]["found"] is True
    assert s["tools"]["node"]["ok"] is True


def test_broken_npx_is_reported_as_present_but_failing(tmp_path, monkeypatch):
    # estado REAL desta maquina em 2026-09-22: o shim existe e morre no npm-prefix
    s = _snap(tmp_path, monkeypatch, ["node", "npx"],
              runner=lambda cmd: "Error: Cannot find module ...npm-prefix.js")
    assert s["tools"]["npx"]["found"] is True
    assert s["tools"]["npx"]["ok"] is False
    assert "npm-prefix" in s["tools"]["npx"]["detail"]


def test_tool_without_version_output_is_not_ok(tmp_path, monkeypatch):
    s = _snap(tmp_path, monkeypatch, ["node"], runner=lambda cmd: "")
    assert s["tools"]["node"]["found"] is True
    assert s["tools"]["node"]["ok"] is False


def test_missing_tool_has_ok_false(tmp_path, monkeypatch):
    s = _snap(tmp_path, monkeypatch, ["node"])
    assert s["tools"]["claude"]["found"] is False
    assert s["tools"]["claude"]["ok"] is False


def test_a_hanging_version_probe_becomes_empty_instead_of_a_frozen_gui(monkeypatch):
    # O motor da ponte e um loop de stdio: se `claude --version` travar sem
    # responder, a janela inteira para. A sonda precisa de teto.
    import subprocess

    seen = {}

    def fake_run(command, **kw):
        seen["command"] = command
        seen["timeout"] = kw.get("timeout")
        raise subprocess.TimeoutExpired(command, kw.get("timeout") or 0)

    monkeypatch.setattr(envreport, "run_command", fake_run)
    assert envreport._first_line(["claude"]) == ""
    assert seen["command"] == ["claude", "--version"]
    assert seen["timeout"] == 10


def test_ollama_absent_is_up_false_with_host(tmp_path, monkeypatch):
    s = _snap(tmp_path, monkeypatch, ["node"],
              ollama={"up": False, "host": "http://127.0.0.1:11434",
                      "models": [], "error": "conexao recusada"})
    assert s["ollama"]["up"] is False
    assert s["ollama"]["modelCount"] == 0
    assert s["ollama"]["error"] == "conexao recusada"


def test_first_run_counts_and_fixed_command_name(tmp_path, monkeypatch):
    s = _snap(tmp_path, monkeypatch, ["node"])
    assert s["app"] == "thero"
    assert s["firstRun"] is True
    assert s["skills"]["installed"] == 1
    assert s["claudeMd"]["exists"] is True
    assert s["claudeMd"]["bytes"] == 40
    assert s["commandName"] == "thero"       # nome fixo, nunca editavel
    assert s["scope"] == "global"


def test_config_present_flips_first_run(tmp_path, monkeypatch):
    cfg = tmp_path / ".thero" / "config.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("{}", encoding="utf-8")
    s = _snap(tmp_path, monkeypatch, ["node"])
    assert s["firstRun"] is False
