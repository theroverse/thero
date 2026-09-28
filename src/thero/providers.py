"""Registro de provedores de IA na interface.

Regra que importa: o Thero guarda o NOME da variavel que contem a chave
(`authVar`), nunca o valor. Nenhuma funcao daqui le `os.environ[name]` para
devolver em mensagem, log ou erro -- no maximo informa se a variavel existe.
E o texto que chegar em `authVar` ou `base` nunca volta cru numa mensagem
montada por este modulo: nome de variavel fora da forma legitima (chave
colada no campo errado) sai em texto fixo, e a base so aparece redigida,
sem o userinfo da URL. (O `summary` redevolve os campos salvos da config
crua porque e o round-trip do formulario, nao uma mensagem dele.)
"""

from __future__ import annotations

import os
import re
from typing import Optional

from thero import localmodels, presets


class ProtectedProvider(Exception):
    """Instalada pelo Thero: nao se desinstala pela interface."""


class ProviderInUse(Exception):
    """Alguma ferramenta (Athena/Sentinel) ainda aponta para ele."""


CONSUMERS = ("athena", "sentinel")

# Forma de um NOME de variavel de ambiente (POSIX, teto de 128 chars): e o
# unico texto de `authVar` que pode aparecer numa mensagem montada aqui.
# Qualquer nome com hifen, ponto ou "$" no meio e provavel valor de chave
# colado no campo errado -- fica barrado, e o texto recebido nao e ecoado.
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")


# Formas de autenticacao aceitas; qualquer outra caixa/espaco e normalizada
# para ca antes de escolher o ramo (um "Local " no ramo apikey escaparia do
# veto de loopback).
AUTH_KINDS = ("session", "local", "apikey")


def _auth_kind(provider: dict) -> str:
    return str(provider.get("authKind") or "apikey").strip().lower()


def _providers_of(cfg: dict) -> list:
    """So as entradas-dict de `providers`, o que quer que o arquivo traga.

    `config.load()` exige apenas que o topo seja dict: um config.json
    editado a mao com `providers: None`, `routing: "zeus"` ou um "abc" na
    lista nao pode derrubar a tela a cada abertura (e o cache `_cfg` da
    ponte repetiria a queda ate reiniciar).
    """
    items = cfg.get("providers")
    if not isinstance(items, list):
        return []
    return [p for p in items if isinstance(p, dict)]


def _mapping_field(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def find(cfg: dict, pid: str) -> Optional[dict]:
    for provider in _providers_of(cfg):
        if provider.get("id") == pid:
            return provider
    return None


def upsert(cfg: dict, provider: dict) -> dict:
    """Troca no lugar se ja existe; acrescenta no fim se e novo.

    Rename: se o `routing.fallback` guardava exatamente o label antigo,
    ele passa a guardar o novo -- senao o roteador ficaria apontando para
    um nome que nao existe mais e a Task 5 exportaria o nome errado. Quando
    o fallback guarda o id, nao se mexe: o id nao mudou. O cfg de entrada
    nunca e mutado (a ponte o mantem em cache).
    """
    if not isinstance(provider, dict):
        raise ValueError("provedor precisa ser um objeto")
    pid = provider.get("id")
    if not isinstance(pid, str) or not pid:
        # Sem isso, `id` None casa com outra entrada sem id e engole ela.
        raise ValueError("provedor precisa de um id que nao seja vazio")
    out = dict(cfg)
    items = [dict(p) for p in _providers_of(cfg)]
    for index, existing in enumerate(items):
        if existing.get("id") == pid:
            old_label = existing.get("label") or ""
            new_label = provider.get("label") or ""
            items[index] = dict(provider)
            routing = _mapping_field(out.get("routing"))
            if (routing and routing.get("fallback") == old_label
                    and old_label and new_label != old_label):
                out["routing"] = dict(routing, fallback=new_label)
            break
    else:
        items.append(dict(provider))
    out["providers"] = items
    return out


def remove(cfg: dict, pid: str) -> dict:
    if not isinstance(pid, str) or not pid:
        # O handler da Task 8 le request.get("id", ""); "" nao e um alvo,
        # e o find casaria com a entrada degenerada de id vazio.
        raise KeyError("provedor desconhecido")
    existing = find(cfg, pid)
    if existing is None:
        raise KeyError("provedor desconhecido: %s" % pid)
    if existing.get("origin") == "thero":
        raise ProtectedProvider(
            "%s foi instalado pelo Thero e nao pode ser removido daqui" % pid)
    routing = _mapping_field(cfg.get("routing"))
    roles = _mapping_field(existing.get("roles"))
    for consumer in CONSUMERS:
        if roles.get(consumer):
            raise ProviderInUse("%s ainda e o provedor de %s "
                                "mude a rota antes" % (pid, consumer))
    # `cfg["agents"][*]["provider"]` guarda o ID do provedor: sem este veto,
    # apaga-lo deixaria o agent sem modelo e a Task 5 culparia o roteador.
    agents = cfg.get("agents")
    for agent in agents if isinstance(agents, list) else []:
        if not isinstance(agent, dict):
            continue
        if agent.get("provider") == pid:
            name = agent.get("label") or agent.get("id") or "sem nome"
            raise ProviderInUse(
                "o agent %s ainda aponta para %s mude a rota antes"
                % (name, pid))
    # `None == None` nao pode virar veto: sem fallback nao ha rota a perder.
    # O fallback do roteador aceita o label OU o id do provedor.
    label = existing.get("label") or ""
    fallback = routing.get("fallback") or ""
    if fallback and fallback in (label, existing.get("id") or ""):
        raise ProviderInUse(
            "%s e o fallback do roteador mude a rota antes" % pid)
    # Um slot de rota guarda o NOME DO MODELO (models-set), e a Task 5 grava
    # esse nome em ATHENA_OLLAMA_MODEL / SENTINEL_OLLAMA_MODEL: apagar o unico
    # dono deixaria a variavel pendurada. O primario deste provedor segura
    # sempre; um nome que so aparece em `models` segura apenas enquanto
    # nenhum sobrevivente o tem como primario -- senao um preset copiado
    # ficaria apagavel so depois de mexer na rota.
    held = set()
    primary = existing.get("model")
    if isinstance(primary, str) and primary:
        held.add(primary)
    listed = existing.get("models")
    if isinstance(listed, list):  # string iteraria letra a letra
        owners = {p.get("model") for p in _providers_of(cfg)
                  if p.get("id") != pid and isinstance(p.get("model"), str)}
        for name in listed:
            if isinstance(name, str) and name and name not in owners:
                held.add(name)
    for consumer in CONSUMERS:
        model = routing.get(consumer) or ""
        if isinstance(model, str) and model and model in held:
            raise ProviderInUse(
                "%s fornece %s, que ainda e o modelo de %s mude a rota antes"
                % (pid, model, consumer))
    # Copias, como no upsert: a ponte guarda o cfg em cache, e devolver os
    # mesmos objetos deixaria uma resposta ja entregue mudar por dentro.
    out = dict(cfg)
    out["providers"] = [dict(p) for p in _providers_of(cfg)
                        if p.get("id") != pid]
    return out


def register(provider: dict) -> dict:
    """Confirma o provedor do jeito que o tipo dele permite.

    - session: a sessao e do proprio produto; o Thero nao autentica por ele.
    - apikey:  existe a variavel nomeada? (o valor nunca aparece)
    - local:   o endpoint loopback responde?

    authKind fora da taxonomia devolve "tipo desconhecido" (com o proprio
    texto normalizado) em vez de cair no ramo apikey de raso.
    """
    kind = _auth_kind(provider)
    if kind not in AUTH_KINDS:
        return {"ok": False, "authState": "tipo desconhecido",
                "msg": "tipo de autenticacao desconhecido: %s" % kind}
    if kind == "session":
        return {"ok": True, "authState": "sessao confirmada",
                "msg": "sessao confirmada no produto - provedor registrado"}
    if kind == "local":
        base = provider.get("base", "")
        if not base:
            return {"ok": False, "authState": "incompleto",
                    "msg": "informe o endpoint local antes de registrar"}
        # A sonda de modelos e da API do Ollama (/api/tags, na raiz). Uma
        # base com caminho e outra coisa (LM Studio em /v1): o veto de HOST
        # loopback continua valendo para todas, e a sonda nao roda contra
        # uma URL que ela nao entende. Decisao do dono, 2026-09-28.
        probeable = not localmodels.has_endpoint_path(base)
        guard = localmodels.guard_base if probeable else localmodels.guard_host
        try:
            url_base = guard(base)
        except ValueError as exc:
            # O texto da excecao cita a base crua (recebi %r): mesma redacao
            # de _redact usada em test_endpoint, sem duplicar a regex.
            return {"ok": False, "authState": "bloqueado",
                    "msg": "modelos locais so por loopback: %s"
                           % _redact(exc)}
        if not probeable:
            return {"ok": True, "authState": "sem sonda",
                    "msg": "endpoint local sem a API do Ollama: registrado, "
                           "sabemos que ele existe, nao sabemos listar os "
                           "modelos dele"}
        # Uma sonda de rede so: o veto ja vive dentro de `list_models`, e o
        # `guard_base` acima apenas repete o veto (sem rede) para dar o
        # motivo humano. Consulta `["ok"]`, nunca o dict: `{"ok": False}` e
        # truthy, e o registro sairia confirmado com o Ollama caido.
        probe = localmodels.list_models(url_base)
        if probe["ok"]:
            return {"ok": True, "authState": "respondeu",
                    "msg": "endpoint local respondeu - provedor registrado"}
        return {"ok": False, "authState": "sem resposta",
                "msg": "registrado, mas o endpoint nao respondeu agora"}
    var = str(provider.get("authVar") or "").strip()
    if not var:
        return {"ok": False, "authState": "incompleto",
                "msg": "defina o nome da variavel que guarda a chave"}
    if _ENV_NAME.match(var) is None:
        # Mensagem fixa: o texto recebido pode SER a chave, e o handler da
        # Task 8 grava este msg em provider["lastCheck"]. Nao ecoar nada.
        return {"ok": False, "authState": "nome invalido",
                "msg": "informe o NOME da variavel "
                       "(ex.: THERO_OPENAI_API_KEY), nunca o valor da chave"}
    if var not in os.environ:
        return {"ok": False, "authState": "aguardando chave",
                "msg": "variavel %s ainda nao definida" % var}
    return {"ok": True, "authState": "chave presente",
            "msg": "provedor registrado - chave lida de %s "
                   "a cada chamada" % var}


def redact(value: object) -> str:
    """Versao publica da redacao de credencial (A3, Task 5).

    apply.py precisa redigir a mesma base antes de devolver um motivo de
    recusa de loopback; expor daqui evita copiar a regex para outro modulo
    (duas fontes divergiriam e uma delas vazaria a credencial).
    """
    return _redact(value)


def _redact(base: str) -> str:
    """Corta o userinfo (ate o "@" do "://user:pass@host") antes do echo.

    Uma base colada na tela pode carregar a chave embutida como credencial
    de proxy; o msg volta para a interface e pode ser persistido.
    """
    return re.sub(r"://[^/@]*@", "://", str(base))


def test_endpoint(provider: dict) -> dict:
    """Sonda o endpoint do jeito que o tipo dele permite, sem estourar.

    Todo caminho devolve texto humano: o ValueError do veto de loopback
    e capturado igual no `register`, e nenhuma mensagem ecoa a base crua
    (sempre a versao redigida) nem o erro cru do `localmodels`.
    """
    base = provider.get("base", "")
    if not base:
        return {"ok": False,
                "msg": "sem endpoint para testar: preencha o campo"}
    kind = _auth_kind(provider)
    safe = _redact(base)
    if kind == "local":
        if not localmodels.has_endpoint_path(base):
            try:
                url_base = localmodels.guard_base(base)
            except ValueError:
                return {"ok": False,
                        "msg": "modelos locais so por loopback: %s" % safe}
            out = localmodels.list_models(url_base)
            if out["ok"]:
                return {"ok": True,
                        "msg": "%s respondeu com %d modelo(s)"
                               % (safe, len(out["models"]))}
            return {"ok": False, "msg": _redact(out["error"])}
        # Base com caminho nao e a API do Ollama: nao temos sonda para ela,
        # e dizer "respondeu" seria uma verificacao inventada. O registro
        # aconteceu (`register` anotou "sem sonda"); aqui so diz isso.
        return {"ok": False,
                "msg": "sem teste disponivel: o Thero so sabe sondar a API "
                       "do Ollama, e %s nao e ela" % safe}
    return {"ok": True,
            "msg": "endpoint anotado (%s) - o Thero nao faz chamada "
                   "autenticada por aqui" % safe}


def summary(cfg: dict) -> list:
    rows = []
    for provider in _providers_of(cfg):
        raw_roles = provider.get("roles")
        roles = _mapping_field(raw_roles)
        used_by = [c for c in CONSUMERS if roles.get(c)]
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
            "transport": provider.get("transport", ""),
            "model": provider.get("model", ""),
            "models": provider.get("models", []),
            "authKind": provider.get("authKind", ""),
            "authVar": provider.get("authVar", ""),
            "authState": provider.get("authState", ""),
            # `is not False`, nao bool(): "enabled": null editado a mao e
            # True para a tela (`p.enabled !== false`) e nao pode virar
            # False no engine.
            "enabled": provider.get("enabled", True) is not False,
            "origin": provider.get("origin", "user"),
            "roles": {"athena": bool(roles.get("athena")),
                      "sentinel": bool(roles.get("sentinel"))},
            "usedBy": used_by,
            "preset": provider.get("preset", ""),
            "lastCheck": provider.get("lastCheck", ""),
        })
    return rows


def _unique_id(pid: str, taken) -> str:
    """Primeiro id livre contra os em uso: pid, pid-2, pid-3, ..."""
    used = set(taken)
    if pid not in used:
        return pid
    n = 2
    while "%s-%d" % (pid, n) in used:
        n += 1
    return "%s-%d" % (pid, n)


def blank_from_preset(pid: str, label: str = "", taken=()) -> dict:
    """Entrada nova do usuario a partir de um preset (tudo editavel).

    `taken` sao os ids ja presentes no cfg: o id novo nunca colide com
    eles -- sem isso, "adicionar" pelo preset `ollama` sobrescrevia o seed
    instalado pelo Thero (perdia `origin: "thero"` e zerava os `roles`,
    derrubando a rota da Athena). O `preset` continua sendo o pid
    informado; o `authVar` sai sanitizado como nome de variavel valido
    (bate o _ENV_NAME), nunca com hifen.
    """
    pid = str(pid or "custom")
    pre = presets.provider_preset(pid) or {}
    new_id = _unique_id(pid, taken)
    auth_kind = pre.get("authKind", "apikey")
    auth_var = ""
    if auth_kind == "apikey":
        auth_var = "THERO_%s_API_KEY" % re.sub(
            r"[^A-Za-z0-9]", "_", new_id).upper()
    return {
        "id": new_id,
        "label": label or pre.get("name", pid),
        "preset": pid,
        "kind": pre.get("kind", ""),
        "base": pre.get("base", ""),
        "transport": pre.get("transport", ""),
        "authKind": auth_kind,
        "authVar": auth_var,
        "model": (pre.get("models") or [""])[0],
        "models": list(pre.get("models", [])),
        "enabled": True,
        "origin": "user",
        "roles": {"athena": False, "sentinel": False},
        "authState": "nao verificado",
        "lastCheck": "",
    }
