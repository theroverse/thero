# Registro de Equipe (Papéis / "Funcionários") — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer do Thero o registro civil de uma "equipe" de papéis nomeados (apelido → provedor+modelo+capacidade), expondo um contrato de escolha por tipo de tarefa que o Zeus consome para rotear modelos.

**Architecture:** Um dicionário de papéis vive como chave de topo `team` em `~/.thero/config.json`, semeado por `presets.default_team()` derivado dos provedores já instalados. A lógica fica num módulo novo e puro `thero/src/thero/team.py` (sem rede, sem `print`), que classifica capacidade, checa disponibilidade injetável (via `localmodels.status`) e responde "dado um tipo de tarefa, qual papel/modelo usar?". A escolha chega a quem imprime pelo `label` (apelido ou nome explícito) + flag `local`, exposta a satélites por uma ferramenta MCP e por `--team-*` na CLI (stdout JSON).

**Tech Stack:** Python 3.9+, stdlib apenas (`json`, `typing`). pytest offline; rede/sonda sempre injetada. Convenção dos módulos novos do Thero: texto que atravessa a ponte/JSON é **ASCII sem acento**; `config.json` em si aceita acento (`ensure_ascii=False` já gravado, verificado em `tests/test_config.py:24-29`).

---

## Contexto real (lido antes de escrever — não presumir)

- O campo `routing` **não está morto**: é lido por `apply.py:300` (`profile_env_block` grava `$env:ATHENA_OLLAMA_MODEL`/`SENTINEL_OLLAMA_MODEL`) e por `providers.py` (guarda de remoção, rename do `fallback`). Mas `routing` só alimenta os consumidores de **env** (Athena/Sentinel); ele **não** orienta o Zeus. Este plano cria o `team` como registro paralelo e **não** mexe na semântica de `routing`.
- `config.load()` sobrepõe chaves de topo salvas sobre os defaults (`config.py:52-57`), então adicionar `"team"` em `default_config()` sobrevive ao round-trip sem tocar em merge. `test_default_config_shape` (`tests/test_config.py:6-11`) **não** enumera as chaves de topo exaustivamente, então adicionar uma chave nova não quebra a suíte.
- Disponibilidade local verificável hoje: `localmodels.status(base)` devolve `{"up","base","models","error"}` onde `models` é lista de `{"name",...}` (`localmodels.py:270-283`). É a única fonte de "o modelo X está instalado?".
- Disponibilidade de provedores de nuvem verificável hoje: apenas `authState` já salvo (`providers.register` escreve `"chave presente"`/`"sessao confirmada"`/`"respondeu"`, `providers.py:173-228`). **Não há telemetria de cota de fornecedor** sem chamada paga — por isso a cota de nuvem é **anotada pelo usuário**, nunca inferida lendo segredo.
- A ponte GUI↔motor (`src/thero/bridge.py`) **ainda não existe** em `src` (confirmado por `ls`): está sendo escrita em paralelo no plano `docs/superpowers/plans/2026-09-22-gui-engine-bridge.md`. Por isso a Task 7 é **condicional a essa dependência** e as Tasks 1-6 vivem inteiramente em arquivos que não colidem com ela (novo `team.py` + `presets.py`/`config.py`/`capabilities.py`, que a ponte só lê).

---

## File Structure

**Cria:**
- `thero/src/thero/team.py` — registro puro de papéis: `default`-independente, `find`/`upsert`/`remove`/`list_roles`, disponibilidade (`provider_available`, `is_local`), a política `pick(cfg, task_type, *, status)`, e os formatadores de narrativa `format_actor`/`default_warnings`. Responsabilidade única: **decidir quem atende uma tarefa**; nunca imprime, nunca faz rede direta.
- `thero/tests/test_team.py` — suíte offline de tudo acima (injeta `status_fn`/dict `status`).

**Modifica (aditivo, fora da zona da ponte em paralelo):**
- `thero/src/thero/presets.py` — acrescenta `default_team()` (sementes derivadas dos seeds de `default_providers()`).
- `thero/src/thero/config.py` — `default_config()` passa a incluir `"team": presets.default_team()`.
- `thero/src/thero/mcp/capabilities.py` — registra `thero_team_list` e `thero_team_pick` (kind `THERO`).
- `thero/src/thero/cli.py` — tratamento antecipado das flags `--team-list`/`--team-pick` (logo após o bloco `--mcp`), imprimindo **uma** linha JSON e retornando antes do banner.
- `thero/tests/test_team_cli.py` — cobre as duas flags pela saída JSON (sem tocar na rede).

**Modifica (Task 7, só se `bridge.py` já estiver no tree):**
- `thero/src/thero/bridge.py` — família de comandos `team-*` seguindo o mesmo `_ok`/`_err`/`COMMANDS` já definidos na Task 7-8 da ponte.

---

## Task 1: Esquema `team` no config e `default_team()` em presets

**Files:**
- Modify: `thero/src/thero/presets.py` (acrescentar função + sementes, depois de `default_routing`, linha ~243)
- Modify: `thero/src/thero/config.py:33-40` (`default_config`)
- Test: `thero/tests/test_team.py` (criar, só os testes de esquema por ora)

- [ ] **Step 1: Escrever o teste que falha** em `thero/tests/test_team.py`

```python
from __future__ import annotations

from thero import config, presets


CAPACITIES = {"local", "medio", "alto"}


def test_default_team_seeds_the_three_workers():
    team = presets.default_team()
    ids = [r["id"] for r in team]
    # P.O. (decisao), Dev (medio), Estagiarios (local) -- apelidos do dono.
    assert {"po", "dev", "estagiarios"} <= set(ids)
    for role in team:
        assert set(["id", "nickname", "capacity", "provider", "model",
                    "task_types", "enabled", "quota"]) <= set(role)
        assert role["capacity"] in CAPACITIES
        assert role["quota"]["state"] in ("ok", "esgotado", "desconhecido")


def test_default_team_binds_to_installed_seeds():
    prov_ids = {p["id"] for p in presets.default_providers()}
    for role in presets.default_team():
        assert role["provider"] in prov_ids  # nunca aponta provedor inexistente


def test_default_config_carries_team_and_roundtrips(tmp_path):
    cfg = config.default_config()
    assert "team" in cfg and cfg["team"]
    p = tmp_path / "config.json"
    saved = config.save(cfg, path=p)
    assert saved == p
    assert config.load(p) == cfg


def test_load_fills_missing_team_key_on_an_older_file(tmp_path):
    import json
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"version": 1, "providers": []}), encoding="utf-8")
    cfg = config.load(p)
    assert cfg["team"] == presets.default_team()   # chave nova vem do default
    assert cfg["providers"] == []                   # escolha do usuario vence
```

- [ ] **Step 2: Rodar para confirmar a falha**

Run: `python -m pytest tests/test_team.py -q`
Expected: falha — `AttributeError: module 'thero.presets' has no attribute 'default_team'` e `"team" in cfg` falso.

- [ ] **Step 3: Implementar `default_team()`** — acrescentar ao fim de `thero/src/thero/presets.py`

```python
# Registro de "equipe" do Zeus: papéis nomeados -> provedor+modelo+capacidade.
# Semeado a partir dos DEFAULT_PROVIDER_SEEDS acima (claude/openai/ollama).
# `task_types` casa com as categorias que o Zeus gera nos passos do plano
# (simple/standard/planning/decision). `capacity` ordena em CAPACITY_ORDER.
# `quota.state` e ANOTADO pelo usuario (nunca telemetria de fornecedor):
# "esgotado" tira o papel da corrida sem ler nenhuma chave.
DEFAULT_TEAM_SEEDS: list = [
    {"id": "po", "nickname": "P.O.", "capacity": "alto",
     "provider": "claude", "model": "opus",
     "task_types": ["planning", "decision", "standard"], "enabled": True},
    {"id": "dev", "nickname": "Dev", "capacity": "medio",
     "provider": "claude", "model": "sonnet",
     "task_types": ["standard", "simple"], "enabled": True},
    {"id": "estagiarios", "nickname": "Estagiarios", "capacity": "local",
     "provider": "ollama", "model": "llama3.2",
     "task_types": ["simple"], "enabled": True},
]


def default_team() -> list:
    out = []
    for seed in DEFAULT_TEAM_SEEDS:
        out.append({
            "id": seed["id"],
            "nickname": seed["nickname"],
            "capacity": seed["capacity"],
            "provider": seed["provider"],
            "model": seed["model"],
            "task_types": list(seed["task_types"]),
            "enabled": True,
            "quota": {"state": "desconhecido", "note": ""},
        })
    return out
```

- [ ] **Step 4: Ligar na `default_config()`** — editar `thero/src/thero/config.py:33-40`

```python
def default_config() -> dict:
    return {
        "version": CONFIG_VERSION,
        "providers": presets.default_providers(),
        "agents": presets.default_agents(),
        "routing": presets.default_routing(),
        "team": presets.default_team(),
        "preferences": {"scope": "global"},
    }
```

- [ ] **Step 5: Rodar a suíte inteira**

Run: `python -m pytest -q`
Expected: `394 + 4 = 398 passed` (nenhum teste antigo quebra: a chave nova de topo é sobreposta, não enumerada).

- [ ] **Step 6: Commit local**

```bash
git add src/thero/presets.py src/thero/config.py tests/test_team.py
git commit -m "feat(team): adiciona registro de equipe ao config e default_team()"
```
Commit é **local, sem push, nunca em `main`**.

---

## Task 2: `team.py` — leitura, `upsert`, `remove`, `list_roles` (copy-on-write)

Mesmo contrato de pureza de `providers.py`: nunca muta o `cfg` de entrada (a ponte guarda cache), ignora entradas não-dict, e aceita um config editado à mão sem explodir.

**Files:**
- Create: `thero/src/thero/team.py`
- Test: `thero/tests/test_team.py` (acrescentar)

- [ ] **Step 1: Escrever os testes que falham** — acrescentar a `thero/tests/test_team.py`

```python
from thero import team


def _cfg():
    return {"team": [
        {"id": "po", "nickname": "P.O.", "capacity": "alto",
         "provider": "claude", "model": "opus",
         "task_types": ["planning"], "enabled": True,
         "quota": {"state": "ok", "note": ""}},
    ]}


def test_find_returns_role_or_none():
    cfg = _cfg()
    assert team.find(cfg, "po")["nickname"] == "P.O."
    assert team.find(cfg, "ghost") is None


def test_upsert_adds_a_new_role_without_mutating_input():
    cfg = _cfg()
    fresh = {"id": "estagiarios", "nickname": "Estagiarios", "capacity": "local",
             "provider": "ollama", "model": "llama3.2",
             "task_types": ["simple"], "enabled": True}
    out = team.upsert(cfg, fresh)
    assert {r["id"] for r in out["team"]} == {"po", "estagiarios"}
    assert len(cfg["team"]) == 1          # entrada original intacta
    assert out["team"][1]["quota"]["state"] == "desconhecido"  # default aplicado


def test_upsert_replaces_in_place_by_id():
    out = team.upsert(_cfg(), {"id": "po", "capacity": "medio",
                               "provider": "claude", "model": "sonnet"})
    assert len(out["team"]) == 1
    assert out["team"][0]["capacity"] == "medio"


def test_remove_drops_role():
    out = team.remove(_cfg(), "po")
    assert out["team"] == []


def test_remove_unknown_raises_keyerror():
    import pytest
    with pytest.raises(KeyError):
        team.remove(_cfg(), "nao-existe")


def test_list_roles_normalizes_and_survives_garbage():
    cfg = {"team": [{"id": "po", "capacity": "alto"}, "lixo", 5, None]}
    rows = team.list_roles(cfg)
    assert len(rows) == 1
    row = rows[0]
    assert row["nickname"] == ""                 # ausente vira string vazia
    assert row["display"] == "po"                # sem provider/modelo: cai no id
    assert row["task_types"] == []
```

- [ ] **Step 2: Rodar para confirmar a falha**

Run: `python -m pytest tests/test_team.py -q`
Expected: falha — `ImportError`/`AttributeError` em `team`.

- [ ] **Step 3: Escrever `thero/src/thero/team.py`** (parte de registro)

```python
"""Registro de equipe do Zeus: papéis nomeados -> provedor+modelo+capacidade.

Puro e offline: nenhuma chamada de rede, nenhum print(). A unica fonte de
"esta instalado?" chega injetada (`status` de localmodels.status). Cota de
nuvem nao e telemetria -- e anotada pelo usuario em role["quota"]["state"].
Nunca le nem ecoa o valor de uma chave; só o NOME (authVar) aparece, e aqui
nem isso: só provider/model/apelido.

Convenção da ponte: qualquer texto que sai por JSON é ASCII sem acento.
"""

from __future__ import annotations

from typing import Optional

CAPACITY_ORDER = ("local", "medio", "alto")
TASK_TYPES = ("simple", "standard", "planning", "decision")
# Capacidade minima que cada tipo de tarefa exige. Simples roda no local;
# planejamento/decisao pedem o mais inteligente.
TASK_MIN_CAPACITY = {
    "simple": "local",
    "standard": "medio",
    "planning": "alto",
    "decision": "alto",
}
_QUOTA_STATES = ("ok", "esgotado", "desconhecido")


def _capacity_rank(capacity: str) -> int:
    try:
        return CAPACITY_ORDER.index(capacity)
    except ValueError:
        return -1


def _team_of(cfg: dict) -> list:
    items = cfg.get("team")
    if not isinstance(items, list):
        return []
    return [r for r in items if isinstance(r, dict)]


def _string(value: object) -> str:
    return value if isinstance(value, str) else ""


def find(cfg: dict, role_id: str) -> Optional[dict]:
    for role in _team_of(cfg):
        if role.get("id") == role_id:
            return role
    return None


def _normalize(role: dict) -> dict:
    out = dict(role)
    quota = out.get("quota")
    if not isinstance(quota, dict):
        quota = {}
    state = quota.get("state")
    if state not in _QUOTA_STATES:
        state = "desconhecido"
    out["quota"] = {"state": state, "note": _string(quota.get("note"))}
    out["nickname"] = _string(out.get("nickname"))
    out["capacity"] = out.get("capacity") if out.get("capacity") in CAPACITY_ORDER else ""
    out["provider"] = _string(out.get("provider"))
    out["model"] = _string(out.get("model"))
    task_types = out.get("task_types")
    out["task_types"] = [t for t in task_types if isinstance(t, str)] \
        if isinstance(task_types, list) else []
    out["enabled"] = out.get("enabled", True) is not False
    return out


def upsert(cfg: dict, role: dict) -> dict:
    if not isinstance(role, dict):
        raise ValueError("papel precisa ser um objeto")
    rid = role.get("id")
    if not isinstance(rid, str) or not rid:
        raise ValueError("papel precisa de um id que nao seja vazio")
    out = dict(cfg)
    items = [dict(r) for r in _team_of(cfg)]
    for index, existing in enumerate(items):
        if existing.get("id") == rid:
            # Overlay SÓ das chaves presentes em `role` (cru): um update
            # parcial (ex.: so mexe a cota) nao pode apagar nickname/model/
            # task_types do papel. Normaliza uma unica vez, no fim.
            merged = dict(existing)
            merged.update({k: v for k, v in role.items() if k != "id"})
            merged["id"] = rid
            items[index] = _normalize(merged)
            break
    else:
        items.append(_normalize(role))
    out["team"] = items
    return out


def remove(cfg: dict, role_id: str) -> dict:
    if find(cfg, role_id) is None:
        raise KeyError("papel desconhecido: %s" % (role_id,))
    out = dict(cfg)
    out["team"] = [dict(r) for r in _team_of(cfg) if r.get("id") != role_id]
    return out


def display_name(role: dict) -> str:
    """Apelido quando existe; senao 'provedor/modelo' (nome explicito)."""
    nickname = _string(role.get("nickname"))
    if nickname:
        return nickname
    provider = _string(role.get("provider"))
    model = _string(role.get("model"))
    if provider and model:
        return "%s/%s" % (provider, model)
    return provider or model or _string(role.get("id"))


def list_roles(cfg: dict) -> list:
    rows = []
    for role in _team_of(cfg):
        r = _normalize(role)
        r["display"] = display_name(r)
        rows.append(r)
    return rows
```

- [ ] **Step 4: Rodar a suíte inteira**

Run: `python -m pytest -q`
Expected: `398 + 6 = 404 passed`.

- [ ] **Step 5: Commit local**

```bash
git add src/thero/team.py tests/test_team.py
git commit -m "feat(team): registro find/upsert/remove/list_roles copy-on-write"
```

---

## Task 3: `team.py` — disponibilidade (`is_local` + `provider_available`) com sonda injetada

Sem rede aqui: quem faz rede é o chamador, que injeta `status` (resultado de `localmodels.status`). Um papel local só está disponível se o **modelo** dele aparece em `status["models"]`. Um papel de nuvem está disponível se o `authState` do provedor já foi confirmado por `providers.register` (texto humano seguro, não segredo).

**Files:**
- Modify: `thero/src/thero/team.py`
- Test: `thero/tests/test_team.py` (acrescentar)

- [ ] **Step 1: Escrever os testes que falham** — acrescentar

```python
from thero import providers


def _cfg_with_providers():
    return {
        "providers": [
            {"id": "claude", "preset": "claude", "kind": "agente local",
             "authKind": "session", "authState": "sessao confirmada",
             "base": "", "model": "opus"},
            {"id": "ollama", "preset": "ollama", "kind": "local",
             "authKind": "local", "authState": "respondeu",
             "base": "http://127.0.0.1:11434", "model": "llama3.2"},
            {"id": "openai", "preset": "openai", "kind": "nuvem",
             "authKind": "apikey", "authState": "nao verificado",
             "base": "https://api.openai.com/v1", "model": "gpt-4o"},
        ],
        "team": [
            {"id": "po", "nickname": "P.O.", "capacity": "alto",
             "provider": "claude", "model": "opus",
             "task_types": ["planning"], "enabled": True,
             "quota": {"state": "ok", "note": ""}},
            {"id": "estagiarios", "nickname": "Estagiarios", "capacity": "local",
             "provider": "ollama", "model": "llama3.2",
             "task_types": ["simple"], "enabled": True,
             "quota": {"state": "ok", "note": ""}},
        ],
    }


def _status(names):
    return {"up": True, "base": "http://127.0.0.1:11434",
            "models": [{"name": n} for n in names], "error": ""}


def test_is_local_true_for_ollama_and_local_kind():
    cfg = _cfg_with_providers()
    assert team.is_local(cfg, "ollama") is True
    assert team.is_local(cfg, "claude") is False
    assert team.is_local(cfg, "nao-existe") is False


def test_provider_available_local_needs_model_installed():
    cfg = _cfg_with_providers()
    ok, _ = team.provider_available(cfg, "ollama", status=_status(["llama3.2"]))
    assert ok is True
    ok2, reason = team.provider_available(cfg, "ollama", status=_status([]))
    assert ok2 is False
    assert "llama3.2" in reason      # cita o nome do modelo, nunca segredo


def test_provider_available_session_confirmed():
    cfg = _cfg_with_providers()
    ok, _ = team.provider_available(cfg, "claude", status=None)
    assert ok is True


def test_provider_available_apikey_unverified_is_false():
    cfg = _cfg_with_providers()
    ok, reason = team.provider_available(cfg, "openai", status=None)
    assert ok is False
    assert "openai" in reason


def test_consumers_stay_a_shared_constant():
    # team nao inventa consumidores; reusa os de providers se precisar citar.
    assert providers.CONSUMERS == ("athena", "sentinel")
```

- [ ] **Step 2: Rodar para confirmar a falha**

Run: `python -m pytest tests/test_team.py -q`
Expected: falha — `AttributeError: module 'thero.team' has no attribute 'is_local'`.

- [ ] **Step 3: Implementar disponibilidade** — acrescentar a `thero/src/thero/team.py`

```python
_LOCAL_PRESET_KINDS = ("local",)


def _provider_of(cfg: dict, provider_id: str) -> dict:
    providers_list = cfg.get("providers")
    for provider in providers_list if isinstance(providers_list, list) else []:
        if isinstance(provider, dict) and provider.get("id") == provider_id:
            return provider
    return {}


def is_local(cfg: dict, provider_id: str) -> bool:
    provider = _provider_of(cfg, provider_id)
    if not provider:
        return False
    kind = _string(provider.get("kind")).lower()
    auth = _string(provider.get("authKind")).lower()
    preset = _string(provider.get("preset")).lower()
    return kind in _LOCAL_PRESET_KINDS or auth == "local" \
        or preset in ("ollama", "lmstudio")


def _installed_local_models(status: Optional[dict]) -> set:
    if not isinstance(status, dict) or not status.get("up"):
        return set()
    models = status.get("models")
    names = set()
    for item in models if isinstance(models, list) else []:
        if isinstance(item, dict):
            name = _string(item.get("name"))
            if name:
                names.add(name)
            digest = _string(item.get("model"))  # algumas versoes usam "model"
            if digest:
                names.add(digest)
    return names


def provider_available(cfg: dict, provider_id: str, *,
                       status: Optional[dict]) -> tuple:
    """(disponivel, motivo_legivel). Nunca ecoa segredo: o motivo cita
    NOME de provedor/modelo e o authState salvo (texto humano de register)."""
    provider = _provider_of(cfg, provider_id)
    if not provider:
        return (False, "provedor %s nao esta cadastrado" % (provider_id or "?",))
    if is_local(cfg, provider_id):
        names = _installed_local_models(status)
        wanted = _string(provider.get("model"))
        if not names:
            return (False, "motor local sem modelos instalados")
        if wanted and not any(n == wanted or n.startswith(wanted.split(":")[0])
                              for n in names):
            return (False, "modelo local %s nao esta instalado" % wanted)
        return (True, "modelo local respondendo")
    auth_state = _string(provider.get("authState"))
    if auth_state in ("chave presente", "sessao confirmada", "respondeu"):
        return (True, auth_state)
    return (False, "credencial de %s nao verificada" % (provider_id or "?",))
```

- [ ] **Step 4: Rodar a suíte inteira**

Run: `python -m pytest -q`
Expected: `404 + 5 = 409 passed`.

- [ ] **Step 5: Commit local**

```bash
git add src/thero/team.py tests/test_team.py
git commit -m "feat(team): disponibilidade injetavel (local/nuvem) sem telemetria"
```

---

## Task 4: `team.py` — contrato de escolha por tarefa `pick(cfg, task_type, *, status)`

Este é o coração do pedido do dono: "dado um tipo de tarefa, qual papel/modelo usar?" consumindo capacidade, disponibilidade e cota **anotada**. Regra determinística: papel `enabled`, que atenda `task_type`, não marcado `esgotado`, disponível; entre candidatos, menor capacidade suficiente primeiro (tarefa simples não gasta o modelo caro), desempate por `capacity` e depois `id`.

**Files:**
- Modify: `thero/src/thero/team.py`
- Test: `thero/tests/test_team.py` (acrescentar)

- [ ] **Step 1: Escrever os testes que falham** — acrescentar

```python
def _full_cfg():
    cfg = _cfg_with_providers()
    cfg["team"].append(
        {"id": "dev", "nickname": "Dev", "capacity": "medio",
         "provider": "claude", "model": "sonnet",
         "task_types": ["standard", "simple"], "enabled": True,
         "quota": {"state": "ok", "note": ""}})
    return cfg


def test_pick_simple_prefers_the_local_intern():
    out = team.pick(_full_cfg(), "simple", status=_status(["llama3.2"]))
    assert out["ok"] is True
    assert out["role_id"] == "estagiarios"
    assert out["label"] == "Estagiarios"
    assert out["local"] is True
    assert out["model"] == "llama3.2"


def test_pick_planning_uses_the_smartest_role():
    out = team.pick(_full_cfg(), "planning", status=_status(["llama3.2"]))
    assert out["ok"] is True
    assert out["role_id"] == "po"
    assert out["capacity"] == "alto"
    assert out["local"] is False


def test_pick_skips_a_role_marked_exhausted():
    cfg = _full_cfg()
    cfg["team"] = team.upsert(cfg, {"id": "po", "quota": {"state": "esgotado",
                                                          "note": "acabou o mes"}})["team"]
    out = team.pick(cfg, "planning", status=_status(["llama3.2"]))
    # Sem o P.O., sobe para o melhor candidato restante que atenda planning;
    # dev nao cobre planning, mas a queda degrada para nao-encontrado.
    assert out["ok"] is False
    assert "planning" in out["reason"]


def test_pick_degrades_when_local_model_missing():
    # Estagiarios nao esta instalado -> simple cai para um papel disponível.
    out = team.pick(_full_cfg(), "simple", status=_status([]))
    assert out["ok"] is True
    assert out["role_id"] == "dev"      # Dev cobre simple e esta (session) ok


def test_pick_unknown_task_type_is_not_found():
    out = team.pick(_full_cfg(), "telepatia", status=_status(["llama3.2"]))
    assert out["ok"] is False
    assert "telepatia" in out["reason"]


def test_pick_result_carries_display_and_local_for_narrative():
    out = team.pick(_full_cfg(), "simple", status=_status(["llama3.2"]))
    assert set(["role_id", "label", "model", "provider", "capacity",
                "local", "available"]) <= set(out)
```

- [ ] **Step 2: Rodar para confirmar a falha**

Run: `python -m pytest tests/test_team.py -q`
Expected: falha — `AttributeError: ... no attribute 'pick'`.

- [ ] **Step 3: Implementar `pick`** — acrescentar a `thero/src/thero/team.py`

```python
def _result(cfg: dict, role: dict, task_type: str, *, available: bool,
            reason: str, ok: bool) -> dict:
    provider_id = _string(role.get("provider"))
    return {
        "ok": ok,
        "task_type": task_type,
        "role_id": _string(role.get("id")),
        "label": display_name(role),
        "nickname": _string(role.get("nickname")),
        "model": _string(role.get("model")),
        "provider": provider_id,
        "capacity": _string(role.get("capacity")),
        "local": is_local(cfg, provider_id),
        "available": available,
        "reason": reason,
    }


def _not_found(cfg: dict, task_type: str, reason: str) -> dict:
    return {
        "ok": False, "task_type": task_type, "role_id": "", "label": "",
        "nickname": "", "model": "", "provider": "", "capacity": "",
        "local": False, "available": False, "reason": reason,
    }


def pick(cfg: dict, task_type: str, *,
         status: Optional[dict] = None) -> dict:
    """Escolhe o papel para um tipo de tarefa. Offline e deterministico:
    a unica entrada externa e `status` (dict de localmodels.status) injetado.

    Candidatos: enabled, que listam `task_type` em `task_types`, capacidade
    >= minimo do tipo, nao `esgotado` e disponivel. Ordena por capacidade
    crescente (gasta o mais barato que resolve), depois por id."""
    if task_type not in TASK_TYPES:
        return _not_found(cfg, task_type,
                          "tipo de tarefa desconhecido: %s" % (task_type,))
    min_capacity = TASK_MIN_CAPACITY[task_type]
    min_rank = _capacity_rank(min_capacity)
    candidates = []
    for role in _team_of(cfg):
        r = _normalize(role)
        if not r["enabled"]:
            continue
        if task_type not in r["task_types"]:
            continue
        if r["quota"]["state"] == "esgotado":
            continue
        if _capacity_rank(r["capacity"]) < min_rank:
            continue
        available, reason = provider_available(cfg, r["provider"], status=status)
        if not available:
            continue
        candidates.append((_capacity_rank(r["capacity"]), r["id"], r, reason))
    if not candidates:
        return _not_found(cfg, task_type,
                          "nenhum papel disponivel atende '%s'" % (task_type,))
    candidates.sort(key=lambda item: (item[0], item[1]))
    _rank, _id, role, reason = candidates[0]
    return _result(cfg, role, task_type, available=True, reason=reason, ok=True)
```

- [ ] **Step 4: Rodar a suíte inteira**

Run: `python -m pytest -q`
Expected: `409 + 6 = 415 passed`.

- [ ] **Step 5: Commit local**

```bash
git add src/thero/team.py tests/test_team.py
git commit -m "feat(team): pick por tarefa com capacidade/cota/disponibilidade"
```

---

## Task 5: `team.py` — narrativa e avisos (`format_actor` + `default_warnings`)

O `pick` já devolve `label` (apelido ou `provedor/modelo`) e `local`. Esta task entrega duas conveniências que a UI/Zeus consomem: a frase de atribuição (sem acento, ASCII, para caber na ponte) e a checagem de "default aponta para modelo local não instalado → avisar, nunca vazar silencioso".

**Files:**
- Modify: `thero/src/thero/team.py`
- Test: `thero/tests/test_team.py` (acrescentar)

- [ ] **Step 1: Escrever os testes que falham** — acrescentar

```python
def test_format_actor_uses_nickname_and_local_suffix():
    out = team.pick(_full_cfg(), "simple", status=_status(["llama3.2"]))
    assert team.format_actor(out, verb="solicitou a", action="preparar o diretorio") \
        == "Zeus solicitou a Estagiarios (local) preparar o diretorio"


def test_format_actor_falls_back_to_explicit_name_without_nickname():
    cfg = _full_cfg()
    cfg["team"] = team.upsert(cfg, {"id": "dev", "nickname": ""})["team"]
    out = team.pick(cfg, "standard", status=_status(["llama3.2"]))
    # sem apelido: mostra provider/model explicito, e nao marca (local)
    assert out["label"] == "claude/sonnet"
    line = team.format_actor(out, verb="pediu a", action="indexar")
    assert "(local)" not in line
    assert "claude/sonnet" in line


def test_default_warnings_flags_missing_local_model():
    warns = team.default_warnings(_full_cfg(), status=_status([]))
    assert any("llama3.2" in w for w in warns)


def test_default_warnings_quiet_when_installed():
    warns = team.default_warnings(_full_cfg(), status=_status(["llama3.2"]))
    assert warns == []
```

- [ ] **Step 2: Rodar para confirmar a falha**

Run: `python -m pytest tests/test_team.py -q`
Expected: falha — sem `format_actor`/`default_warnings`.

- [ ] **Step 3: Implementar** — acrescentar a `thero/src/thero/team.py`

```python
def format_actor(picked: dict, *, verb: str, actor: str = "Zeus",
                 action: str) -> str:
    """Uma linha de traco legivel, em ASCII (sem acento) para a ponte.

    '{actor} {verb} {label}[ (local)] {action}'. Sem apelido, `label` ja
    veio como 'provedor/modelo' explicito; o sufixo (local) so aparece
    quando o papel e de motor local, para o dono saber quando roda offline.
    """
    label = _string(picked.get("label")) or "..."
    suffix = " (local)" if picked.get("local") else ""
    return "%s %s %s%s %s" % (actor, verb, label, suffix, action)


def default_warnings(cfg: dict, *, status: Optional[dict]) -> list:
    """Avisos para os papeis default que apontam para modelo local ausente.

    Nao veta: e so o 'avisar e pedir um clique'. O download/instalacao do
    motor e pre-requisito de outro plano (ver Dependencias)."""
    warns = []
    for role in _team_of(cfg):
        r = _normalize(role)
        if not r["enabled"] or not r["provider"]:
            continue
        if not is_local(cfg, r["provider"]):
            continue
        available, reason = provider_available(cfg, r["provider"], status=status)
        if not available and r["model"]:
            warns.append("papel '%s' usa o modelo local '%s' (%s)"
                         % (display_name(r), r["model"], reason))
    return warns
```

- [ ] **Step 4: Rodar a suíte inteira**

Run: `python -m pytest -q`
Expected: `415 + 4 = 419 passed`.

- [ ] **Step 5: Commit local**

```bash
git add src/thero/team.py tests/test_team.py
git commit -m "feat(team): format_actor e default_warnings para a narrativa"
```

---

## Task 6: Superfície para satélite — ferramenta MCP `thero_team_pick`/`thero_team_list` + flags de CLI com JSON na stdout

Como um satélite (Zeus) pergunta ao Thero hoje: o dispatcher MCP (`mcp/server.py`) roda o **CLI** de cada ferramenta por argv (`kind=THERO` → `thero.py ...`, `capabilities.py` monta o argv). Então expor a escolha = (a) uma Capability MCP e (b) um par de flags em `thero.py` que imprimem **uma** linha JSON e retornam, no mesmo molde de antecipação de `--mcp` (`cli.py:490-494`). Isso **não** toca a ponte `--serve` (canal distinto, Task 7).

> **Colisão sabida:** a ponte em paralelo insere `--serve` "logo depois de `--mcp`" (doc da ponte, Task 8 Step 4). Por isso o Step 3 é uma **verificação de merge antes de editar**: ler o despacho atual de `cli.py` e encaixar sem duplicar.

> **`--team-pick`/`--team-list` NÃO entram em `bridge.ALLOWED_FLAGS`.** Essa whitelist é lista fechada do que a GUI pode passar via `cmd:"run"` (doc da ponte, `bridge.py:4289-4294`). Estas duas flags são o **canal de satélite/MCP** (o dispatcher MCP roda `python thero.py --team-pick` direto, como já faz com `--audit-only`), não comandos da tela "run". Ficam deliberadamente fora da whitelist; se um dia a GUI precisar chamá-las, isso é revisão separada na ponte, não aqui.

**Files:**
- Modify: `thero/src/thero/mcp/capabilities.py`
- Modify: `thero/src/thero/cli.py` (parser + despacho antecipado)
- Test: `thero/tests/test_mcp_capabilities.py` (acrescentar) e `thero/tests/test_team_cli.py` (criar)

- [ ] **Step 1: Escrever o teste da Capability MCP que falha** — acrescentar a `thero/tests/test_mcp_capabilities.py`

```python
def test_team_pick_capability_builds_thero_argv():
    cap = capabilities.get_capability("thero_team_pick")
    assert cap is not None
    assert cap.kind == capabilities.THERO
    argv = cap.build_argv({"task_type": "planning"})
    assert argv == ["--team-pick", "planning"]


def test_team_list_capability_builds_thero_argv():
    cap = capabilities.get_capability("thero_team_list")
    assert cap is not None
    assert cap.build_argv({}) == ["--team-list"]
```

- [ ] **Step 2: Escrever o teste da CLI que falha** — criar `thero/tests/test_team_cli.py`

```python
from __future__ import annotations

import json
from unittest.mock import patch

from thero import cli


def test_team_pick_flag_emits_single_json_line(tmp_path, capsys):
    with patch.object(cli, "parse_args") as mock_args:
        mock_args.return_value = _ns(team_pick="simple", team_list=False,
                                      mcp=False, serve=False, publish=False,
                                      local=False)
        cli.main(tmp_path / "thero.py")
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    payload = json.loads(out[0])
    assert payload["task_type"] == "simple"
    assert "role_id" in payload


def test_team_list_flag_emits_roles_json(tmp_path, capsys):
    with patch.object(cli, "parse_args") as mock_args:
        mock_args.return_value = _ns(team_pick=None, team_list=True,
                                      mcp=False, serve=False, publish=False,
                                      local=False)
        cli.main(tmp_path / "thero.py")
    out = capsys.readouterr().out.strip().splitlines()
    payload = json.loads(out[0])
    assert {r["id"] for r in payload["team"]} >= {"po", "dev", "estagiarios"}


def _ns(**kw):
    class _A:
        pass
    a = _A()
    for key, value in kw.items():
        setattr(a, key, value)
    return a
```

- [ ] **Step 3: Verificação de merge ANTES de editar `cli.py`** (descobrir, não chutar)

Run: `python -c "import inspect,thero.cli as c; src=inspect.getsource(c.main); print('serve' in src, 'team' in src)"`
Expected: duas flags booleanas. Se `'serve' is True`, a ponte já landed: insira as flags de time **depois** do bloco `args.serve` (que também retorna cedo) para não reordenar o trabalho alheio; se `False`, insira **logo após** o bloco `args.mcp`. Registre o estado no commit.

- [ ] **Step 4: Registrar as duas Capabilities** — editar `thero/src/thero/mcp/capabilities.py`, acrescentar ao `_CAPABILITIES` (após `thero_audit`):

```python
def _argv_team_pick(arguments: dict[str, Any]) -> list[str]:
    task_type = arguments.get("task_type")
    if not task_type:
        raise ValueError("task_type e obrigatorio")
    return ["--team-pick", str(task_type)]


def _argv_team_list(arguments: dict[str, Any]) -> list[str]:
    return ["--team-list"]
```

e as duas entradas na lista:

```python
    Capability(
        name="thero_team_list",
        title="Thero: listar a equipe",
        description=(
            "Lista os papeis/equipes nomeados registrados (apelido, "
            "provedor+modelo, capacidade, cota anotada). Somente leitura."
        ),
        kind=THERO,
        input_schema={"type": "object", "properties": {}},
        build_argv=_argv_team_list,
    ),
    Capability(
        name="thero_team_pick",
        title="Thero: escolher papel para uma tarefa",
        description=(
            "Dado um tipo de tarefa (simple/standard/planning/decision), "
            "devolve qual papel/modelo usar conforme capacidade, "
            "disponibilidade e cota anotada, com apelido para o traco."
        ),
        kind=THERO,
        input_schema={
            "type": "object",
            "properties": {
                "task_type": {
                    "type": "string",
                    "enum": ["simple", "standard", "planning", "decision"],
                    "description": "Categoria da tarefa a rotear.",
                },
            },
            "required": ["task_type"],
        },
        build_argv=_argv_team_pick,
    ),
```

- [ ] **Step 5: Adicionar as flags ao parser** — em `thero/src/thero/cli.py`, após o bloco `--mcp` (parser, ~linha 446):

```python
    parser.add_argument(
        "--team-list",
        action="store_true",
        help="Imprime os papeis da equipe como uma linha JSON (canal de satellite).",
    )
    parser.add_argument(
        "--team-pick",
        metavar="TIPO",
        default=None,
        help=(
            "Dado um tipo de tarefa (simple/standard/planning/decision), "
            "imprime a escolha de papel/modelo como uma linha JSON e sai. "
            "Usado por satelites (Zeus) e pela ferramenta MCP thero_team_pick."
        ),
    )
```

- [ ] **Step 6: Despacho antecipado (JSON na stdout, antes do banner)** — logo após o bloco `if args.mcp: ... return` (ou `if args.serve:` se já landed, ver Step 3):

```python
    # Canal de satelite: UMA linha JSON na stdout e sai. Nada de banner
    # antes disto (mesma disciplina de --mcp/--serve: stdout e o canal).
    if getattr(args, "team_pick", None) or getattr(args, "team_list", False):
        import json

        from thero import config as _config
        from thero import localmodels, team

        cfg = _config.load()
        base = ""
        for provider in cfg.get("providers", []):
            if isinstance(provider, dict) and (
                provider.get("preset") == "ollama" or provider.get("id") == "ollama"
            ):
                base = provider.get("base", "")
                break
        try:
            status = localmodels.status(base)
        except ValueError:
            # base fora de loopback: sem motor local, nada instalavel.
            status = {"up": False, "models": [], "base": "", "error": "loopback"}
        if getattr(args, "team_list", False):
            payload = {"team": team.list_roles(cfg)}
        else:
            payload = team.pick(cfg, args.team_pick, status=status)
        print(json.dumps(payload, ensure_ascii=True))
        return
```

> `ensure_ascii=True` aqui é deliberado: o stdout pode ser lido por um processo sem UTF-8 garantido no caminho do satélite (diferente do canal MCP UTF-8). Os `label`s de default são ASCII ("P.O.", "Dev", "Estagiarios").

- [ ] **Step 7: Rodar a suíte inteira**

Run: `python -m pytest -q`
Expected: `419 + 4 = 423 passed`.

- [ ] **Step 8: Smoke manual offline (não obrigatório, documenta o contrato)**

Run: `python thero.py --team-pick planning`
Expected: uma linha JSON contendo `"ok"`, `"label":"P.O."`, `"local":false`.
Run: `python thero.py --team-list`
Expected: uma linha JSON com a lista dos três papeis.

- [ ] **Step 9: Commit local**

```bash
git add src/thero/mcp/capabilities.py src/thero/cli.py \
        tests/test_mcp_capabilities.py tests/test_team_cli.py
git commit -m "feat(team): MCP thero_team_pick/list + flags JSON na CLI"
```

---

## Task 7 (condicional): comandos `team-*` na ponte GUI↔motor

Só existe depois que `src/thero/bridge.py` estiver no tree (está sendo escrito em paralelo na Task 7-8 da ponte). Esta task **não** roda se o arquivo ainda não existir — o executor verifica primeiro.

**Files:**
- Modify: `thero/src/thero/bridge.py` (se existir)
- Test: `thero/tests/test_bridge_team.py` (só se a ponte existir)

- [ ] **Step 1: Verificar a dependência**

Run: `python -c "import importlib.util as u; print(bool(u.find_spec('thero.bridge')))"`
Expected: `True` → seguir; `False` → **pular esta task** (deixar como pendência da ponte; os satélites já funcionam via MCP/CLI da Task 6). Não criar `bridge.py` aqui.

- [ ] **Step 2: Escrever o teste que falha** — criar `thero/tests/test_bridge_team.py`

```python
from __future__ import annotations

from thero import bridge


def _state(tmp_path):
    return bridge.BridgeState(entry_path=tmp_path / "thero.py",
                              config_path=tmp_path / "config.json")


def test_team_list_returns_roles(tmp_path):
    st = _state(tmp_path)
    resp = bridge.handle_request({"id": 1, "cmd": "team-list"}, st)
    assert resp["result"]["team"]


def test_team_pick_answers_task_type(tmp_path):
    st = _state(tmp_path)
    resp = bridge.handle_request(
        {"id": 2, "cmd": "team-pick", "task_type": "simple"}, st)
    assert resp["result"]["task_type"] == "simple"


def test_team_upsert_and_remove(tmp_path):
    st = _state(tmp_path)
    resp = bridge.handle_request(
        {"id": 3, "cmd": "team-upsert", "role": {"id": "qa", "nickname": "QA",
         "capacity": "medio", "provider": "claude", "model": "sonnet",
         "task_types": ["standard"]}}, st)
    ids = {r["id"] for r in resp["result"]["config"]["team"]}
    assert "qa" in ids
```

- [ ] **Step 3: Implementar o handler da família** — em `thero/src/thero/bridge.py`, junto às outras famílias (usar os nomes `_ok`/`_err`/`state.load`/`state.persist` **exatamente** como a ponte já define):

```python
def _handle_team(state, request: dict):
    from thero import team
    cmd = request["cmd"]
    cfg = state.load()
    if cmd == "team-list":
        return _ok(request["id"], {"team": team.list_roles(cfg)})
    if cmd == "team-pick":
        task_type = request.get("task_type", "")
        base = ""
        for provider in cfg.get("providers", []):
            if isinstance(provider, dict) and (
                provider.get("preset") == "ollama" or provider.get("id") == "ollama"):
                base = provider.get("base", "")
                break
        try:
            status = localmodels.status(base)
        except ValueError:
            status = {"up": False, "models": []}
        return _ok(request["id"], team.pick(cfg, task_type, status=status))
    if cmd == "team-upsert":
        role = request.get("role")
        if not isinstance(role, dict) or not role.get("id"):
            return _err(request["id"], "papel incompleto")
        out = team.upsert(cfg, role)
        state.persist(out)
        return _ok(request["id"], {"config": out})
    if cmd == "team-remove":
        try:
            out = team.remove(cfg, request.get("id", ""))
        except KeyError as exc:
            return _err(request["id"], str(exc))
        state.persist(out)
        return _ok(request["id"], {"config": out})
    return None
```

- [ ] **Step 4: Registrar os comandos e o despacho**

Na tupla `COMMANDS` da ponte acrescentar: `"team-list", "team-pick", "team-upsert", "team-remove"`. No `handle_request`, incluir `_handle_team` na iteração das famílias de handlers (junto a `_handle_config, _handle_providers, _handle_agents`).

- [ ] **Step 5: Rodar** (só se a ponte existir)

Run: `python -m pytest tests/test_bridge_team.py -q`
Expected: `3 passed`.

- [ ] **Step 6: Commit local**

```bash
git add src/thero/bridge.py tests/test_bridge_team.py
git commit -m "feat(team): comandos team-* na ponte GUI-motor (pos-merge da ponte)"
```

---

## Pré-requisito referenciado (NÃO implementar aqui)

Instalação do motor local (Ollama) e `ollama pull` dos modelos default durante o onboarding moram num **plano próprio a ser escrito depois** (a suíte já tem `localmodels.pull`/`status` e o veto de loopback). Este plano só **consome** `localmodels.status` (injetável) e **avisa** quando um default aponta para modelo ausente (`team.default_warnings`), nunca veta — acomoda com "avisar e pedir um clique". Dependência declarada: `plan: onboarding-motor-local` (inexistente ainda).

---

## Auto-revisão

**1. Cobertura do prescrito:** dicionário de papéis no config com round-trip (Task 1, e a chave de topo sobrevive a `config.load`/`save` sem mexer em merge); defaults derivados dos seeds instalados + validados contra `localmodels.status` (Task 1 seeds, Task 5 `default_warnings`); contrato de escolha por tarefa consumindo capacidade/cota/disponibilidade (Task 4 `pick`); narrativa com apelido→fallback explícito→sufixo `(local)` (Task 5 `format_actor`, campos `label`/`local` do `pick`); satélite pergunta via MCP + CLI (Task 6) e ponte condicional (Task 7); motor local como dependência referenciada, não implementada. Decisões fixas do dono respeitadas: escrita em terceiros fica em `apply.py` (nada aqui escreve `~/.claude/...`); backups nunca tocados/versionados; cota sem telemetria paga (só `authState` verificável + `quota.state` anotado); nada de segredo ecoado (só nomes).

**2. Placeholders:** nenhum "TODO"/"similar à Task N". Onde havia incerteza real (ponte em paralelo, `cli.py` já ter `--serve`), virou **task de verificação** com comando e branch explícitos (Task 6 Step 3, Task 7 Step 1), não buraco.

**3. Consistência de tipos/nomes entre tasks:** `pick` devolve `{ok,task_type,role_id,label,nickname,model,provider,capacity,local,available,reason}` — `format_actor` lê `label`/`local`, os testes da Task 4/5/6 conferem essas chaves. `TASK_TYPES`/`TASK_MIN_CAPACITY`/`CAPACITY_ORDER` definidos na Task 4 usados nas Tasks 4-6. `is_local`/`provider_available`/`display_name` definidos nas Tasks 3 e 2, consumidos em 4/5. Flags `--team-pick`/`--team-list` da CLI batem com o `build_argv` da MCP. Teste de `providers.CONSUMERS` mantém a âncora compartilhada explícita.

**Contagem acumulada:** 394 → 398 → 404 → 409 → 415 → 419 → 423 (+ponte condicional 426 se `bridge.py` existir).

## Perguntas ao dono (com recomendação conservadora aplicada no plano)

1. **Forma da cota.** Adotei cota anotada `quota.state ∈ {ok, esgotado, desconhecido}` + `note`, sem nenhum número de token/dólar inferido. Recomendação: manter anotado; se ele quiser um *orçamento* (ex.: `usd_used`/`usd_limit`), é campo extra em `quota`, leitura local, continua sem telemetria. Aplicado: `desconhecido` nunca bloqueia (só `esgotado` tira da corrida).

2. **Apelidos default.** Semeie "P.O." (alto), "Dev" (médio), "Estagiarios" (local), casando os exemplos citados. Recomendação: confirmar se "Dev" médio deve existir ou se prefere só o par P.O./Estagiarios. Aplicado: três papéis, todos editáveis por `team-upsert`.

3. **Acentos nos apelidos.** Escrevi "Estagiarios" sem acento e `ensure_ascii=True` na stdout do canal satélite, porque texto via JSON/ponte é ASCII por convenção do repo. Recomendação: apelidos ficam ASCII; se o dono quiser "Estagiários" acentuado no `config.json`, o campo aceita acento (round-trip provado), mas a linha de satélite precisará ser UTF-8. Aplicado: ASCII no default.

4. **"Tarefa simples → local" com o local ausente.** Fiz `pick` **degradar** para o próximo papel disponível (Dev/session) em vez de falhar, mais `default_warnings`. Recomendação: degradação + aviso > falha seca. Aplicado: degrada.

5. **Ordem de escolha de capacidade.** Escolhi "menor capacidade suficiente primeiro" para não gastar o modelo caro em tarefa simples. Recomendação: manter; se o dono quiser sempre o papel nomeado específico (não o tier), é trocar o sort por um mapa `task_type → role_id` fixo. Aplicado: tier.

6. **Integração com a ponte.** Deixei `team-*` na GUI como Task 7 **condicional** ao merge da ponte em curso. Recomendação: não escrever `bridge.py` agora (o outro agente é o dono). Aplicado: verificação + skip.
