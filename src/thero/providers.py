"""Registro de provedores de IA na interface.

Regra que importa: o Thero guarda o NOME da variavel que contem a chave
(`authVar`), nunca o valor. Nenhuma funcao daqui le `os.environ[name]` para
devolver em mensagem, log ou erro -- no maximo informa se a variavel existe.
"""

from __future__ import annotations

import os
from typing import Optional

from thero import localmodels, presets


class ProtectedProvider(Exception):
    """Instalada pelo Thero: nao se desinstala pela interface."""


class ProviderInUse(Exception):
    """Alguma ferramenta (Athena/Sentinel) ainda aponta para ele."""


CONSUMERS = ("athena", "sentinel")


def find(cfg: dict, pid: str) -> Optional[dict]:
    return next((p for p in cfg.get("providers", []) if p.get("id") == pid),
                None)


def upsert(cfg: dict, provider: dict) -> dict:
    """Troca no lugar se ja existe; acrescenta no fim se e novo."""
    out = dict(cfg)
    items = [dict(p) for p in out.get("providers", [])]
    for index, existing in enumerate(items):
        if existing.get("id") == provider.get("id"):
            items[index] = dict(provider)
            break
    else:
        items.append(dict(provider))
    out["providers"] = items
    return out


def remove(cfg: dict, pid: str) -> dict:
    existing = find(cfg, pid)
    if existing is None:
        raise KeyError("provedor desconhecido: %s" % pid)
    if existing.get("origin") == "thero":
        raise ProtectedProvider(
            "%s foi instalado pelo Thero e nao pode ser removido daqui" % pid)
    routing = cfg.get("routing") or {}
    roles = existing.get("roles") or {}
    for consumer in CONSUMERS:
        if roles.get(consumer):
            raise ProviderInUse(
                "%s ainda e o provedor de %s mude a rota antes" % (pid, consumer))
    if routing.get("fallback") == existing.get("label"):
        raise ProviderInUse(
            "%s e o fallback do roteador mude a rota antes" % pid)
    # Um slot de rota guarda o NOME DO MODELO (models-set), e a Task 5 grava
    # esse nome em ATHENA_OLLAMA_MODEL / SENTINEL_OLLAMA_MODEL. Se o modelo
    # pertence a este provedor, apaga-lo deixaria a variavel pendurada.
    offered = {existing.get("model") or ""}
    offered.update(existing.get("models") or [])
    offered.discard("")
    for consumer in CONSUMERS:
        model = routing.get(consumer) or ""
        if model and model in offered:
            raise ProviderInUse(
                "%s fornece %s, que ainda e o modelo de %s mude a rota antes"
                % (pid, model, consumer))
    out = dict(cfg)
    out["providers"] = [p for p in out["providers"] if p.get("id") != pid]
    return out


def _probe_loopback(base: str) -> dict:
    """Una sonda: `list_models` ja faz o veto de loopback e o pedido HTTP.

    Nao ha segunda verificacao "de seguranca" depois daqui -- o veto acontece
    dentro de `list_models`, antes de qualquer rede, e os testes da Task 3
    provem isso. Rodar as duas coisas era sondar a rede duas vezes por clique.

    DEVOLVE UM DICT. `if _probe_loopback(base):` e sempre verdade -- um
    `{"ok": False}` dict e truthy e a tela diria "endpoint respondeu" com o
    Ollama caido. Por isso o `register` abaixo consulta `["ok"]`, nao o dict.
    """
    return localmodels.list_models(base)


def register(provider: dict) -> dict:
    """Confirma o provedor do jeito que o tipo dele permite.

    - session: a sessao e do proprio produto; o Thero nao autentica por ele.
    - apikey:  existe a variavel nomeada? (o valor nunca aparece)
    - local:   o endpoint loopback responde?
    """
    kind = provider.get("authKind") or "apikey"
    if kind == "session":
        return {"ok": True, "authState": "sessao confirmada",
                "msg": "sessao confirmada no produto - provedor registrado"}
    if kind == "local":
        base = provider.get("base", "")
        if not base:
            return {"ok": False, "authState": "incompleto",
                    "msg": "informe o endpoint local antes de registrar"}
        try:
            url_base = localmodels.guard_base(base)
        except ValueError as exc:
            return {"ok": False, "authState": "bloqueado",
                    "msg": "modelos locais so por loopback: %s" % exc}
        # `["ok"]`, nunca o dict: `{"ok": False}` e truthy, e o registro sairia
        # confirmado com o Ollama caido.
        probe = _probe_loopback(url_base)
        if probe["ok"]:
            return {"ok": True, "authState": "respondeu",
                    "msg": "endpoint local respondeu - provedor registrado"}
        return {"ok": False, "authState": "sem resposta",
                "msg": "registrado, mas o endpoint nao respondeu agora"}
    var = (provider.get("authVar") or "").strip()
    if not var:
        return {"ok": False, "authState": "incompleto",
                "msg": "defina o nome da variavel que guarda a chave"}
    if var not in os.environ:
        return {"ok": False, "authState": "aguardando chave",
                "msg": "variavel %s ainda nao definida" % var}
    return {"ok": True, "authState": "chave presente",
            "msg": "provedor registrado - chave lida de %s a cada chamada" % var}


def test_endpoint(provider: dict) -> dict:
    base = provider.get("base", "")
    if not base:
        return {"ok": False, "msg": "sem endpoint para testar: preencha o campo"}
    kind = provider.get("authKind") or "apikey"
    if kind == "local":
        out = localmodels.list_models(base)
        if out["ok"]:
            return {"ok": True,
                    "msg": "%s respondeu com %d modelo(s)"
                           % (base, len(out["models"]))}
        return {"ok": False, "msg": out["error"]}
    return {"ok": True,
            "msg": "endpoint anotado (%s) - o Thero nao faz chamada autenticada "
                   "por aqui" % base}


def summary(cfg: dict) -> list:
    rows = []
    for provider in cfg.get("providers", []):
        used_by = [c for c in CONSUMERS
                   if (provider.get("roles") or {}).get(c)]
        # Um provedor editado pela interface pode chegar sem `kind` (o payload
        # do formulario nao o traz): cai no tipo do preset, senao a coluna
        # "tipo" da tela fica vazia para toda entrada do usuario.
        kind = provider.get("kind") or (
            presets.provider_preset(provider.get("preset", "")) or {}
        ).get("kind", "")
        rows.append({
            "id": provider.get("id"),
            "label": provider.get("label"),
            "kind": kind,
            "base": provider.get("base", ""),
            "model": provider.get("model", ""),
            "authKind": provider.get("authKind", ""),
            "authVar": provider.get("authVar", ""),
            "authState": provider.get("authState", ""),
            "enabled": bool(provider.get("enabled", True)),
            "origin": provider.get("origin", "user"),
            "usedBy": used_by,
            "preset": provider.get("preset", ""),
        })
    return rows


def blank_from_preset(pid: str, label: str = "") -> dict:
    """Entrada nova do usuario a partir de um preset (tudo editavel)."""
    pre = presets.provider_preset(pid) or {}
    new_id = pid
    auth_kind = pre.get("authKind", "apikey")
    return {
        "id": new_id,
        "label": label or pre.get("name", pid),
        "preset": pid,
        "kind": pre.get("kind", ""),
        "base": pre.get("base", ""),
        "transport": pre.get("transport", ""),
        "authKind": auth_kind,
        "authVar": ("THERO_%s_API_KEY" % new_id.upper())
                   if auth_kind == "apikey" else "",
        "model": (pre.get("models") or [""])[0],
        "models": list(pre.get("models", [])),
        "enabled": True,
        "origin": "user",
        "roles": {"athena": False, "sentinel": False},
        "authState": "nao verificado",
        "lastCheck": "",
    }
