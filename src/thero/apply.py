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
    """Copia silenciosa ANTES de tocar; devolve o NOME do ultimo backup.

    system.backup.backup_file() faz print() -- otimo no terminal, e o canal da
    ponte e JSON. Aqui o backup e efeito colateral, nao mensagem. Fica na
    maquina: nunca e versionado nem enviado.

    Retencao decidida pelo dono em 2026-09-28: no maximo DOIS arquivos por
    alvo, sem serie temporal. "-original" e escrito uma vez e nunca e
    sobrescrito: e o byte que existia antes da primeira mexida do Thero.
    "-last" e substituido a cada escrita e guarda o conteudo imediatamente
    anterior. Nome fixo, sem timestamp -- o caso que o B2 resolvia com sufixo
    _2 nao existe mais, porque duas escritas no mesmo segundo atualizam o
    mesmo par.
    """
    if not path.exists():
        return ""
    original = path.with_name("%s-original.zbkp%s" % (path.stem,
                                                      path.suffix))
    if not original.exists():
        shutil.copy2(str(path), str(original))
    last = path.with_name("%s-last.zbkp%s" % (path.stem, path.suffix))
    shutil.copy2(str(path), str(last))
    return last.name


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
    salvo como cp1252 (comum no PowerShell 5.1) viraria U+FFFD escrito de
    volta -- perda byte a byte. utf-8-sig tolera BOM na leitura (escrevemos
    sem BOM); cp1252 so quando o utf-8 falha, e ai PRESERVA o cp1252. Nem um
    nem outro => None, e o chamador recusa sem tocar no arquivo. OSError
    (caminho que e diretorio, alvo sem permissao) tambem vira None (B4): a
    recusa e limpa, a excecao do SO nao sai do modulo.
    """
    try:
        return path.read_text(encoding="utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        pass
    except OSError:
        return None
    try:
        return path.read_text(encoding="cp1252"), "cp1252"
    except (UnicodeDecodeError, OSError):
        return None


def _refuse(msg: str) -> dict:
    return {"ok": False, "written": "", "backup": "", "msg": msg}


def _backup_and_write(path: Path, content: str, encoding: str) -> dict:
    """Serializa em bytes ANTES de tocar no arquivo (B1/B4).

    write_text() abre e trunca e so entao codifica: alvo salvo em cp1252 com
    um caractere fora do cp1252 no modelo deixaria o settings.json VAZIO no
    disco com o erro na janela. Aqui, se o conteudo nao cabe na codificacao
    do arquivo (ou o SO recua a gravacao -- alvo somente leitura, caminho que
    e diretorio), a recusa e limpa: backup e escrita so acontecem com os
    bytes em Mao, e o msg nao ecoa chave nem credencial.
    """
    try:
        payload = content.encode(encoding)
    except UnicodeEncodeError:
        return _refuse("o conteudo nao cabe na codificacao %s do arquivo %s"
                       % (encoding, path.name))
    try:
        backup = _backup(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    except OSError:
        return _refuse("nao consegui escrever em %s: o sistema recusou a"
                       " gravacao" % path.name)
    return {"ok": True, "written": str(path), "backup": backup,
            "msg": "atualizado: %s%s" % (path.name, _backup_note(backup))}


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
    return _backup_and_write(
        path,
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding,
    )


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

    result = _backup_and_write(path, "\n".join(out) + "\n", encoding)
    if skipped_provider and result["ok"]:
        result["msg"] += (": mantive o model_provider do arquivo porque a "
                "mesa [model_providers.%s] nao existe nele" % skipped_provider)
    return result


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
    result = _backup_and_write(
        profile,
        upsert_block(existing, block, ENV_MARKER_START, ENV_MARKER_END),
        encoding,
    )
    if result["ok"]:
        result["msg"] = ("ambiente Athena/Sentinel atualizado na $PROFILE%s"
                         % _backup_note(result["backup"]))
    return result


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