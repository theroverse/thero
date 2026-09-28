import subprocess

from thero.system import process


class FakePopen:
    def __init__(self, lines, code=0):
        self._lines = lines
        self.returncode = code

    def __iter__(self):
        return iter(self._lines)

    def wait(self):
        return self.returncode

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_lines_then_exit_code(monkeypatch):
    monkeypatch.setattr(process.subprocess, "Popen",
                        lambda *a, **k: FakePopen(["a\n", "b\n"]))
    out = list(process.stream_command(["npx", "skills", "check"]))
    assert out == [("out", "a"), ("out", "b"), ("exit", 0)]


def test_windows_launcher_translation_is_reused(monkeypatch):
    seen = {}

    def spy(command, **kwargs):
        seen["command"] = command
        return FakePopen([])

    monkeypatch.setattr(process.os, "name", "nt")
    monkeypatch.setattr(process.subprocess, "Popen", spy)
    list(process.stream_command(["npx", "skills"]))
    assert seen["command"][0] == "npx.cmd"


def test_stderr_is_merged_into_the_same_stream(monkeypatch):
    captured = {}

    def spy(command, **kwargs):
        captured["stderr"] = kwargs.get("stderr")
        captured["encoding"] = kwargs.get("encoding")
        return FakePopen([])

    monkeypatch.setattr(process.subprocess, "Popen", spy)
    list(process.stream_command(["node", "-v"]))
    assert captured["stderr"] is subprocess.STDOUT
    assert captured["encoding"] == "utf-8"


def test_a_missing_executable_becomes_a_line_and_exit_127(monkeypatch):
    def boom(*a, **k):
        raise OSError("cannot find the file specified")

    monkeypatch.setattr(process.subprocess, "Popen", boom)
    out = list(process.stream_command(["npx", "skills"]))
    assert out[-1] == ("exit", 127)
    assert out[0][0] == "out"
    assert "npx" in out[0][1]


def test_nonzero_exit_is_reported_not_raised(monkeypatch):
    monkeypatch.setattr(process.subprocess, "Popen",
                        lambda *a, **k: FakePopen(["x"], code=3))
    out = list(process.stream_command(["npx", "skills", "update"]))
    assert out[-1] == ("exit", 3)


def test_shell_is_never_used(monkeypatch):
    captured = {}

    def spy(command, **kwargs):
        captured.update(kwargs)
        captured["argv"] = command
        return FakePopen([])

    monkeypatch.setattr(process.subprocess, "Popen", spy)
    list(process.stream_command(["git", "status"], cwd=None))
    assert captured["shell"] is False
    assert captured["argv"] == ["git", "status"]


def test_an_empty_command_is_a_line_and_exit_2_not_a_crash(monkeypatch):
    # run_command() levanta ValueError em vazio (contrato antigo, mantido);
    # aqui quem chama e a ponte da Task 8, e excecao para fora viraria
    # traceback no canal JSON. A recusa sai como linha do proprio fluxo.
    def spy(*a, **k):
        raise AssertionError("Popen nao pode ser chamado com argv vazio")

    monkeypatch.setattr(process.subprocess, "Popen", spy)
    out = list(process.stream_command([]))
    assert out == [("out", "comando vazio"), ("exit", 2)]


def test_blank_lines_are_not_streamed_to_the_panel(monkeypatch):
    # O pull do ollama emite linha em branco entre as barras de progresso;
    # mandar ("out", "") para a janela acrescenta vazio ao painel sem saida
    # nenhuma, entao o filtro e contrato, nao enfeite.
    monkeypatch.setattr(process.subprocess, "Popen",
                        lambda *a, **k: FakePopen(["a\n", "\n", "\r\n", "b"]))
    out = list(process.stream_command(["ollama", "pull", "llama3.2"]))
    assert out == [("out", "a"), ("out", "b"), ("exit", 0)]
