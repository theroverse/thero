"""Escritores de configuracao: o Thero aplicando provedor+modelo nos programas.

So escrevem onde o formato foi CONFIRMADO nesta maquina:
  claude    -> ~/.claude/settings.json       (chave "model" + env.ANTHROPIC)
  opencode  -> ~/.config/opencode/opencode.json  ("model": "provedor/modelo")
  codex     -> ~/.codex/config.toml          (escalares topo model/provider)
  profile   -> $PROFILE                      (blocos ATHENA_/SENTINEL_OLLAMA_)
O resto (Qoder, VS Code, Cline, Cursor...) e record-only: `writes=False`,
o Thero anota a intencao e nao encosta no arquivo de ninguem.

Regras caras: backup antes de escrever, merge em vez de substituir, e NUNCA
escrever em arquivo que nao se consegue reler como texto (nem utf-8 nem
cp1252 => recusa sem tocar). Um provedor local com base fora de loopback e
recusado na origem (A3): o valor vai parar em $env:ATHENA_OLLAMA_HOST que a
Athena le sem validacao. Todo retorno traz `written`, `backup` e um `msg` que
diz o que foi tocado -- a tela mostra, o usuario sabe.
Nada aqui usa print(): a GUI fala com o motor por stdout como canal JSON.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

from thero import localmodels, providers
from thero.shell_command import upsert_block
from thero.settings import (
    ENV_MARKER_END,
    ENV_MARKER_START,
    OLLAMA_DEFAULT_HOST,
)
from thero.system.process import timestamp


def default_paths(home: Optional[Path] = None) -> dict:
    # Deliberadamente SEM chave "profile": localizar a $PROFILE exige rodar
    # PowerShell (envreport._profile_path), e default_paths nao faz subprocess.
    # apply_agent aceita paths["profile"] so quando o proprio chamador o
    # injeta; a ponte passa a $PROFILE resolvida no argumento `profile`.
    home = Path(home) if home else Path.home()
    return {
        "claude": home / ".claude" / "settings.json",
        "opencode": home / ".config" / "opencode" / "opencode.json",
        "codex": home / ".codex" / "config.toml",
    }


def find_agent(cfg: dict, agent_id: str) -> Optional[dict]:
    return next((a for a in cfg.get("agents", []) if a.get("id") == agent_id),
                None)


def _backup(path: Path) -> str:
    """Copia silenciosa ANTES de tocar; devolve o NOME do backup (ou "").

    system.backup.backup_file() faz print() -- otimo no terminal, e o canal da
    ponte e JSON. Aqui o backup e efeito colateral, nao mensagem. Fica na
    maquina: nunca e versionado nem enviado.
    """
    if not path.exists():
        return ""
    target = path.with_name(
        "%s.backup_%s%s" % (path.stem, timestamp(), path.suffix))
    shutil.copy2(str(path), str(target))
    return target.name


def _backup_note(backup: str) -> str:
    return " (backup: %s)" % backup if backup else ""


def _model_of(cfg: dict, agent: dict) -> str:
    if agent.get("model"):
        return agent["model"]
    provider = next((p for p in cfg.get("providers", [])
                     if p.get("id") == agent.get("provider")), None)
    return (provider or {}).get("model", "")


def _read_text(path: Path):
    """Le texto SEM corromper -> (texto, encoding_de_escrita) ou None.

    Proibido errors="replace" num caminho que regrava: um $PROFILE/config.toml
    salvo como cp1252 (comum no PowerShell 5.1) viraria U+FFFD escrito de volta
    -- perda byte a byte. utf-8-sig tolera BOM na leitura (escrevemos sem BOM);
    cp1252 so quando o utf-8 falha, e ai PRESERVA o cp1252. Nem um nem outro =>
    None, e o chamador recusa sem tocar no arquivo.
    """
    try:
        return path.read_text(encoding="utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        return path.read_text(encoding="cp1252"), "cp1252"
    except UnicodeDecodeError:
        return None


def _refuse(msg: str) -> dict:
    return {"ok": False, "written": "", "backup": "", "msg": msg}


def _write_json_target(path: Path, mutate) -> dict:
    """Le JSON (tolerando BOM), aplica `mutate`, escreve so se parsear.

    Arquivo ausente comeca de {}; ilegivel como texto ou JSON invalido e
    recusado sem toque e sem backup.
    """
    path = Path(path)
    encoding = "utf-8"
    if path.exists():
        read = _read_text(path)
        if read is None:
            return _refuse("nao consegui ler %s como texto" % path)
        original, encoding = read
        try:
            data = json.loads(original)
        except ValueError:
            return _refuse("nao fui em %s: nao e JSON valido" % path)
        if not isinstance(data, dict):
            return _refuse("nao fui em %s: o JSON nao e um objeto" % path)
    else:
        data = {}
    data = mutate(data) or data
    backup = _backup(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding=encoding,
    )
    return {"ok": True, "written": str(path), "backup": backup,
            "msg": "atualizado: %s%s" % (path.name, _backup_note(backup))}


def apply_claude(agent, cfg: dict, path: Path) -> dict:
    # `agent` chega do despacho; None -> agente de id "claude" (compat com
    # chamada direta). Nunca fixar "claude" no corpo: um segundo agente com
    # target="claude" escreveria o modelo do agente errado.
    if agent is None:
        agent = find_agent(cfg, "claude") or {}
    model = _model_of(cfg, agent)
    if not model:
        return _refuse("sem modelo definido para o Claude Code")

    def mutate(data):
        data["model"] = model
        env = data.get("env")
        if not isinstance(env, dict):
            env = {}
        env["ANTHROPIC_MODEL"] = model
        data["env"] = env
        return data

    return _write_json_target(Path(path), mutate)


def apply_opencode(agent: dict, cfg: dict, path: Path) -> dict:
    provider = agent.get("provider") or "local"
    model = _model_of(cfg, agent)
    if not model:
        return _refuse("sem modelo definido para o OpenCode")

    def mutate(data):
        data["model"] = "%s/%s" % (provider, model)
        return data

    return _write_json_target(Path(path), mutate)


def _codex_has_provider_table(lines, provider: str) -> bool:
    """Mesma mesa [model_providers.<id>] que o Codex usa ao resolver."""
    exact = "[model_providers.%s]" % provider
    sub = "[model_providers.%s." % provider
    for line in lines:
        stripped = line.strip()
        if stripped == exact or stripped.startswith(sub):
            return True
    return False


def apply_codex(agent: dict, cfg: dict, path: Path) -> dict:
    """Edicao linha-a-linha: so os escalares de topo, antes do 1o [table].

    Sem parser TOML no core (politica stdlib-only + Python 3.9 nao tem
    tomllib), entao mexer so nas linhas de topo e o caminho que preserva
    mesas, comentarios e formatacao do usuario.
    """
    path = Path(path)
    model = _model_of(cfg, agent)
    if not model:
        return _refuse("sem modelo definido para o Codex")
    encoding = "utf-8"
    lines = []
    if path.exists():
        read = _read_text(path)
        if read is None:
            return _refuse("nao consegui ler %s como texto" % path)
        original, encoding = read
        lines = original.splitlines()
    table_index = len(lines)
    for index, line in enumerate(lines):
        if line.strip().startswith("["):
            table_index = index
            break
    head = list(lines[:table_index])
    tail = lines[table_index:]

    wanted = {"model": '"%s"' % model}
    provider = agent.get("provider") or ""
    skipped_provider = ""
    if provider:
        # Apontar model_provider para uma mesa [model_providers.<id>] que nao
        # existe QUEBRA o Codex (na maquina real o arquivo ja tem, p.ex.,
        # model_provider = "deepseek" com a mesa la). So escrevo se a mesa
        # existir no corpo; senao escrevo apenas `model` e aviso no msg.
        if _codex_has_provider_table(lines, provider):
            wanted["model_provider"] = '"%s"' % provider
        else:
            skipped_provider = provider

    consumed = set()
    out = []
    for line in head:
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip()
            if key in wanted:
                out.append("%s = %s" % (key, wanted[key]))
                consumed.add(key)
                continue
        out.append(line)
    for key, value in wanted.items():
        if key not in consumed:
            out.append("%s = %s" % (key, value))
    out.extend(tail)

    backup = _backup(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding=encoding)
    msg = "atualizado: %s%s" % (path.name, _backup_note(backup))
    if skipped_provider:
        msg += (": mantive o model_provider do arquivo porque a mesa "
                "[model_providers.%s] nao existe nele" % skipped_provider)
    return {"ok": True, "written": str(path), "backup": backup, "msg": msg}


def provider_base(cfg: dict, provider_id: str) -> str:
    provider = next((p for p in cfg.get("providers", [])
                     if p.get("id") == provider_id), None)
    base = (provider or {}).get("base") or ""
    return base or OLLAMA_DEFAULT_HOST


# Um par de variaveis por consumidor, com o nome exato que cada um le no
# proprio codigo e o padrao daquele consumidor quando o usuario nao escolheu:
#   Athena   -> athena/src/athena/settings.py:52-72
#   Sentinel -> sentinel/src/sentinel/settings.py:255-283
# A lista de consumidores que a UI conhece e `providers.CONSUMERS`; o teste
# abaixo garante que estas duas fontes nunca divergem.
ENV_CONTRACTS = {
    "athena": ("ATHENA_OLLAMA_HOST", "ATHENA_OLLAMA_MODEL", "llama3.2"),
    "sentinel": ("SENTINEL_OLLAMA_HOST", "SENTINEL_OLLAMA_MODEL",
                 "qwen3-coder-next"),
}


def _ollama_base(cfg: dict) -> str:
    """Host do motor local, VALIDADO como loopback antes de virar $PROFILE.

    O valor aqui escrito chega a ATHENA_OLLAMA_HOST, que a Athena le sem
    validacao; so o Sentinel veta por conta propria. Entao o veto mora AQUI:
    delegar ao localmodels.guard_base (nao reimplementar a regex de loopback).
    Base remota -> ValueError (com a base crua no texto; quem chama redige).
    """
    for provider in cfg.get("providers", []):
        if not isinstance(provider, dict):
            continue
        is_ollama = (provider.get("preset") == "ollama"
                     or provider.get("id") == "ollama")
        if is_ollama:
            return localmodels.guard_base(
                provider.get("base") or OLLAMA_DEFAULT_HOST)
    return OLLAMA_DEFAULT_HOST


def profile_env_block(cfg: dict) -> str:
    """Contrato dos dois consumidores locais, num bloco so da $PROFILE."""
    routing = cfg.get("routing") or {}
    base = _ollama_base(cfg)
    lines = [
        ENV_MARKER_START,
        "# Gerado pelo Thero. Editar na interface do Thero (Modelos locais).",
    ]
    for consumer in providers.CONSUMERS:
        host_var, model_var, fallback = ENV_CONTRACTS[consumer]
        lines.append('$env:%s = "%s"' % (host_var, base))
        lines.append('$env:%s = "%s"'
                     % (model_var, routing.get(consumer) or fallback))
    lines.append(ENV_MARKER_END)
    return "\n".join(lines)


def apply_profile(cfg: dict, profile) -> dict:
    # Valida ANTES de converter: Path(None) levanta TypeError e o msg de
    # "$PROFILE nao localizada" ficaria inalcancavel.
    if profile is None or not str(profile):
        return _refuse("nao localizei a $PROFILE do PowerShell")
    profile = Path(profile)
    try:
        block = profile_env_block(cfg)
    except ValueError as exc:
        return _refuse("modelos locais so em loopback: %s"
                       % providers.redact(exc))
    existing = ""
    encoding = "utf-8"
    if profile.exists():
        read = _read_text(profile)
        if read is None:
            return _refuse("nao consegui ler %s como texto" % profile)
        existing, encoding = read
    elif not profile.parent.exists():
        return _refuse("pasta da $PROFILE nao existe: %s" % profile.parent)
    backup = _backup(profile)
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(
        upsert_block(existing, block, ENV_MARKER_START, ENV_MARKER_END),
        encoding=encoding,
    )
    return {"ok": True, "written": str(profile), "backup": backup,
            "msg": "ambiente Athena/Sentinel atualizado na $PROFILE%s"
                   % _backup_note(backup)}


TARGETS = ("claude", "opencode", "codex", "profile")


def apply_agent(agent: dict, cfg: dict, paths: dict,
                profile: Optional[Path] = None) -> dict:
    target = agent.get("target") or "none"
    # id/target presentes em TODO retorno: a ponte casa os resultados por
    # `id` no apply-all; sem isso o recod-only (Qoder/VS Code/Cline/Cursor)
    # nunca daria match e o status ficaria "pendente" para sempre.
    base = {"id": agent.get("id", target), "target": target}
    label = agent.get("label") or agent.get("id", "")
    if target not in TARGETS:
        return dict(base, ok=True, writes=False, written="", backup="",
                    msg="%s: registrado no Thero (o arquivo desse programa "
                        "nao expoe chave verificavel)" % label)
    if target == "profile":
        where = profile or paths.get("profile")
        if not where:
            return dict(base, ok=False, writes=True, written="", backup="",
                        msg="$PROFILE nao encontrada nesta maquina")
        out = apply_profile(cfg, Path(where))
    else:
        where = paths.get(target)
        if not where:
            return dict(base, ok=False, writes=True, written="", backup="",
                        msg="sem caminho conhecido para %s" % target)
        if target == "claude":
            out = apply_claude(agent, cfg, Path(where))
        elif target == "opencode":
            out = apply_opencode(agent, cfg, Path(where))
        else:
            out = apply_codex(agent, cfg, Path(where))
    return dict(base, writes=True, **out)


def apply_all(cfg: dict, paths: dict,
              profile: Optional[Path] = None) -> list:
    results = []
    for agent in cfg.get("agents", []):
        if not agent.get("enabled", True):
            continue
        results.append(apply_agent(agent, cfg, paths, profile))
    return results