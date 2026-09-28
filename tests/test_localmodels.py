"""Testes offline do cliente de modelos locais: nenhum toque em rede real.

O Ollama nao esta instalado nesta maquina e mesmo assim estivesse, a suíte
não pode depender dele: tudo passa pelo FakeUrlopen via monkeypatch.
"""

import http.client
import json
import urllib.error

import pytest

from thero import localmodels


class FakeResponse:
    """Corpo inteiro via read() E iteravel em linhas -- os dois contratos do
    `http.client.HTTPResponse` real. `served`/`read_calls` existem para o teste
    provar que o pull consome linha a linha em vez de slurpar o corpo, e
    `length` espelha os bytes QUE FALTAM no corpo: num servidor com
    Content-Length cortado no meio e o unico sinal de truncamento."""

    def __init__(self, payload, length=0):
        self._payload = payload
        parts = payload.split(b"\n")
        # Corte so em b"\n", igual ao readline() do HTTPResponse real (que nao
        # trata \r, \v nem \f como fim de linha).
        self._lines = [p + b"\n" for p in parts[:-1]]
        if parts[-1]:
            self._lines.append(parts[-1])
        self.served = 0
        self.read_calls = 0
        self.length = length

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


class ExplodingResponse(FakeResponse):
    """Entrega `after` linhas e ai levanta `exc` -- o IncompleteRead no meio
    da stream que um HTTPResponse real da quando o servidor derruba o socket
    durante um pull de varios GB, depois de o consumidor ja ter visto linhas."""

    def __init__(self, payload, exc, after=1):
        FakeResponse.__init__(self, payload)
        self._exc = exc
        self._after = after

    def __iter__(self):
        for raw in FakeResponse.__iter__(self):
            if self.served > self._after:
                raise self._exc
            yield raw


class FakeUrlopen:
    """Registra o que foi chamado e devolve o corpo pedido.

    Assina `__call__(request, timeout=None)` de propósito: o módulo SEMPRE
    passa um `urllib.request.Request` (nunca uma string crua) e o timeout
    como keyword -- é o contrato real de urlopen e a única forma do teste
    provar que nenhum `ollama pull` pendurado trava o loop da ponte.

    Guarda cada resposta em `responses` para o teste do pull poder contar
    quantas linhas do corpo foram de fato consumidas. `response=` injeta um
    FakeResponse pronto (o ExplodingResponse) e `length=` simula o corpo
    truncado com bytes residuais.
    """

    def __init__(self, body=b'{"models": []}', error=None, response=None,
                 length=0):
        self.calls = []
        self.responses = []
        self.body = body
        self.error = error
        self.response = response
        self.length = length

    def __call__(self, request, timeout=None):
        self.calls.append({
            "url": request.full_url,
            "method": request.get_method(),
            "data": request.data,
            "timeout": timeout,
        })
        if self.error:
            raise self.error
        response = self.response
        if response is None:
            response = FakeResponse(self.body, length=self.length)
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


@pytest.mark.parametrize("error", [
    # A recusa em ingles (Linux/POSIX) e a variante PT-BR do Windows com o
    # MESMO errno 10061: o ramo de "conexao recusada" nao pode depender de
    # substring inglesa, que nunca dispara na lingua desta maquina.
    urllib.error.URLError("connection refused"),
    urllib.error.URLError(ConnectionRefusedError(
        10061, "Nenhuma conexão pôde ser feita")),
])
def test_a_refused_port_reports_down_instead_of_raising(error, monkeypatch):
    monkeypatch.setattr(localmodels, "urlopen", FakeUrlopen(error=error))
    out = localmodels.list_models("http://127.0.0.1:11434")
    assert out["ok"] is False
    assert out["models"] == []
    # A mensagem cita o HOST, nao a razao crua do SO despejada na frase.
    assert "recusada" in out["error"]
    assert "127.0.0.1:11434" in out["error"]
    assert "refused" not in out["error"]


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


@pytest.mark.parametrize("bad", [
    # Os quatro originais: host remoto puro.
    "http://10.0.0.5:11434",
    "https://ollama.example.com",
    "http://[fe80::1]:11434",
    "http://localhost.evil.com:11434",
    # urlparse().hostname corta no PRIMEIRO ":", o http.client conecta no
    # ULTIMO: estes passam num teste de hostname e mudam de host/porta.
    "http://localhost:11434.evil.com",
    "http://localhost:11434.evil.com:80",
    "http://127.0.0.1:11434:80",
    # fragmento com host venenoso e path sobrando depois do host.
    "http://localhost#@evil.com",
    "http://127.0.0.1:11434/../",
])
def test_only_loopback_is_ever_contacted(bad, monkeypatch):
    fake = FakeUrlopen()
    monkeypatch.setattr(localmodels, "urlopen", fake)
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
    # A "/" final e aceita porque normalize_base a descarta ANTES do veto;
    # qualquer outro path/query/fragment (ver BAD_BASES acima) e recusa.
    for good in ("http://127.0.0.1:11434", "http://localhost:11434",
                 "http://[::1]:11434", "localhost:11434",
                 "http://localhost:11434/", "http://LOCALHOST:11434"):
        base = localmodels.normalize_base(good)
        assert localmodels._assert_loopback(base) == base


def test_guard_base_gates_a_remote_host_before_any_network(monkeypatch):
    # Publico por causa da Task 4 (providers.register): um satellite precisa
    # recusar host remoto ANTES de montar o payload de escrita de config, sem
    # compor os privados (_guard/_assert_loopback) de outro satellite. O veto e
    # so de URL -- o urlopen fakeado prova que nenhuma chamada sai daqui.
    fake = FakeUrlopen()
    monkeypatch.setattr(localmodels, "urlopen", fake)
    assert localmodels.guard_base("localhost:11434") == "http://localhost:11434"
    with pytest.raises(ValueError):
        localmodels.guard_base("http://10.0.0.5:11434")
    assert fake.calls == []


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
    monkeypatch.setattr(
        localmodels, "urlopen",
        FakeUrlopen(error=urllib.error.HTTPError(
            "u", 500, "boom", None, None)),
    )
    events = list(localmodels.pull("x", base="http://127.0.0.1:11434"))
    assert events[-1][0] == "exit"
    assert events[-1][1] == 1


def test_pull_reports_stream_error_as_exit_1(monkeypatch):
    # docs.ollama.com/api/errors: o erro de stream chega como evento
    # {"error": ...} SEM mudar o status HTTP. Tratado como linha comum, o
    # exit 0 entregaria um modelo inexistente para ATHENA_OLLAMA_MODEL.
    body = b'{"error": "pull failed: could not connect to registry"}\n'
    fake = FakeUrlopen(body)
    monkeypatch.setattr(localmodels, "urlopen", fake)
    events = list(localmodels.pull("x", base="http://127.0.0.1:11434"))
    assert events == [
        ("out", "pull failed: could not connect to registry"),
        ("exit", 1),
    ]


def test_pull_error_after_progress_still_exits_1(monkeypatch):
    body = (json.dumps({"status": "pulling manifest"}).encode() + b"\n"
            + json.dumps({"error": "no space left on device"}).encode() + b"\n")
    fake = FakeUrlopen(body)
    monkeypatch.setattr(localmodels, "urlopen", fake)
    events = list(localmodels.pull("x", base="http://127.0.0.1:11434"))
    assert events[0] == ("out", "pulling manifest")
    assert events[-1] == ("exit", 1)


def test_pull_truncated_body_exits_1(monkeypatch):
    # Servidor com Content-Length cortado no meio do corpo: iterar a resposta
    # nao levanta em EOF antecipado -- so o `length` residual denuncia.
    body = json.dumps({"status": "success"}).encode() + b"\n"
    fake = FakeUrlopen(body, length=4096)
    monkeypatch.setattr(localmodels, "urlopen", fake)
    events = list(localmodels.pull("x", base="http://127.0.0.1:11434"))
    assert ("out", "resposta truncada pelo Ollama (download incompleto)") \
        in events
    assert events[-1] == ("exit", 1)


def test_pull_empty_stream_exits_1(monkeypatch):
    # Stream sem NENHUM evento valido nao diz nada sobre o download: a ponte
    # nao pode ver verde onde nao houve manifest.
    fake = FakeUrlopen(b"\n")
    monkeypatch.setattr(localmodels, "urlopen", fake)
    assert list(localmodels.pull("x", base="http://127.0.0.1:11434")) == \
        [("exit", 1)]


def test_a_non_http_service_reports_down_instead_of_raising(monkeypatch):
    # HTTPException NAO herda de OSError: um servico nao-HTTP na 11434
    # (Ollama Desktop, proxy, WSL port-forward -- banal no Windows) faria
    # BadStatusLine escapar de list_models, delete e status.
    def broken():
        return FakeUrlopen(error=http.client.BadStatusLine("nao-e-http"))

    monkeypatch.setattr(localmodels, "urlopen", broken())
    out = localmodels.list_models("http://127.0.0.1:11434")
    assert out["ok"] is False
    assert out["error"]
    monkeypatch.setattr(localmodels, "urlopen", broken())
    out = localmodels.delete("llama3.2", base="http://127.0.0.1:11434")
    assert out["ok"] is False
    assert out["error"]
    monkeypatch.setattr(localmodels, "urlopen", broken())
    st = localmodels.status("http://127.0.0.1:11434")
    assert st["up"] is False
    assert st["error"]


def test_incomplete_read_mid_pull_stream_exits_1(monkeypatch):
    # IncompleteRead no MEIO da stream, depois de o consumidor ja ter visto
    # ("out", ...): vira ("out", diagnostico) + ("exit", 1), nunca excecao
    # escapando pela geradora afora.
    body = (json.dumps({"status": "pulling manifest"}).encode() + b"\n"
            + json.dumps({"status": "downloading 42%"}).encode() + b"\n")
    fake = FakeUrlopen(response=ExplodingResponse(
        body, http.client.IncompleteRead(b"partial"), after=1))
    monkeypatch.setattr(localmodels, "urlopen", fake)
    events = list(localmodels.pull("llama3.2", base="http://127.0.0.1:11434"))
    assert events[0] == ("out", "pulling manifest")
    assert events[-1] == ("exit", 1)
    assert len(events) == 3


def test_pull_veto_is_immediate_but_the_network_stays_lazy(monkeypatch):
    # pull() NAO e mais geradora pura: o veto roda na chamada, sem esperar
    # o iterador ser consumido -- pull remoto nunca iterado nao escapa ileso.
    with pytest.raises(ValueError):
        localmodels.pull("llama3.2", base="http://10.0.0.5:11434")
    # ...e o contrato observavel (Iterator[tuple]) nao mudou: a rede so
    # acontece quando alguem itera.
    fake = FakeUrlopen(json.dumps({"status": "success"}).encode() + b"\n")
    monkeypatch.setattr(localmodels, "urlopen", fake)
    iterator = localmodels.pull("llama3.2", base="http://127.0.0.1:11434")
    assert fake.calls == []
    assert list(iterator)[-1] == ("exit", 0)
    assert fake.calls[0]["url"].endswith("/api/pull")


def test_delete_uses_the_delete_endpoint(monkeypatch):
    from thero.settings import OLLAMA_DELETE_TIMEOUT

    fake = FakeUrlopen(b"{}")
    monkeypatch.setattr(localmodels, "urlopen", fake)
    out = localmodels.delete("llama3.2", base="http://127.0.0.1:11434")
    assert out["ok"] is True
    assert fake.calls[0]["method"] == "DELETE"
    assert json.loads(fake.calls[0]["data"]) == {"name": "llama3.2"}
    # delete e MUTACAO, nao sonda: 3 s reportariam falha num apagamento que
    # aconteceu de verdade (unlink de blobs de GB sob antivirus).
    assert fake.calls[0]["timeout"] == OLLAMA_DELETE_TIMEOUT == 30
    assert OLLAMA_DELETE_TIMEOUT > localmodels.OLLAMA_PROBE_TIMEOUT


def test_delete_refuses_a_foreign_host():
    with pytest.raises(ValueError):
        localmodels.delete("llama3.2", base="http://10.1.2.3:11434")


def test_status_returns_exactly_the_envreport_contract_keys(monkeypatch):
    # envreport._ollama_probe le com COLCHETES (envreport.py:62-68): um
    # rename de chave quebraria so em runtime, engolido pelo except largo
    # do snapshot. Os dois caminhos, up e down.
    monkeypatch.setattr(localmodels, "urlopen", FakeUrlopen(TAGS))
    up = localmodels.status("http://127.0.0.1:11434")
    assert set(up) == {"up", "base", "models", "error"}
    assert up["up"] is True
    assert up["base"] == "http://127.0.0.1:11434"
    assert len(up["models"]) == 2
    monkeypatch.setattr(localmodels, "urlopen",
                        FakeUrlopen(error=urllib.error.URLError("down")))
    down = localmodels.status("http://127.0.0.1:11434")
    assert set(down) == {"up", "base", "models", "error"}
    assert down["up"] is False
    assert down["models"] == []
    assert down["error"]


def test_human_bytes_degrades_to_mb_for_small_models():
    # Um modelo de 54 MB como "0.0 GB" e lido como "vazio" na tela.
    assert localmodels.human_bytes(54 * 1024 ** 2) == "54 MB"
    assert localmodels.human_bytes(int(8.9e9)) == "8.3 GB"
    assert localmodels.human_bytes(0) == "-"


def test_guard_host_leaves_a_non_ollama_local_path_alone():
    # Decisao do dono (2026-09-28, pergunta 1): o veto de HOST loopback vale
    # para todos; o que e especifico do Ollama e a sonda de modelos, e morar
    # na raiz. O LM Studio fala OpenAI-compativel em /v1 -- sem esta porta
    # ele nao existe como provedor.
    assert localmodels.guard_host(
        "http://127.0.0.1:1234/v1") == "http://127.0.0.1:1234/v1"
    assert localmodels.guard_host("localhost:1234/v1") == (
        "http://localhost:1234/v1")
    with pytest.raises(ValueError) as exc:
        localmodels.guard_host("http://10.0.0.5:1234/v1")
    assert "apenas loopback" in str(exc.value)


def test_guard_base_still_refuses_a_path_because_it_is_the_ollama_api():
    # O caminho continua proibido ONDE ele mentira: as chamadas reais
    # (/api/tags, /api/pull, DELETE /api/models) sao montadas em cima da
    # base, entao "/v1" produziria uma URL inexistente.
    for bad in ("http://127.0.0.1:11434/v1", "http://127.0.0.1:11434/../"):
        with pytest.raises(ValueError) as exc:
            localmodels.guard_base(bad)
        assert "caminho" in str(exc.value)


def test_has_endpoint_path_is_the_question_register_asks():
    assert localmodels.has_endpoint_path("http://127.0.0.1:1234/v1") is True
    assert localmodels.has_endpoint_path("localhost:11434") is False
    assert localmodels.has_endpoint_path("http://localhost:11434/") is False
