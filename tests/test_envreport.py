from pathlib import Path

from thero import envreport
from thero.settings import (
    COMMAND_MARKER_END,
    COMMAND_MARKER_START,
    ENV_MARKER_END,
    ENV_MARKER_START,
)


class FakeWhich:
    def __init__(self, found):
        self.found = set(found)

    def __call__(self, name):
        return "/usr/bin/%s" % name if name in self.found else None


def _patched(monkeypatch, found, runner=None, ollama=None):
    monkeypatch.setattr(envreport, "_which", FakeWhich(found))
    monkeypatch.setattr(envreport, "_version_probe",
                        runner or (lambda cmd: ("%s ok" % cmd[0], True)))
    monkeypatch.setattr(envreport, "_ollama_probe",
                        lambda: ollama or {"up": False, "host": "", "models": [],
                                           "error": ""})
    monkeypatch.setattr(envreport, "_profile_path", lambda: None)


def _home(tmp_path):
    skills = tmp_path / ".claude" / "skills"
    (skills / "react").mkdir(parents=True)
    (skills / "react" / "SKILL.md").write_text("# react", encoding="utf-8")
    (tmp_path / ".claude" / "CLAUDE.md").write_text("x" * 40, encoding="utf-8")
    return tmp_path


def _snap(tmp_path, monkeypatch, found, runner=None, ollama=None):
    _patched(monkeypatch, found, runner, ollama)
    home = _home(tmp_path)
    return envreport.snapshot(entry_path=Path("thero.py"), home=home,
                              config_path=tmp_path / ".thero" / "config.json")


def test_reports_every_program_the_ui_asks_about(tmp_path, monkeypatch):
    s = _snap(tmp_path, monkeypatch, ["node", "npx", "claude"])
    assert {"node", "npx", "claude", "git"} <= set(s["tools"])
    assert s["tools"]["claude"]["found"] is True
    assert s["tools"]["node"]["ok"] is True


def test_broken_npx_is_reported_as_present_but_failing(tmp_path, monkeypatch):
    # estado REAL desta maquina em 2026-09-22: o shim existe e morre no
    # npm-prefix (exit != 0) -- e o returncode, nao o texto, que diz isso.
    s = _snap(tmp_path, monkeypatch, ["node", "npx"],
              runner=lambda cmd: ("Error: Cannot find module ...npm-prefix.js",
                                  False))
    assert s["tools"]["npx"]["found"] is True
    assert s["tools"]["npx"]["ok"] is False
    assert "npm-prefix" in s["tools"]["npx"]["detail"]


def test_tool_without_version_output_is_not_ok(tmp_path, monkeypatch):
    # exit 0 sem saida tambem nao confirma nada
    s = _snap(tmp_path, monkeypatch, ["node"], runner=lambda cmd: ("", True))
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
    assert envreport._version_probe(["claude"]) == ("", False)
    assert seen["command"] == ["claude", "--version"]
    assert seen["timeout"] == 10


def test_a_hanging_profile_probe_becomes_none_instead_of_a_frozen_gui(monkeypatch):
    # Espelho da sonda de versao: `powershell -NoProfile -Command $PROFILE`
    # sem teto e o mesmo congelamento, no mesmo loop de stdio.
    import subprocess

    from thero.shell_command import windows

    seen = {}

    def fake_run(command, **kw):
        seen["command"] = command
        seen["timeout"] = kw.get("timeout")
        raise subprocess.TimeoutExpired(command, kw.get("timeout") or 0)

    monkeypatch.setattr(windows, "run_command", fake_run)
    monkeypatch.setattr(envreport.platform, "system", lambda: "Windows")
    assert envreport._profile_path() is None
    assert seen["command"] == ["powershell", "-NoProfile", "-Command", "$PROFILE"]
    assert seen["timeout"] == envreport.PROFILE_TIMEOUT == 5


def test_profile_probe_survives_a_broken_import(monkeypatch):
    # O import tardio tem de viver DENTRO da fronteira protegida: modulo
    # injetavel/quebrado degrada so o campo profilePath, nunca o payload.
    import sys

    monkeypatch.setattr(envreport.platform, "system", lambda: "Windows")
    monkeypatch.setitem(sys.modules, "thero.shell_command.windows", None)
    assert envreport._profile_path() is None


def test_a_denied_skills_folder_counts_zero_without_killing_the_snapshot(tmp_path, monkeypatch):
    # PermissionError em UM item da fronteira fs nao derruba a tela de Status.
    _patched(monkeypatch, ["node"])
    home = _home(tmp_path)
    skills = home / ".claude" / "skills"
    real_iterdir = Path.iterdir

    def iterdir(self):
        if self == skills:
            raise PermissionError(13, "negada")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    s = envreport.snapshot(entry_path=Path("thero.py"), home=home,
                           config_path=tmp_path / ".thero" / "config.json")
    assert s["skills"]["installed"] == 0
    assert s["claudeMd"]["exists"] is True
    assert s["tools"]["node"]["ok"] is True


def test_a_denied_claude_md_degrades_only_its_field(tmp_path, monkeypatch):
    # TOCTOU na fronteira fs: `exists()` disse sim, `stat()` nega logo
    # depois -- so o campo claudeMd degrada, o resto do snapshot sai inteiro.
    _patched(monkeypatch, ["node"])
    home = _home(tmp_path)
    claude_md = home / ".claude" / "CLAUDE.md"
    real_stat = Path.stat
    real_exists = Path.exists

    def stat(self, *args, **kw):
        if self == claude_md:
            raise PermissionError(13, "negada")
        return real_stat(self, *args, **kw)

    monkeypatch.setattr(Path, "stat", stat)
    monkeypatch.setattr(
        Path, "exists",
        lambda self: True if self == claude_md else real_exists(self))
    s = envreport.snapshot(entry_path=Path("thero.py"), home=home,
                           config_path=tmp_path / ".thero" / "config.json")
    assert s["claudeMd"] == {"exists": False, "bytes": 0, "backups": 0}
    assert s["skills"]["installed"] == 1


def test_nonzero_exit_with_clean_stdout_is_not_ok(monkeypatch):
    # Fim da adivinhacao pelo texto: exit != 0 imprimindo saida "limpa"
    # reporta ok False porque o sucesso vem do returncode real.
    class Result:
        returncode = 3
        stdout = "Thero wrapper pronto"
        stderr = ""

    monkeypatch.setattr(envreport, "run_command", lambda cmd, **kw: Result())
    assert envreport._version_probe(["claude"]) == ("Thero wrapper pronto", False)


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


def test_env_block_alone_does_not_count_as_installed_command(tmp_path):
    # A Task 5 escreve o bloco de ENV no MESMO $PROFILE e o bloco cita
    # "thero"; a checagem casa o marcador do comando global, nao substring.
    profile = tmp_path / "profile.ps1"
    profile.write_text(
        "%s\n$env:THERO_OLLAMA_MODEL = 'thero-local'\n%s\n"
        % (ENV_MARKER_START, ENV_MARKER_END),
        encoding="utf-8",
    )
    assert envreport._command_installed(profile) is False


def test_command_marker_in_profile_counts_as_installed(tmp_path):
    profile = tmp_path / "profile.ps1"
    profile.write_text(
        "%s\nfunction thero { python thero.py }\n%s\n"
        % (COMMAND_MARKER_START, COMMAND_MARKER_END),
        encoding="utf-8",
    )
    assert envreport._command_installed(profile) is True


def test_config_present_flips_first_run(tmp_path, monkeypatch):
    cfg = tmp_path / ".thero" / "config.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("{}", encoding="utf-8")
    s = _snap(tmp_path, monkeypatch, ["node"])
    assert s["firstRun"] is False


def test_ollama_probe_reads_the_real_localmodels_contract(monkeypatch):
    # envreport._ollama_probe le o dict de localmodels.status() com
    # COLCHETES; um rename de chave quebraria so em runtime, engolido
    # pelo except Exception do snapshot. Este teste amarra os dois lados
    # de verdade, 100% offline (o urlopen do localmodels e que e trocado).
    import json
    import urllib.error

    from thero import localmodels

    class Tags:
        def __init__(self, payload):
            self._payload = payload

        def read(self):
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    body = json.dumps({"models": [{"name": "llama3.2:latest",
                                   "size": 2020990000}]}).encode("utf-8")
    monkeypatch.setattr(localmodels, "urlopen",
                        lambda request, timeout=None: Tags(body))
    out = envreport._ollama_probe()
    assert out["up"] is True
    assert out["host"] == localmodels.OLLAMA_DEFAULT_HOST
    assert [m["name"] for m in out["models"]] == ["llama3.2:latest"]
    assert out["error"] == ""

    def down(request, timeout=None):
        raise urllib.error.URLError("nao escuta")

    monkeypatch.setattr(localmodels, "urlopen", down)
    out = envreport._ollama_probe()
    assert out["up"] is False
    assert out["models"] == []
    assert out["error"]
