"""Modelos locais (Ollama): listar, puxar e apagar pelo HTTP do próprio Ollama.

Contrato verificado na máquina: os consumidores são dois, cada um com seu par
de variáveis -- a Athena lê `ATHENA_OLLAMA_HOST` / `ATHENA_OLLAMA_MODEL`
(athena/src/athena/settings.py:52-72, default http://localhost:11434) e o
Sentinel lê `SENTINEL_OLLAMA_HOST` / `SENTINEL_OLLAMA_MODEL`
(sentinel/src/sentinel/settings.py:255-283, default http://127.0.0.1:11434 +
qwen3-coder-next, com veto de host fora de loopback). Os dois só consomem:
nada aqui instala motor -- o Thero escreve onde apontar.

Regra de segurança: só loopback, sem exceção. Nenhuma função daqui aceita
host remoto e nenhuma envia credencial (os endpoints locais do Ollama não
usam chave -- não inventar header de auth). Proibido print(): este módulo
vive no processo da ponte, cujo stdout é o canal JSON.
"""

from __future__ import annotations

import http.client
import json
import re
import urllib.error
import urllib.request
from typing import Iterator, Optional
from urllib.parse import urlparse

from thero.settings import (
    OLLAMA_DEFAULT_HOST,
    OLLAMA_DELETE_TIMEOUT,
    OLLAMA_PROBE_TIMEOUT,
    OLLAMA_PULL_TIMEOUT,
)

# Dependencia injetavel nos testes; o nome `urlopen` e usado modulo-afora
# de proposito para o monkeypatch funcionar.
urlopen = urllib.request.urlopen

# O netloc COMPLETO pelo qual o http.client conecta (host + porta opcional),
# nao so o hostname do urlparse: ele corta no PRIMEIRO ":", o http.client
# conecta no ULTIMO -- "http://localhost:11434.evil.com" passaria num teste
# de hostname e conectaria em outro host. Colchetes sao a forma IPv6 da URL.
_LOOPBACK_NETLOC = re.compile(
    r"(\[?(127\.0\.0\.1|localhost|::1)\]?)(:[0-9]{1,5})?", re.IGNORECASE
)


def normalize_base(host: Optional[str] = "") -> str:
    """Aceita '127.0.0.1:11434', 'localhost' ou URL completa; devolve URL.

    Descarta APENAS a "/" final -- escolha documentada nos testes: os
    endpoints locais pedem uma base seca, e path/query/fragment que
    sobrarem fazem o _assert_loopback recusar.
    """
    raw = (host or OLLAMA_DEFAULT_HOST).strip()
    if not raw:
        raw = OLLAMA_DEFAULT_HOST
    if "://" not in raw:
        raw = "http://" + raw
    return raw.rstrip("/")


def _assert_loopback_host(base: str) -> str:
    parsed = urlparse(base)
    # O userinfo (ate o ULTIMO "@") nao participa da conexao; o resto do
    # netloc sim, e por isso ele e validado inteiro.
    hostinfo = parsed.netloc.rpartition("@")[2]
    parsed.port  # dentro do veto: ValueError se a porta nao for 0..65535
    if _LOOPBACK_NETLOC.fullmatch(hostinfo) is None:
        raise ValueError(
            "apenas loopback e permitido para modelos locais "
            "(recebi %r)" % (base,)
        )
    return base


def _assert_no_path(base: str) -> str:
    parsed = urlparse(base)
    if parsed.path or parsed.params or parsed.query or parsed.fragment:
        raise ValueError(
            "a base do Ollama nao aceita caminho: os endpoints /api/* sao "
            "montados em cima dela (recebi %r)" % (base,)
        )
    return base


def _assert_loopback(base: str) -> str:
    return _assert_no_path(_assert_loopback_host(base))


def has_endpoint_path(base: str) -> bool:
    """True quando a base aponta para um caminho de API (o "/v1" do LM Studio).

    A API do Ollama mora na raiz, entao caminho presente quer dizer "esta
    base nao e a API do Ollama" -- e a sonda /api/tags nao vale para ela.
    Pergunta pura de URL: nenhuma rede, nenhum veto.
    """
    parsed = urlparse(normalize_base(base))
    return bool(parsed.path or parsed.params or parsed.query or
                parsed.fragment)


def _guard(base: str) -> str:
    """normalize_base -> _assert_loopback, na mesma ordem, nos quatro
    caminhos que fazem rede (list_models, pull, delete, status). O veto
    dispara antes de qualquer chamada de rede."""
    return _assert_loopback(normalize_base(base))


# Publico por contrato da Task 4 (providers.register): um satellite precisa
# recusar host remoto ANTES de montar o payload de escrita de config, e nao
# deve compor os privados (_guard/_assert_loopback) de outro satellite.
guard_base = _guard


def guard_host(base: str) -> str:
    """So o veto de HOST loopback -- por causa de provedor local que nao e a
    API do Ollama (decisao do dono em 2026-09-28, pergunta 1). O caminho
    passa: nada da gente conecta nessa base, entao nao ha URL a mentir.
    Para o Ollama em si continua valendo guard_base, caminho recusado."""
    return _assert_loopback_host(normalize_base(base))


def _describe(error: Exception, base: str) -> str:
    if isinstance(error, urllib.error.HTTPError):
        return "HTTP %d %s" % (error.code, error.reason or "")
    reason = getattr(error, "reason", None) or error
    # Recusa detectada por TIPO/errno, nao pela substring inglesa "refused":
    # no Windows a razao chega "[WinError 10061] Nenhuma conexao pudo ser
    # feita..." e o ramo nunca dispararia.
    refused = (
        isinstance(reason, ConnectionRefusedError)
        or getattr(reason, "errno", None) == 10061
        or getattr(reason, "winerror", None) == 10061
        or "refused" in str(reason).lower()
    )
    if refused:
        # Cita o HOST, nunca a razao crua do SO dentro da frase.
        return "conexao recusada em %s: o Ollama esta rodando?" % base
    return str(reason)


def _size_of(item: dict) -> int:
    # Tamanho e informativo: um valor malformado ("abc", None, lista) nao pode
    # derrubar a listagem inteira -- cai para 0 e o sizeHuman vira "-".
    try:
        return int(item.get("size") or 0)
    except (TypeError, ValueError):
        return 0


def human_bytes(size: int) -> str:
    if size <= 0:
        return "-"
    if size < 1024 ** 3:
        # Abaixo de 1 GB o "0.0 GB" seria lido como modelo vazio na tela.
        return "%.0f MB" % (size / 1024.0 ** 2)
    return "%.1f GB" % (size / 1024.0 ** 3)


def _fetch_tags(url_base: str) -> dict:
    # Caminho de rede UNICO do /api/tags: list_models e status o dividem para
    # o veto/parse nao ser duplicado. Request com method explicito: o contrato
    # de rede e sempre um objeto Request (nunca string crua), igual a pull.
    request = urllib.request.Request(url_base + "/api/tags", method="GET")
    try:
        with urlopen(request, timeout=OLLAMA_PROBE_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except (OSError, ValueError, http.client.HTTPException) as exc:
        # OSError ja cobre socket E urllib.error.URLError/HTTPError (os dois
        # herdam dele); HTTPException cobre o http.client que escapa do
        # OSError (BadStatusLine de servico nao-HTTP na 11434, IncompleteRead
        # no meio do corpo); ValueError so existe aqui pelo json.loads.
        return {"ok": False, "models": [], "error": _describe(exc, url_base)}
    if not isinstance(payload, dict):
        # JSON valido, mas nao o objeto esperado: a tela degrada com erro
        # humano, nunca com AttributeError no meio do payload da ponte.
        return {"ok": False, "models": [],
                "error": "resposta inesperada do Ollama (/api/tags)"}
    # Mesma fronteira logo abaixo: {"models": <nao-list>} iteraria as chaves/
    # letras como se fossem modelos. Lista e o unico formato aceito; chave
    # ausente e o caso legitimo de "nenhum modelo instalado".
    raw_models = payload.get("models") or []
    if not isinstance(raw_models, list):
        return {"ok": False, "models": [],
                "error": "resposta inesperada do Ollama (/api/tags)"}
    models = []
    for item in raw_models:
        # Item que nao seja objeto entra com valores vazios, sem excecao.
        entry = item if isinstance(item, dict) else {}
        details = entry.get("details")
        if not isinstance(details, dict):
            details = {}
        size = _size_of(entry)
        models.append({
            "name": entry.get("name", ""),
            "size": size,
            "sizeHuman": human_bytes(size),
            "params": details.get("parameter_size", ""),
            "family": details.get("family", ""),
        })
    return {"ok": True, "models": models, "error": ""}


def list_models(base: str = "") -> dict:
    return _fetch_tags(_guard(base))


def pull(name: str, base: str = "") -> Iterator[tuple]:
    """Gera ('out', linha) durante o download e ('exit', codigo) no fim.

    NAO e geradora pura: o veto roda na CHAMADA, antes de alguem iterar --
    um pull remoto nunca consumido nao pode ficar ileso. A resposta e lida
    INCREMENTALMENTE -- iterar o HTTPResponse em linhas, nao read() do corpo
    inteiro -- senao nenhum ('out', linha) chega antes de o download acabar
    e a tela de progresso nao tem o que mostrar. O formato ('out', str) /
    ('exit', int) e o que a ponte promete expor como
    `system.process.stream_command` (contrato PLANEJADO da Task 7; o modulo
    ainda nao existe) para tratar `ollama pull` e `npx skills` no mesmo
    painel de terminal.
    """
    return _pull(name, _guard(base))


def _pull(name: str, url_base: str) -> Iterator[tuple]:
    if not name:
        yield ("out", "informe o nome do modelo")
        yield ("exit", 2)
        return
    body = json.dumps({"name": name, "stream": True}).encode("utf-8")
    request = urllib.request.Request(
        url_base + "/api/pull", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    failed = False
    saw_event = False
    try:
        # timeout SEMPRE como keyword e nunca None (sem teto, um `ollama pull`
        # que pendura congela o loop stdio da ponte). O teto aqui e o do pull,
        # NAO o da sonda: e leitura por operacao, nao duracao total -- as
        # fases `verifying sha256`/`writing blob` passam minutos sem emitir
        # bytes, e 3 s de silencio abortariam um download de varios GB.
        with urlopen(request, timeout=OLLAMA_PULL_TIMEOUT) as response:
            for raw in response:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    yield ("out", line)
                    continue
                if not isinstance(event, dict):
                    # JSON atomico solto na stream ("123", "ok"): vira
                    # saida crua, nao AttributeError que escaparia pela
                    # geradora afora.
                    yield ("out", line)
                    continue
                saw_event = True
                # docs.ollama.com/api/errors: o erro de stream chega como
                # evento {"error": ...} SEM mudar o status HTTP. Linha de
                # progresso comum aqui daria exit 0 a um download quebrado,
                # e a tela verde entregaria o modelo ao motor na Task 5.
                if event.get("error"):
                    failed = True
                    yield ("out", str(event["error"]))
                    continue
                yield ("out", event.get("status") or line)
            if getattr(response, "length", 0):
                # Servidor com Content-Length que corta o corpo no meio:
                # iterar nao levanta em EOF antecipado -- so o length
                # residual denuncia o truncamento.
                failed = True
                yield ("out", "resposta truncada pelo Ollama "
                              "(download incompleto)")
    except (OSError, http.client.HTTPException) as exc:
        yield ("out", _describe(exc, url_base))
        yield ("exit", 1)
        return
    # Stream vazia (nenhum evento valido) nao afirma nada sobre o download:
    # exit 1 -- a ponte nao pode marcar verde sem manifest.
    yield ("exit", 1 if (failed or not saw_event) else 0)


def delete(name: str, base: str = "") -> dict:
    url_base = _guard(base)
    body = json.dumps({"name": name}).encode("utf-8")
    request = urllib.request.Request(
        url_base + "/api/delete", data=body,
        headers={"Content-Type": "application/json"}, method="DELETE",
    )
    try:
        # delete e mutacao, nao sonda: o /api/delete faz unlink de blobs de
        # GB e os 3 s da sonda reportariam falha num apagamento realizado.
        with urlopen(request, timeout=OLLAMA_DELETE_TIMEOUT) as response:
            response.read()  # drena o corpo: o IncompleteRead aparece
                             # DENTRO do try, nao no close() implicito
    except (OSError, http.client.HTTPException) as exc:
        return {"ok": False, "error": _describe(exc, url_base)}
    return {"ok": True, "error": ""}


def status(base: str = "") -> dict:
    """Retrato enxuto para a tela: pronto/ausente + quantos modelos.

    Contrato com envreport._ollama_probe (envreport.py:62-68): as chaves
    `up`, `base`, `models`, `error` -- exatamente as que ele le.
    """
    url_base = _guard(base)
    out = _fetch_tags(url_base)
    return {
        "up": bool(out["ok"]),
        "base": url_base,
        "models": out["models"],
        "error": out["error"],
    }
