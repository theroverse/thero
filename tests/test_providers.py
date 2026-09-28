import json

import pytest

from thero import providers


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return b'{"models": []}'


CFG = {
    "providers": [
        {"id": "openai", "label": "OpenAI", "preset": "openai",
         "authKind": "apikey", "authVar": "THERO_OPENAI_API_KEY",
         "base": "https://api.openai.com/v1", "model": "gpt-4o",
         "enabled": True, "origin": "thero",
         "roles": {"athena": False, "sentinel": True}, "lastCheck": ""},
        {"id": "ollama", "label": "Ollama (local)", "preset": "ollama",
         "authKind": "local", "authVar": "",
         "base": "http://127.0.0.1:11434", "model": "llama3.2",
         "enabled": True, "origin": "thero",
         "roles": {"athena": True, "sentinel": False}, "lastCheck": ""},
    ],
    "routing": {"mode": "zeus", "athena": "llama3.2", "sentinel": "llama3.2",
                "fallback": "Claude Code"},
}


def test_find_by_id_and_reject_unknown():
    assert providers.find(CFG, "openai")["label"] == "OpenAI"
    assert providers.find(CFG, "nao-existe") is None


def test_upsert_replaces_in_place_keeps_order():
    new = dict(CFG["providers"][0], label="OpenAI Trabalho")
    out = providers.upsert(CFG, new)
    assert out["providers"][0]["label"] == "OpenAI Trabalho"
    assert len(out["providers"]) == 2


def test_upsert_appends_a_brand_new_provider_at_the_end():
    extra = {"id": "groq", "label": "Groq", "preset": "groq",
             "authKind": "apikey", "authVar": "THERO_GROQ_API_KEY",
             "base": "", "model": "", "enabled": True, "origin": "user",
             "roles": {"athena": False, "sentinel": False}, "lastCheck": ""}
    out = providers.upsert(CFG, extra)
    assert [p["id"] for p in out["providers"]] == ["openai", "ollama", "groq"]


def test_remove_refuses_a_provider_thero_installed():
    with pytest.raises(providers.ProtectedProvider):
        providers.remove(CFG, "openai")


def test_remove_allows_the_users_own_entries():
    cfg = json.loads(json.dumps(CFG))
    cfg["providers"].append({"id": "meu", "label": "Meu", "origin": "user",
                             "roles": {}})
    out = providers.remove(cfg, "meu")
    assert "meu" not in [p["id"] for p in out["providers"]]


def test_remove_refuses_a_provider_a_routing_slot_still_models_on():
    # `models-set` grava routing[slot] = NOME DO MODELO, e a Task 5 escreve esse
    # nome em ATHENA_OLLAMA_MODEL / SENTINEL_OLLAMA_MODEL. Apagar o provedor que
    # fornece aquele modelo deixaria a variavel de ambiente com valor pendurado.
    # So se testa provedor `origin: user` -- os do Thero ja estao protegidos
    # antes, por outro excecao.
    cfg = json.loads(json.dumps(CFG))
    cfg["providers"].append({"id": "meu", "label": "Meu", "origin": "user",
                             "roles": {}, "model": "gpt-3.5-turbo",
                             "models": ["gpt-3.5-turbo"]})
    cfg["providers"].append({"id": "local2", "label": "Local 2",
                             "origin": "user", "roles": {},
                             "model": "llama3.2", "models": ["llama3.2"]})
    # routing.athena = llama3.2 (do CFG), e e do local2:
    with pytest.raises(providers.ProviderInUse):
        providers.remove(cfg, "local2")
    # routing.sentinel = llama3.2 tambem; re-roteado, o local2 fica livre:
    cfg["routing"]["athena"] = "gpt-3.5-turbo"
    cfg["routing"]["sentinel"] = "gpt-3.5-turbo"
    with pytest.raises(providers.ProviderInUse):
        providers.remove(cfg, "meu")
    out = providers.remove(cfg, "local2")
    assert "local2" not in [p["id"] for p in out["providers"]]


def test_register_session_kind_confirms_without_touching_the_network():
    # o tipo `session` e a sessao do proprio produto: o Thero nao roda nada.
    out = providers.register(dict(
        CFG["providers"][0], preset="claude", authKind="session",
        authVar="", base=""))
    assert out["ok"] is True
    assert "sessao" in out["msg"].lower()


def test_register_apikey_checks_only_whether_the_variable_exists(monkeypatch):
    monkeypatch.delenv("THERO_OPENAI_API_KEY", raising=False)
    out = providers.register(CFG["providers"][0])
    assert out["ok"] is False
    assert "THERO_OPENAI_API_KEY" in out["msg"]
    # a mensagem cita o NOME, nunca um valor
    assert "=" not in out["msg"].split("THERO_OPENAI_API_KEY")[1][:3]


def test_register_apikey_with_the_variable_present(monkeypatch):
    monkeypatch.setenv("THERO_OPENAI_API_KEY", "secret-nao-usado")
    out = providers.register(CFG["providers"][0])
    assert out["ok"] is True
    assert "secret-nao-usado" not in out["msg"]


def test_register_local_pings_only_loopback(monkeypatch):
    seen = []

    def fake(request, timeout=None):
        # list_models() passa um Request (nunca uma string) -- mesma folha do
        # FakeUrlopen da Task 3, so que aqui o que importa e a URL visitada.
        seen.append(getattr(request, "full_url", str(request)))
        return FakeResponse()

    monkeypatch.setattr(providers.localmodels, "urlopen", fake)
    out = providers.register(CFG["providers"][1])
    assert out["ok"] is True
    assert seen and seen[0].startswith("http://127.0.0.1:11434")
    assert seen[0].endswith("/api/tags")


def test_register_local_refuses_a_remote_endpoint(monkeypatch):
    p = dict(CFG["providers"][1], base="http://10.0.0.9:11434")
    out = providers.register(p)
    assert out["ok"] is False
    assert "loopback" in out["msg"]


def test_register_is_silent_about_values_even_when_the_var_is_set(monkeypatch):
    monkeypatch.setenv("THERO_OPENAI_API_KEY", "NUNCA-IMPRIMA-ISTO")
    out = providers.register(CFG["providers"][0])
    assert "NUNCA-IMPRIMA-ISTO" not in json.dumps(out)


def test_summary_marks_which_apps_use_which_provider():
    rows = providers.summary(CFG)
    by_id = {r["id"]: r for r in rows}
    assert by_id["ollama"]["usedBy"] == ["athena"]
    assert by_id["openai"]["usedBy"] == ["sentinel"]
