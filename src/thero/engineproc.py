import os
import shutil
import subprocess
import time
from urllib.parse import urlparse

from thero import localmodels
from thero.settings import OLLAMA_START_WAIT

OLLAMA_WINDOWS_DIRS = (
    # onde o instalador manual poe o binario
    r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe",
    r"%ProgramFiles%\Ollama\ollama.exe",
)
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


def find_binary() -> str:
    """O caminho do `ollama` que o USUARIO instalou, ou '' se nao existe.

    Nao baixa nem instala nada  -  o instalar e do plano
    2026-09-28-instalacao-do-engine-local.md (outro trabalho, dono dele). Isto
    so responde "existe na maquina?", que e o que a decisao do dono pede
    (checar,
    iniciar, reiniciar) e o que impede alguem de instalar por cima de um Ollama
    que ja esta la sem perguntar.
    """
    found = shutil.which("ollama")
    if found:
        return found
    for pattern in OLLAMA_WINDOWS_DIRS:
        candidate = os.path.expandvars(pattern)
        if os.path.isfile(candidate):
            return candidate
    return ""


def start(wait: int = OLLAMA_START_WAIT) -> dict:
    """Levanta o motor do usuario como processo DESANEXADO, e sonda ate
    responder.

    Nos nao somos o servico que hospeda o motor: `Popen` e chamado sem que
    ninguem guarde o objeto, entao fechar a janela nao derruba o Ollama e o
    Thero tambem nao o reanima. Auto-start no login continua sendo do Ollama.
    """
    binary = find_binary()
    if not binary:
        return {"ok": False, "up": False, "started": False, "pending": False,
                "msg": "Ollama nao esta nesta maquina. Instalar e passo do "
                       "plano 2026-09-28-instalacao-do-engine-local.md; o "
                       "Thero nao instala motor nem embute binario."}
    if localmodels.status()["up"]:
        return {"ok": True, "up": True, "started": False, "pending": False,
                "msg": "O Ollama ja esta no ar: nada a iniciar."}
    creationflags = 0
    if os.name == "nt":
        # creationflags != 0 so no Windows (no POSIX o subprocess levanta
        # ValueError). DEVNULL nos tres cabos: herdar o stdout da ponte seria
        # escrever no canal JSON (regra inegociavel 3).
        creationflags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen([binary, "serve"], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         shell=False, close_fds=True,
                         creationflags=creationflags)
    except OSError as exc:
        return {"ok": False, "up": False, "started": False, "pending": False,
                "msg": "nao consegui iniciar %s: %s" % (binary, exc)}
    for _ in range(max(1, int(wait))):
        if localmodels.status()["up"]:
            return {"ok": True, "up": True, "started": True, "pending": False,
                    "msg": "Ollama no ar (%s)." % binary}
        time.sleep(1)
    return {"ok": True, "up": False, "started": True, "pending": True,
            "msg": "Ollama subindo; reabra a tela de Modelos daqui a pouco."}


def _pid_on_port(port: int) -> int:
    """Quem escuta a porta do daemon, pelo `netstat -ano` do proprio Windows
    (stdlib-only: nada de psutil). 0 quando nao ha ninguem  -  e o caso em que
    'reiniciar' e so 'iniciar'. stdout sempre capturado, mesmo motivo do Popen
    acima."""
    if os.name != "nt":
        return 0
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return 0
    for line in out.splitlines():
        cols = line.split()
        if len(cols) >= 5 and cols[0].upper() == "TCP" \
                and cols[1].endswith(":%d" % port) \
                and cols[3].upper() == "LISTENING":
            try:
                return int(cols[4])
            except ValueError:
                return 0
    return 0


def restart(wait: int = OLLAMA_START_WAIT) -> dict:
    """Para o daemon que escuta a porta local e o levanta de novo.

    Alvo = PID do ouvinte da porta, NUNCA `/IM ollama.exe`: matar por nome
    derrubaria tambem o `ollama serve` que o usuario tem num terminal dele.
    Peso assumido - e por isso o unico gatilho e clique: baixa em
    andamento cai, e a mensagem diz isso.
    """
    if os.name != "nt":
        return {"ok": False, "up": False, "restarted": False, "stopped": False,
                "msg": "reiniciar o Ollama so esta implementado no Windows."}
    parsed = urlparse(localmodels.status()["base"])
    port = parsed.port or 11434
    pid = _pid_on_port(port)
    if pid:
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                           capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.SubprocessError):
            pass
        time.sleep(1)
    out = start(wait=wait)
    out["restarted"] = True
    out["stopped"] = bool(pid)
    out["msg"] = (("parei o Ollama (PID %d) e levantei de novo; baixas em "
                   "andamento caem. " % pid + out["msg"]) if pid
                  else out["msg"])
    return out
