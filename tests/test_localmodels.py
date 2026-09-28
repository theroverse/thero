"""Testes offline do cliente de modelos locais: nenhum toque em rede real.

O Ollama nao esta instalado nesta maquina e mesmo assim estivesse, a suíte
não pode depender dele: tudo passa pelo FakeUrlopen via monkeypatch.
"""

import json

import pytest

from thero import localmodels


class FakeResponse:
    """Corpo inteiro via read() E iteravel em linhas -- os dois contratos do
    `http.client.HTTPResponse` real. `served`/`read_calls` existem para o teste
    provar que o pull consome linha a linha em vez de slurpar o corpo."""

    def __init__(self, payload):
        self._payload = payload
        parts = payload.split(b"\n")
        # Corte so em b"\n", igual ao readline() do HTTPResponse real (que nao
        # trata \r, \v nem \f como fim de linha).
        self._lines = [p + b"\n" for p in parts[:-1]]
        if parts[-1]:
            self._lines.append(parts[-1])
        self.served = 0
        self.read_calls = 0

    def read(self):
        self.read_calls += 1
        return self._payload

    def __iter__(self):
        for raw in self._lines:
            self.served += 1
            yield raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeUrlopen:
    """Registra o que foi chamado e devolve o corpo pedido.

    Assina `__call__(request, timeout=None)` de propósito: o módulo SEMPRE
    passa um `urllib.request.Request` (nunca uma string crua) e o timeout
    como keyword -- é o contrato real de urlopen e a única forma do teste
    provar que nenhum `ollama pull` pendurado trava o loop da ponte.

    Guarda cada resposta em `responses` para o teste do pull poder contar
    quantas linhas do corpo foram de fato consumidas.
    """

    def __init__(self, body=b'{"models": []}', error=None):
        self.calls = []
        self.responses = []
        self.body = body
        self.error = error

    def __call__(self, request, timeout=None):
        self.calls.append({
            "url": request.full_url,
            "method": request.get_method(),
            "data": request.data,
            "timeout": timeout,
        })
        if self.error:
            raise self.error
        response = FakeResponse(self.body)
        self.responses.append(response)
        return response


TAGS = json.dumps({
    "models": [
        {"name": "llama3.2:latest", "size": 2020990000,
         "details": {"parameter_size": "3B", "family": "llama"}},
        {"name": "qwen2.5-coder:14b", "size": 8900000000,
         "details": {"parameter_size": "14B", "family": "qwen2"}},
    ]
}).encode("utf-8")


def test_list_models_reads_the_ollama_tags_endpoint(monkeypatch):
    fake = FakeUrlopen(TAGS)
    monkeypatch.setattr(localmodels, "urlopen", fake)
    out = localmodels.list_models("http://127.0.0.1:11434")
    assert out["ok"] is True
    assert [m["name"] for m in out["models"]] == [
        "llama3.2:latest", "qwen2.5-coder:14b"]
    assert out["models"][1]["sizeHuman"].startswith("8.3")
    assert fake.calls[0]["url"].endswith("/api/tags")
    assert fake.calls[0]["method"] == "GET"


def test_a_refused_port_reports_down_instead_of_raising(monkeypatch):
    import urllib.error

    monkeypatch.setattr(
        localmodels, "urlopen",
        FakeUrlopen(error=urllib.error.URLError("connection refused")),
    )
    out = localmodels.list_models("http://127.0.0.1:11434")
    assert out["ok"] is False
    assert out["models"] == []
    assert "recusado" in out["error"] or "refused" in out["error"]


def test_list_models_survives_a_non_list_models_field(monkeypatch):
    # {"models": <nao-list>} e o payload que quebra o `int(item.get(...))`:
    # a tela degrada com erro humano, nunca com excecao no meio do payload.
    body = json.dumps({"models": "descesperado"}).encode("utf-8")
    fake = FakeUrlopen(body)
    monkeypatch.setattr(localmodels, "urlopen", fake)
    out = localmodels.list_models("http://127.0.0.1:11434")
    assert out["ok"] is False
    assert out["models"] == []
    assert out["error"]


def test_list_models_coerces_a_broken_size_to_zero(monkeypatch):
    # Tamanho e informativo: um valor malformado nao esconde o modelo que o
    # usuario tem instalado -- cai para 0 / "-" e a listagem continua ok.
    body = json.dumps({"models": [{"size": "abc"}]}).encode("utf-8")
    fake = FakeUrlopen(body)
    monkeypatch.setattr(localmodels, "urlopen", fake)
    out = localmodels.list_models("http://127.0.0.1:11434")
    assert out["ok"] is True
    assert out["models"] == [{"name": "", "size": 0, "sizeHuman": "-",
                              "params": "", "family": ""}]


def test_only_loopback_is_ever_contacted(monkeypatch):
    fake = FakeUrlopen()
    monkeypatch.setattr(localmodels, "urlopen", fake)
    for bad in ("http://10.0.0.5:11434", "https://ollama.example.com",
                "http://[fe80::1]:11434", "http://localhost.evil.com:11434"):
        with pytest.raises(ValueError):
            localmodels.list_models(bad)
        with pytest.raises(ValueError):
            localmodels.status(bad)
        with pytest.raises(ValueError):
            localmodels.delete("llama3.2", base=bad)
        with pytest.raises(ValueError):
            list(localmodels.pull("llama3.2", base=bad))
    # o veto dispara antes de qualquer rede: nenhuma chamada chegou ao fake
    assert fake.calls == []


def test_loopback_spellings_are_all_accepted():
    for good in ("http://127.0.0.1:11434", "http://localhost:11434",
                 "http://[::1]:11434", "localhost:11434"):
        base = localmodels.normalize_base(good)
        assert localmodels._assert_loopback(base) == base


def test_pull_streams_lines_then_exits(monkeypatch):
    body = b"".join(
        json.dumps({"status": "downloading %d%%" % p}).encode() + b"\n"
        for p in (0, 50, 100)
    ) + json.dumps({"status": "success"}).encode() + b"\n"
    fake = FakeUrlopen(body)
    monkeypatch.setattr(localmodels, "urlopen", fake)
    events = []
    # Consumir aos poucos e quebrar no meio: so assim o teste ve se o
    # ('out', ...) sai DURANTE o download ou depois de o corpo acabar.
    for event in localmodels.pull("llama3.2", base="http://127.0.0.1:11434"):
        events.append(event)
        if event == ("out", "downloading 50%"):
            break
    assert events == [("out", "downloading 0%"), ("out", "downloading 50%")]
    response = fake.responses[0]
    # Streaming de verdade: 2 das 4 linhas entregues e NENHUM read() do corpo
    # inteiro -- com read() o corpo estaria slurpado antes do primeiro evento.
    assert response.served == 2
    assert response.served < len(response._lines)
    assert response.read_calls == 0
    # Contrato completo, consumido ate o fim numa segunda chamada: cada linha
    # NDJSON vira ('out', status) e o ultimo evento e sempre ('exit', 0).
    full = list(localmodels.pull("llama3.2", base="http://127.0.0.1:11434"))
    assert full == [
        ("out", "downloading 0%"),
        ("out", "downloading 50%"),
        ("out", "downloading 100%"),
        ("out", "success"),
        ("exit", 0),
    ]
    # timeout SEMPRE como keyword e nunca None: pull pendurado nao congela
    # o loop stdio da ponte
    call = fake.calls[0]
    assert call["url"].endswith("/api/pull")
    assert json.loads(call["data"]) == {"name": "llama3.2", "stream": True}
    # teto do pull, NAO o da sonda: 3 s de silencio numa fase `writing blob`
    # abortaria um download de varios GB no meio
    assert call["timeout"] == localmodels.OLLAMA_PULL_TIMEOUT
    assert localmodels.OLLAMA_PULL_TIMEOUT > localmodels.OLLAMA_PROBE_TIMEOUT


def test_pull_failure_becomes_exit_1_not_an_exception(monkeypatch):
    import urllib.error

    monkeypatch.setattr(
        localmodels, "urlopen",
        FakeUrlopen(error=urllib.error.HTTPError(
            "u", 500, "boom", None, None)),
    )
    events = list(localmodels.pull("x", base="http://127.0.0.1:11434"))
    assert events[-1][0] == "exit"
    assert events[-1][1] == 1


def test_delete_uses_the_delete_endpoint(monkeypatch):
    fake = FakeUrlopen(b"{}")
    monkeypatch.setattr(localmodels, "urlopen", fake)
    out = localmodels.delete("llama3.2", base="http://127.0.0.1:11434")
    assert out["ok"] is True
    assert fake.calls[0]["method"] == "DELETE"
    assert json.loads(fake.calls[0]["data"]) == {"name": "llama3.2"}


def test_delete_refuses_a_foreign_host():
    with pytest.raises(ValueError):
        localmodels.delete("llama3.2", base="http://10.1.2.3:11434")
