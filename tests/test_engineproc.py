"""Ciclo de vida sob demanda, sem nunca ser o pai do motor.

Regra do repo (e do outro plano): nenhum teste abre socket nem gerou processo --
tudo injetado na costura publica do modulo.
"""

import os

import pytest

from thero import engineproc, localmodels


def test_find_binary_prefers_the_path_then_the_known_dirs(monkeypatch, tmp_path):
    exe = tmp_path / "ollama.exe"
    exe.write_text("", encoding="utf-8")
    monkeypatch.setattr(engineproc.shutil, "which", lambda n: str(exe))
    assert engineproc.find_binary() == str(exe)
    monkeypatch.setattr(engineproc.shutil, "which", lambda n: None)
    monkeypatch.setattr(engineproc.os.path, "isfile", lambda p: False)
    assert engineproc.find_binary() == ""


def test_start_without_the_binary_points_at_the_other_plan(monkeypatch):
    monkeypatch.setattr(engineproc, "find_binary", lambda: "")
    out = engineproc.start()
    assert out["ok"] is False and out["started"] is False
    assert "instalacao-do-engine-local" in out["msg"]
    assert "baixa" not in out["msg"]              # nao promete baixar nada


def test_start_spawns_detached_and_never_holds_the_child(monkeypatch):
    opened = []
    monkeypatch.setattr(engineproc, "find_binary", lambda: "C:/ollama.exe")
    # Duas fotos do mesmo motor: o `start()` consulta ANTES de spawnar (senao
    # seria um segundo daemon) e de NOVO no poll depois do Popen. Um fake
    # estatico nao casa as duas: e por isso aqui e uma sequencia.
    retratos = iter([{"up": False, "base": "", "models": [], "error": ""},
                     {"up": True, "base": "", "models": [], "error": ""}])
    monkeypatch.setattr(engineproc.localmodels, "status",
                        lambda base="": next(retratos))
    monkeypatch.setattr(engineproc.subprocess, "Popen",
                        lambda argv, **kw: opened.append(kw) or object())
    out = engineproc.start()
    assert out["started"] is True and out["up"] is True
    assert opened[0]["stdout"] is engineproc.subprocess.DEVNULL
    assert opened[0]["stderr"] is engineproc.subprocess.DEVNULL
    if engineproc.os.name == "nt":
        assert opened[0]["creationflags"] & engineproc.DETACHED_PROCESS
    # o objeto Popen nao e guardado em lugar nenhum: sem handle nao ha como
    # "manter vivo" nem "derrubar junto com a janela".
    assert not [n for n in vars(engineproc) if n.startswith("_child")]


def test_restart_kills_the_port_owner_then_starts(monkeypatch):
    killed = []
    monkeypatch.setattr(engineproc, "_pid_on_port", lambda port: 4321)
    monkeypatch.setattr(engineproc.subprocess, "run",
                        lambda argv, **kw: killed.append(argv))
    monkeypatch.setattr(engineproc.localmodels, "status",
                        lambda base="": {"up": True,
                                         "base": "http://127.0.0.1:11434",
                                         "models": [], "error": ""})
    monkeypatch.setattr(engineproc, "start",
                        lambda wait=0: {"ok": True, "up": True, "started": True,
                                        "pending": False, "msg": "subiu"})
    out = engineproc.restart()
    assert killed[0][:3] == ["taskkill", "/PID", "4321"]
    assert out["restarted"] is True and out["stopped"] is True
    assert "PID 4321" in out["msg"]


def test_pid_on_port_is_zero_when_nothing_listens(monkeypatch):
    monkeypatch.setattr(engineproc.os, "name", "posix")
    assert engineproc._pid_on_port(11434) == 0    # nada de fake no caminho


class PortNetstat:
    """Filho de `netstat -ano -p TCP` encenado: a saida real do Windows tem
    cabecalho, linhas UDP, ESTABLISHED e portas parecidas -- todas as que o
    parser NAO pode confundir com o daemon do Ollama."""

    HEAD = ("Active Connections\n\n  Proto  Local Address          "
            "Foreign Address        State           PID\n")

    def __init__(self, rows, error=None):
        self.rows = rows
        self.error = error
        self.argv = None

    def __call__(self, argv, **kwargs):
        self.argv = argv
        if self.error:
            raise self.error

        class Out:
            stdout = PortNetstat.HEAD + "\n".join(self.rows) + "\n"

        return Out()


def test_pid_on_port_reads_the_listening_row(monkeypatch):
    monkeypatch.setattr(engineproc.os, "name", "nt")
    fake = PortNetstat([
        "  TCP    127.0.0.1:11434        0.0.0.0:0              LISTENING"
        "       4321",
        "  TCP    127.0.0.1:11434        127.0.0.1:52100        ESTABLISHED"
        "       9999",
        "  TCP    127.0.0.1:1143         0.0.0.0:0              LISTENING"
        "       777",
        "  UDP    0.0.0.0:11434          *:*                                    "
        "555",
    ])
    monkeypatch.setattr(engineproc.subprocess, "run", fake)
    assert engineproc._pid_on_port(11434) == 4321
    assert fake.argv[:2] == ["netstat", "-ano"]      # TCP filtrado no proprio netstat


def test_pid_on_port_is_zero_without_a_listener_or_on_a_broken_pid(monkeypatch):
    monkeypatch.setattr(engineproc.os, "name", "nt")

    def rows(*lines):
        return PortNetstat(list(lines))

    monkeypatch.setattr(engineproc.subprocess, "run", rows())
    assert engineproc._pid_on_port(11434) == 0
    monkeypatch.setattr(engineproc.subprocess, "run", rows(
        "  TCP    127.0.0.1:11434        0.0.0.0:0              LISTENING"
        "       nao-e-numero"))
    assert engineproc._pid_on_port(11434) == 0


def test_pid_on_port_survives_a_missing_netstat(monkeypatch):
    # `netstat` fora do PATH nao pode derrubar a ponte: sem retrato, o
    # restart entende "ninguem escuta" e vira um start simples.
    monkeypatch.setattr(engineproc.os, "name", "nt")
    monkeypatch.setattr(engineproc.subprocess, "run",
                        PortNetstat([], error=OSError("sem netstat")))
    assert engineproc._pid_on_port(11434) == 0


def test_find_binary_falls_back_to_the_manual_install_folder(monkeypatch,
                                                             tmp_path):
    # O instalador oficial poe o binario em %LOCALAPPDATA%\Programs\Ollama sem
    # tocar no PATH: so pelo caminho ele e encontrado, e e o estado de quem
    # instalou na maquina (a espinha dorsal do outro plano).
    exe = tmp_path / "Programs" / "Ollama" / "ollama.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ")
    monkeypatch.setattr(engineproc.shutil, "which", lambda name: None)
    # `lambda c: os.path.isfile(c)` seria o mesmo que o modulo ja faz: o
    # que interessa aqui e o padrao Candidato vir do teste, nao do disco.
    monkeypatch.setattr(engineproc, "OLLAMA_WINDOWS_DIRS", [str(exe)])
    assert engineproc.find_binary() == str(exe)
    monkeypatch.setattr(engineproc, "OLLAMA_WINDOWS_DIRS", ["%NOVA%\nada.exe"])
    assert engineproc.find_binary() == ""


def test_start_reports_pending_when_the_daemon_is_slow(monkeypatch):
    # O teto curto e deliberate (cada segundo e a janela parada): estourou, a
    # resposta diz `pending` e a tela re-consulta no proximo clique.
    monkeypatch.setattr(engineproc, "find_binary", lambda: "C:/ollama.exe")
    down = {"up": False, "base": "", "models": [], "error": ""}
    monkeypatch.setattr(engineproc.localmodels, "status", lambda base="": down)
    monkeypatch.setattr(engineproc.subprocess, "Popen",
                        lambda argv, **kw: object())
    monkeypatch.setattr(engineproc.time, "sleep", lambda s: None)
    out = engineproc.start(wait=2)
    assert out["ok"] is True and out["started"] is True and out["pending"] is True
    assert out["up"] is False


def test_start_turns_a_spawn_failure_into_a_refusal(monkeypatch):
    # Binario no disco nao e binario executavel: antivírus/edicao travada da
    # OSError no Popen, e a ponte espera recusa com o nome do arquivo.
    monkeypatch.setattr(engineproc, "find_binary", lambda: "C:/ollama.exe")
    monkeypatch.setattr(engineproc.localmodels, "status",
                        lambda base="": {"up": False, "base": "", "models": [],
                                         "error": ""})

    def boom(argv, **kw):
        raise PermissionError(13, "acesso negado")

    monkeypatch.setattr(engineproc.subprocess, "Popen", boom)
    out = engineproc.start()
    assert out["ok"] is False and out["started"] is False
    assert "ollama.exe" in out["msg"]


def test_restart_is_not_offered_outside_windows(monkeypatch):
    monkeypatch.setattr(engineproc.os, "name", "posix")
    out = engineproc.restart()
    assert out["ok"] is False and out["restarted"] is False
    assert "Windows" in out["msg"]


def test_restart_without_a_listener_is_a_plain_start(monkeypatch):
    # ninguem escuta a porta: nada e morto (matar por nome esta fora de
    # questao), e `stopped` diz a tela que nao houve parada.
    killed = []
    monkeypatch.setattr(engineproc.os, "name", "nt")
    monkeypatch.setattr(engineproc.localmodels, "status",
                        lambda base="": {"up": False, "base":
                                         "http://127.0.0.1:11434",
                                         "models": [], "error": ""})
    monkeypatch.setattr(engineproc, "_pid_on_port", lambda port: 0)
    monkeypatch.setattr(engineproc.subprocess, "run",
                        lambda argv, **kw: killed.append(argv))
    monkeypatch.setattr(engineproc, "start",
                        lambda wait=None: {"ok": True, "up": True,
                                           "started": True, "pending": False,
                                           "msg": "no ar"})
    out = engineproc.restart()
    assert killed == []
    assert out["stopped"] is False and out["restarted"] is True


def test_restart_keeps_going_when_taskkill_refuses(monkeypatch):
    # taskkill pode estourar (PID ja morto, sem privilegio). Isso nao impede
    # o start de tentar: o objetivo e o motor no ar, nao o kill em si.
    monkeypatch.setattr(engineproc.os, "name", "nt")
    monkeypatch.setattr(engineproc.localmodels, "status",
                        lambda base="": {"up": False, "base":
                                         "http://127.0.0.1:11434",
                                         "models": [], "error": ""})
    monkeypatch.setattr(engineproc, "_pid_on_port", lambda port: 4321)

    def boom(argv, **kw):
        raise OSError("sem permissao")

    monkeypatch.setattr(engineproc.subprocess, "run", boom)
    monkeypatch.setattr(engineproc.time, "sleep", lambda s: None)
    monkeypatch.setattr(engineproc, "start",
                        lambda wait=None: {"ok": True, "up": True,
                                           "started": True, "pending": False,
                                           "msg": "no ar"})
    out = engineproc.restart()
    assert out["stopped"] is True
    assert "4321" in out["msg"]


def test_start_does_nothing_when_the_engine_is_already_up(monkeypatch):
    # Segundo daemon na mesma porta e o erro que esta linha fecha: o "iniciar"
    # da tela nao pode virar um segundo `ollama serve` quando ja ha um no ar
    # (o do usuario, instalado por ele).
    spawned = []
    monkeypatch.setattr(engineproc, "find_binary", lambda: "C:/ollama.exe")
    monkeypatch.setattr(engineproc.localmodels, "status",
                        lambda base="": {"up": True, "base": "", "models": [],
                                         "error": ""})
    monkeypatch.setattr(engineproc.subprocess, "Popen",
                        lambda argv, **kw: spawned.append(argv))
    out = engineproc.start()
    assert spawned == []
    assert out["ok"] is True and out["started"] is False and out["up"] is True
    assert "ja esta no ar" in out["msg"]
