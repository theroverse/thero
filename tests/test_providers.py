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
    # `models-set` grava routing[slot] = NOME DO MODELO, e a Task 5
    # escreve esse nome em ATHENA_OLLAMA_MODEL / SENTINEL_OLLAMA_MODEL.
    # Apagar o provedor que fornece aquele modelo deixaria a variavel de
    # ambiente com valor pendurado.
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


# ---- C1: o campo quer o NOME da variavel, nunca o valor da chave ----
# O handler da Task 8 persiste o `msg` em provider["lastCheck"] e a tela o
# desenha: nada que sair de register pode carregar texto colado por engano.


def test_register_apikey_rejects_a_pasted_key_without_echoing_it():
    out = providers.register({"authKind": "apikey",
                              "authVar": "sk-TESTE-1234567890"})
    assert out["ok"] is False
    assert out["authState"] == "nome invalido"
    # nem no msg, nem em nenhuma outra chave do dict devolvido
    assert "sk-TESTE-1234567890" not in json.dumps(out)


def test_register_apikey_survives_a_non_text_auth_var():
    # payload JS pode trazer numero no campo; nao pode virar traceback
    out = providers.register({"authKind": "apikey", "authVar": 12345})
    assert out["ok"] is False
    assert out["authState"] == "nome invalido"


def test_register_apikey_empty_name_still_asks_for_one():
    out = providers.register({"authKind": "apikey", "authVar": "   "})
    assert out["ok"] is False
    assert out["authState"] == "incompleto"
    assert out["msg"] == "defina o nome da variavel que guarda a chave"


def test_register_apikey_valid_name_absent_still_awaits_the_key(monkeypatch):
    monkeypatch.delenv("THERO_MINHA_VAR", raising=False)
    out = providers.register({"authKind": "apikey",
                              "authVar": "THERO_MINHA_VAR"})
    assert out["ok"] is False
    assert out["authState"] == "aguardando chave"
    assert "THERO_MINHA_VAR" in out["msg"]


def test_register_apikey_valid_name_present_cites_only_the_name(monkeypatch):
    monkeypatch.setenv("THERO_MINHA_VAR", "segredo-colado-na-tela")
    out = providers.register({"authKind": "apikey",
                              "authVar": "THERO_MINHA_VAR"})
    assert out["ok"] is True
    assert out["authState"] == "chave presente"
    assert "THERO_MINHA_VAR" in out["msg"]
    assert "segredo-colado-na-tela" not in json.dumps(out)


# ---- I3: test_endpoint nao solta traceback nem credencial ----
# O msg volta para a tela e pode ser persistido; entao nem o "ValueError:
# ..." cru nem o userinfo de uma URL com chave podem aparecer nele.


def test_endpoint_without_a_base_stays_on_the_screen():
    out = providers.test_endpoint({"authKind": "local", "base": ""})
    assert out["ok"] is False
    assert "preencha" in out["msg"]


def test_endpoint_local_reports_a_dead_endpoint_as_text(monkeypatch):
    def boom(request, timeout=None):
        raise ConnectionRefusedError("nada escuta na porta")

    monkeypatch.setattr(providers.localmodels, "urlopen", boom)
    out = providers.test_endpoint({"authKind": "local",
                                   "base": "http://127.0.0.1:11434"})
    assert out["ok"] is False
    assert "Ollama" in out["msg"]
    assert "ValueError" not in json.dumps(out)


def test_endpoint_local_counts_models_when_it_answers(monkeypatch):
    monkeypatch.setattr(providers.localmodels, "urlopen",
                        lambda request, timeout=None: FakeResponse())
    out = providers.test_endpoint({"authKind": "local",
                                   "base": "http://127.0.0.1:11434"})
    assert out["ok"] is True
    assert "127.0.0.1" in out["msg"]
    assert "modelo(s)" in out["msg"]


def test_endpoint_local_refuses_a_remote_host_in_human_words():
    # hoje isto ESTOURA ValueError para fora da ponte; tem que virar texto.
    out = providers.test_endpoint({"authKind": "local",
                                   "base": "http://10.0.0.9:11434"})
    assert out["ok"] is False
    assert "loopback" in out["msg"]
    assert "ValueError" not in json.dumps(out)


def test_endpoint_never_echoes_a_credential_from_a_non_local_url():
    out = providers.test_endpoint(
        {"authKind": "apikey",
         "base": "https://usuario:sk-SEGREDO@api.example.test/v1"})
    assert out["ok"] is True
    assert "sk-SEGREDO" not in json.dumps(out)
    assert "usuario:" not in json.dumps(out)
    assert "api.example.test" in out["msg"]


def test_endpoint_local_refusal_does_not_echo_the_credential():
    out = providers.test_endpoint(
        {"authKind": "local",
         "base": "http://paulo:sk-SEGREDO@10.0.0.9:11434"})
    assert out["ok"] is False
    assert "sk-SEGREDO" not in json.dumps(out)
    assert "paulo" not in json.dumps(out)


# ---- I1+I2: veto de fallback sem falso positivo e rename que nao evapora ----


def _com_um_provedor_user(fallback):
    cfg = json.loads(json.dumps(CFG))
    cfg["providers"].append({"id": "meu", "label": "Meu Provedor",
                             "origin": "user", "roles": {}})
    cfg["routing"]["fallback"] = fallback
    return cfg


def test_remove_refuses_the_fallback_even_when_it_stores_the_id():
    cfg = _com_um_provedor_user("meu")
    with pytest.raises(providers.ProviderInUse):
        providers.remove(cfg, "meu")


def test_remove_refuses_the_fallback_named_by_its_label():
    cfg = _com_um_provedor_user("Meu Provedor")
    with pytest.raises(providers.ProviderInUse):
        providers.remove(cfg, "meu")


def test_remove_does_not_refuse_when_label_and_fallback_are_both_absent():
    # `None == None` nao e veto: sem fallback no routing nao ha o que perder.
    cfg = {"providers": [{"id": "x", "origin": "user", "roles": {}}]}
    out = providers.remove(cfg, "x")
    assert out["providers"] == []


def test_remove_does_not_refuse_a_different_fallback():
    cfg = _com_um_provedor_user("Outro")
    out = providers.remove(cfg, "meu")
    assert [p["id"] for p in out["providers"]] == ["openai", "ollama"]


def test_upsert_repoints_the_fallback_when_the_label_is_renamed():
    cfg = _com_um_provedor_user("Meu Provedor")
    novo = dict(cfg["providers"][-1], label="Nome Novo")
    out = providers.upsert(cfg, novo)
    assert out["routing"]["fallback"] == "Nome Novo"
    # o cfg de entrada nao pode ser mutado: a ponte guarda o `_cfg` em cache
    assert cfg["routing"]["fallback"] == "Meu Provedor"
    assert cfg["providers"][-1]["label"] == "Meu Provedor"


def test_upsert_rename_leaves_the_fallback_alone_when_it_stores_the_id():
    cfg = _com_um_provedor_user("meu")
    novo = dict(cfg["providers"][-1], label="Nome Novo")
    out = providers.upsert(cfg, novo)
    assert out["routing"]["fallback"] == "meu"


def test_upsert_rename_does_not_invent_a_fallback_for_a_label_less_provider():
    # label antigo vazio + fallback explicitamente vazio: "" == "" nao e
    # o provedor segurando a rota -- repontar criaria um fallback do nada.
    cfg = {"providers": [{"id": "x", "origin": "user", "roles": {}}],
           "routing": {"fallback": ""}}
    out = providers.upsert(cfg, {"id": "x", "label": "Agora Tem Nome",
                                 "origin": "user", "roles": {}})
    assert out["routing"]["fallback"] == ""


# ---- I4: id vazio nao engole entrada nova nem apaga a entrada errada ----


def test_upsert_refuses_a_provider_without_a_usable_id():
    for broken in ({"label": "Sem Id"}, {"id": "", "label": "Id Vazio"},
                   {"id": 7}):
        with pytest.raises(ValueError):
            providers.upsert(CFG, broken)


def test_upsert_refuses_something_that_is_not_a_provider_object():
    with pytest.raises(ValueError):
        providers.upsert(CFG, "openai")


def test_remove_refuses_an_empty_id_before_touching_anything():
    # o handler da Task 8 faz request.get("id", ""): remove(cfg, "") nao
    # pode APAGAR a entrada cujo id e "" -- tem que dizer "desconhecido".
    cfg = json.loads(json.dumps(CFG))
    cfg["providers"].append({"id": "", "origin": "user", "roles": {}})
    with pytest.raises(KeyError):
        providers.remove(cfg, "")
    with pytest.raises(KeyError):
        providers.remove(cfg, None)
    assert "" in [p["id"] for p in cfg["providers"]]


# ---- I5: agent que aponta para o provedor tambem trava a remocao ----


def test_remove_refuses_a_provider_an_agent_still_points_at():
    cfg = json.loads(json.dumps(CFG))
    cfg["providers"].append({"id": "meu", "label": "Meu", "origin": "user",
                             "roles": {}})
    cfg["agents"] = [{"id": "opencode", "label": "OpenCode",
                      "provider": "meu"}, "lixo"]
    # sem o veto, apagar deixa o OpenCode sem modelo e a Task 5 responde
    # "sem modelo definido" sem dizer a causa.
    with pytest.raises(providers.ProviderInUse) as exc:
        providers.remove(cfg, "meu")
    assert "OpenCode" in str(exc.value)


def test_remove_still_works_when_no_agent_references_the_provider():
    cfg = json.loads(json.dumps(CFG))
    cfg["providers"].append({"id": "meu", "label": "Meu", "origin": "user",
                             "roles": {}})
    cfg["agents"] = [{"id": "claude", "label": "Claude Code",
                      "provider": "claude"}]
    out = providers.remove(cfg, "meu")
    assert "meu" not in [p["id"] for p in out["providers"]]


# ---- I7: authKind normalizado; tipo fora da taxonomia e recusado ----


def test_register_trims_and_lowercases_the_auth_kind():
    # "Local " caindo no ramo apikey escaparia do veto de loopback.
    out = providers.register({"authKind": "Local ",
                              "base": "http://10.0.0.9:11434"})
    assert out["ok"] is False
    assert "loopback" in out["msg"]


def test_register_accepts_the_session_kind_in_any_capitalization():
    out = providers.register({"authKind": "Session"})
    assert out["ok"] is True
    assert "sessao" in out["msg"].lower()


def test_register_refuses_an_unknown_kind_naming_it():
    out = providers.register({"authKind": "oauth", "authVar": "QUALQUER"})
    assert out["ok"] is False
    assert out["authState"] == "tipo desconhecido"
    assert "oauth" in out["msg"]


def test_endpoint_uses_the_local_branch_even_for_a_sloppy_local_kind():
    out = providers.test_endpoint({"authKind": " Local",
                                   "base": "http://10.0.0.9:11434"})
    assert out["ok"] is False
    assert "loopback" in out["msg"]


# ---- I6: blank_from_preset nao sobrescreve seed nem gera nome impossivel


def test_blank_from_preset_avoids_ids_already_taken():
    out = providers.blank_from_preset("ollama", taken=("ollama",))
    assert out["id"] == "ollama-2"
    out = providers.blank_from_preset("ollama", taken=("ollama", "ollama-2"))
    assert out["id"] == "ollama-3"
    # o preset continua o pid informado; "user" e o unico origin possivel
    assert out["preset"] == "ollama"
    assert out["origin"] == "user"


def test_blank_from_preset_keeps_the_plain_id_when_nothing_is_taken():
    out = providers.blank_from_preset("groq")
    assert out["id"] == "groq"
    assert out["authVar"] == "THERO_GROQ_API_KEY"


def test_blank_from_preset_auth_var_is_a_valid_variable_name():
    # o nome gerado tem que bater o _ENV_NAME do C1: hifen e impossivel
    # em variavel de ambiente.
    out = providers.blank_from_preset("nao-existe")
    assert out["authVar"] == "THERO_NAO_EXISTE_API_KEY"
    assert providers._ENV_NAME.match(out["authVar"])
    out = providers.blank_from_preset("ollama", taken=("ollama",))
    assert out["authVar"] == ""  # preset local: sem chave, sem variavel
    out = providers.blank_from_preset("openai", taken=("openai",))
    assert out["authVar"] == "THERO_OPENAI_2_API_KEY"


def test_blank_from_preset_survives_a_none_or_off_taxonomy_pid():
    out = providers.blank_from_preset(None)
    assert out["id"] == "custom"
    assert out["preset"] == "custom"
    out = providers.blank_from_preset(5)
    assert out["id"] == "5"


# ---- M1: lixo no config.json editado a mao degrada, nao derruba a tela ----


def test_junk_entries_in_the_provider_list_are_skipped_everywhere():
    cfg = {"providers": ["abc", 42,
                         {"id": "ok1", "origin": "user",
                          "roles": ["athena"]}],
           "routing": "zeus", "agents": [None, 5]}
    assert providers.find(cfg, "ok1")["id"] == "ok1"
    assert providers.find(cfg, "abc") is None
    rows = providers.summary(cfg)
    assert [r["id"] for r in rows] == ["ok1"]
    assert rows[0]["usedBy"] == []  # roles lista: nenhum consumo
    out = providers.remove(cfg, "ok1")
    assert out["providers"] == []
    up = providers.upsert(cfg, {"id": "novo", "origin": "user"})
    assert [p["id"] for p in up["providers"]] == ["ok1", "novo"]


def test_providers_none_is_just_an_empty_registry():
    cfg = {"providers": None}
    assert providers.find(cfg, "x") is None
    assert providers.summary(cfg) == []
    with pytest.raises(KeyError):
        providers.remove(cfg, "x")
    up = providers.upsert(cfg, {"id": "a", "origin": "user"})
    assert [p["id"] for p in up["providers"]] == ["a"]


# ---- M2: `models` string nao e iterada letra a letra ----


def test_models_string_is_not_iterated_character_by_character():
    cfg = {"providers": [{"id": "u", "origin": "user", "roles": {},
                          "model": "", "models": "llama3.2"}],
           "routing": {"athena": "l", "sentinel": "outra"}}
    # "l" e uma letra da string, nao um modelo: apagar "u" nao mexe em rota.
    out = providers.remove(cfg, "u")
    assert out["providers"] == []


# ---- M3: nome compartilhado pertence a quem o tem como primario ----


def test_shared_model_name_is_owned_by_the_provider_that_lists_it_primary():
    cfg = json.loads(json.dumps(CFG))
    cfg["providers"].append({"id": "clone", "label": "Clone",
                             "origin": "user", "roles": {},
                             "model": "gpt-4o-mini",
                             "models": ["llama3.2", "gpt-4o-mini"]})
    # routing.athena/sentinel = llama3.2: quem deve fornecer o nome e o
    # ollama (primario dele), que sobrevive ao clone -- o preset copiado
    # nao pode ficar apagavel so depois de mexer na rota.
    out = providers.remove(cfg, "clone")
    assert "clone" not in [p["id"] for p in out["providers"]]


def test_models_only_name_still_holds_the_route_without_another_owner():
    cfg = json.loads(json.dumps(CFG))
    cfg["providers"].append({"id": "clone", "label": "Clone",
                             "origin": "user", "roles": {},
                             "model": "gpt-4o-mini",
                             "models": ["qwen9", "gpt-4o-mini"]})
    cfg["routing"]["athena"] = "qwen9"
    # ninguem mais tem qwen9 como primario: o clone segura a rota sozinho.
    with pytest.raises(providers.ProviderInUse):
        providers.remove(cfg, "clone")


# ---- M4: remove devolve copias, nao os objetos do cfg em cache ----


def test_remove_returns_copies_not_the_input_objects():
    cfg = json.loads(json.dumps(CFG))
    cfg["providers"].append({"id": "meu", "origin": "user", "roles": {}})
    out = providers.remove(cfg, "meu")
    survivor = out["providers"][0]
    assert survivor is not cfg["providers"][0]
    survivor["label"] = "Mutado"
    assert cfg["providers"][0]["label"] == "OpenAI"


# ---- M5/M6: a linha da tela e o `enabled` null ----


def test_summary_ships_the_fields_the_screen_draws():
    rows = providers.summary(CFG)
    by_id = {r["id"]: r for r in rows}
    ollama = by_id["ollama"]
    # os mesmos defaults de blank_from_preset para entrada sem o campo:
    # a tela le p.transport, p.models, p.roles e x.lastCheck sem perguntar.
    assert ollama["transport"] == ""
    assert ollama["models"] == []
    assert ollama["roles"] == {"athena": True, "sentinel": False}
    assert ollama["lastCheck"] == ""
    assert by_id["openai"]["roles"] == {"athena": False, "sentinel": True}


def test_summary_treats_enabled_null_as_enabled():
    # a UI desenha com `p.enabled !== false`; bool(None) divergia no engine
    cfg = json.loads(json.dumps(CFG))
    cfg["providers"][0]["enabled"] = None
    rows = providers.summary(cfg)
    by_id = {r["id"]: r for r in rows}
    assert by_id["openai"]["enabled"] is True
    cfg["providers"][0]["enabled"] = False
    rows = providers.summary(cfg)
    by_id = {r["id"]: r for r in rows}
    assert by_id["openai"]["enabled"] is False


# ---- ramos que a cobertura pegou de fora na versao original da task ----


def test_remove_refuses_a_user_provider_holding_a_consumer_role():
    cfg = json.loads(json.dumps(CFG))
    cfg["providers"].append({"id": "meu", "origin": "user",
                             "roles": {"athena": True, "sentinel": False}})
    with pytest.raises(providers.ProviderInUse) as exc:
        providers.remove(cfg, "meu")
    assert "athena" in str(exc.value)


def test_register_local_without_base_asks_for_the_endpoint():
    out = providers.register({"authKind": "local", "base": ""})
    assert out["ok"] is False
    assert out["authState"] == "incompleto"
    assert "endpoint local" in out["msg"]


def test_register_local_marks_a_dead_loopback_as_sem_resposta(monkeypatch):
    def boom(request, timeout=None):
        raise ConnectionRefusedError("porta vazia")

    monkeypatch.setattr(providers.localmodels, "urlopen", boom)
    out = providers.register({"authKind": "local",
                              "base": "http://127.0.0.1:11434"})
    # o veto de loopback foi passado; o endpoint e que nao respondeu agora.
    assert out["ok"] is False
    assert out["authState"] == "sem resposta"
