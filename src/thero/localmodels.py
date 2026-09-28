"""Modelos locais (Ollama): listar, puxar e apagar pelo HTTP do próprio Ollama.

Contrato verificado na máquina: os consumidores são dois, cada um com seu par
de variáveis -- a Athena lê `ATHENA_OLLAMA_HOST` / `ATHENA_OLLAMA_MODEL`
(athena/src/athena/settings.py:52-72, default http://localhost:11434) e o
Sentinel lê `SENTINEL_OLLAMA_HOST` / `SENTINEL_OLLAMA_MODEL`
(sentinel/src/sentinel/settings.py:255-279, default http://127.0.0.1:11434 +
qwen3-coder-next, com veto de host fora de loopback). Os dois só consomem:
nada aqui instala motor -- o Thero escreve onde apontar.

Regra de segurança: só loopback, sem exceção. Nenhuma função daqui aceita
host remoto e nenhuma envia credencial (os endpoints locais do Ollama não
usam chave -- não inventar header de auth). Proibido print(): este módulo
vive no processo da ponte, cujo stdout é o canal JSON.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Iterator, Optional
from urllib.parse import urlparse

from thero.settings import OLLAMA_DEFAULT_HOST, OLLAMA_PROBE_TIMEOUT

# Dependencia injetavel nos testes; o nome `urlopen` e usado modulo-afora
# de proposito para o monkeypatch funcionar.
urlopen = urllib.request.urlopen

_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def normalize_base(host: Optional[str] = "") -> str:
    """Aceita '127.0.0.1:11434', 'localhost' ou URL completa; devolve URL."""
    raw = (host or OLLAMA_DEFAULT_HOST).strip()
    if not raw:
        raw = OLLAMA_DEFAULT_HOST
    if "://" not in raw:
        raw = "http://" + raw
    return raw.rstrip("/")


def _assert_loopback(base: str) -> str:
    # Comparacao EXATA de hostname: startswith/substring e o bypass classico
    # de http://localhost.evil.com:11434 .
    host = (urlparse(base).hostname or "").lower()
    if host not in _LOOPBACK:
        raise ValueError(
            "apenas loopback e permitido para modelos locais "
            "(recebi %r)" % (host or base)
        )
    return base


def _guard(base: str) -> str:
    """normalize_base -> _assert_loopback, na mesma ordem, nos quatro
    caminhos que fazem rede (list_models, pull, delete, status). O veto
    dispara antes de qualquer chamada de rede."""
    return _assert_loopback(normalize_base(base))


def _describe(error: Exception) -> str:
    if isinstance(error, urllib.error.HTTPError):
        return "HTTP %d %s" % (error.code, error.reason)
    reason = getattr(error, "reason", None) or error
    text = str(reason)
    if "refused" in text.lower():
        return (
            "Ollama nao respondeu (conexao recusada em %s). "
            "Ele esta rodando?" % text
        )
    return text


def list_models(base: str = "") -> dict:
    url = _guard(base) + "/api/tags"
    # Request com method explicito: o contrato de rede e sempre um objeto
    # Request (nunca string crua), igual a pull/delete.
    request = urllib.request.Request(url, method="GET")
    try:
        with urlopen(request, timeout=OLLAMA_PROBE_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, ValueError, OSError) as exc:
        return {"ok": False, "models": [], "error": _describe(exc)}
    if not isinstance(payload, dict):
        # JSON valido, mas nao o objeto esperado: a tela degrada com erro
        # humano, nunca com AttributeError no meio do payload da ponte.
        return {"ok": False, "models": [],
                "error": "resposta inesperada do Ollama (/api/tags)"}
    models = []
    for item in payload.get("models", []):
        size = int(item.get("size") or 0)
        models.append({
            "name": item.get("name", ""),
            "size": size,
            "sizeHuman": human_bytes(size),
            "params": (item.get("details") or {}).get("parameter_size", ""),
            "family": (item.get("details") or {}).get("family", ""),
        })
    return {"ok": True, "models": models, "error": ""}


def human_bytes(size: int) -> str:
    if size <= 0:
        return "-"
    return "%.1f GB" % (size / 1024.0 ** 3)


def pull(name: str, base: str = "") -> Iterator[tuple]:
    """Gera ('out', linha) durante o download e ('exit', codigo) no fim.

    O formato e o mesmo de system.process.stream_command, para a ponte tratar
    `ollama pull` e `npx skills` no mesmo painel de terminal.
    """
    url = _guard(base) + "/api/pull"
    if not name:
        yield ("out", "informe o nome do modelo")
        yield ("exit", 2)
        return
    body = json.dumps({"name": name, "stream": True}).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        # timeout SEMPRE como keyword e nunca None (sem teto, um
        # `ollama pull` que pendura congela o loop stdio da ponte). O corpo
        # e lido inteiro com read() e cortado em linhas -- a resposta NAO e
        # iteravel neste caminho.
        with urlopen(request, timeout=OLLAMA_PROBE_TIMEOUT) as response:
            payload = response.read()
    except (urllib.error.URLError, OSError) as exc:
        yield ("out", _describe(exc))
        yield ("exit", 1)
        return
    for raw in payload.split(b"\n"):
        line = raw.decode("utf-8", "replace").strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            yield ("out", line)
            continue
        if not isinstance(event, dict):
            # JSON atomico solto na stream ("123", "ok"): vira saida crua,
            # nao AttributeError que escaparia pela geradora afora.
            yield ("out", line)
            continue
        text = event.get("status") or event.get("error") or line
        yield ("out", text)
    yield ("exit", 0)


def delete(name: str, base: str = "") -> dict:
    url = _guard(base) + "/api/delete"
    body = json.dumps({"name": name}).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"},
        method="DELETE",
    )
    try:
        with urlopen(request, timeout=OLLAMA_PROBE_TIMEOUT) as response:
            response.read()
    except (urllib.error.URLError, OSError) as exc:
        return {"ok": False, "error": _describe(exc)}
    return {"ok": True, "error": ""}


def status(base: str = "") -> dict:
    """Retrato enxuto para a tela: pronto/ausente + quantos modelos.

    Contrato com envreport._ollama_probe (envreport.py:62-68): as chaves
    `up`, `base`, `models`, `error` -- exatamente as que ele le.
    """
    url_base = _guard(base)
    out = list_models(url_base)
    return {
        "up": bool(out["ok"]),
        "base": url_base,
        "models": out["models"],
        "error": out["error"],
    }
