"""Testes offline do cliente de modelos locais: nenhum toque em rede real.

O Ollama nao esta instalado nesta maquina e mesmo assim estivesse, a suíte
não pode depender dele: tudo passa pelo FakeUrlopen via monkeypatch.
"""

import json

import pytest

from thero import localmodels


class FakeResponse:
    """Corpo inteiro disponível via read() -- o mesmo contrato do
    HTTPResponse real para o uso que o módulo faz (sem iterar a resposta)."""

    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return self._payload

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
    """

    def __init__(self, body=b'{"models": []}', error=None):
        self.calls = []
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
        return FakeResponse(self.body)


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
    events = list(localmodels.pull("llama3.2", base="http://127.0.0.1:11434"))
    assert events[-1] == ("exit", 0)
    assert ("out", "downloading 50%") in events
    assert ("out", "success") in events
    call = fake.calls[0]
    assert call["url"].endswith("/api/pull")
    assert json.loads(call["data"]) == {"name": "llama3.2", "stream": True}
    # timeout SEMPRE como keyword e nunca None: pull pendurado nao congela
    # o loop stdio da ponte
    assert call["timeout"] == localmodels.OLLAMA_PROBE_TIMEOUT


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
