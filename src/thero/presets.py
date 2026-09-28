"""Catalogo de presets de provedor e de programa-alvo.

Fonte unica do preenchimento inicial de `~/.thero/config.json`: o usuario
edita por cima, mas o preset continua aqui. Espelha `gui/mock.js` (fase 1
aprovada) -- se um dos dois mudar, o outro muda junto.

`writes` num programa-alvo e a diferenca entre "o Thero escreve neste
arquivo" e "o Thero so registra a intencao": so e True para arquivos cujo
formato foi CONFIRMADO nesta maquina (claude / opencode / codex / $PROFILE).
Qoder e VS Code estao como False de proposito: o conteudo real das configs
deles nao expoe chave de provedor/modelo verificavel.
"""

from __future__ import annotations

from typing import Optional

# authKind: "session" = sessao do proprio produto | "apikey" = chave em
# variavel de ambiente | "local" = endpoint local sem chave
PROVIDER_PRESETS: list = [
    {"id": "claude", "name": "Claude Code", "kind": "agente local",
     "authKind": "session", "base": "", "transport": "claude -p (subprocesso)",
     "models": ["opus", "sonnet", "haiku"], "famous": True},
    {"id": "qoder", "name": "Qoder", "kind": "agente local",
     "authKind": "session", "base": "", "transport": "sessao do Qoder",
     "models": ["padrao do plano"], "famous": True},
    {"id": "opencode", "name": "OpenCode", "kind": "agente local",
     "authKind": "apikey", "base": "",
     "transport": "provedores configurados no OpenCode",
     "models": ["conforme provedor"], "famous": True},
    {"id": "openai", "name": "OpenAI", "kind": "nuvem",
     "authKind": "apikey", "base": "https://api.openai.com/v1",
     "transport": "OpenAI-compativel",
     "models": ["gpt-4o", "gpt-4o-mini"], "famous": True},
    {"id": "codex", "name": "Codex", "kind": "agente local",
     "authKind": "session", "base": "https://api.openai.com/v1",
     "transport": "login do Codex CLI", "models": ["gpt-5-codex"],
     "famous": True},
    {"id": "cline", "name": "Cline", "kind": "agente local",
     "authKind": "apikey", "base": "", "transport": "chave propria por provedor",
     "models": ["conforme provedor"], "famous": True},
    {"id": "omniroute", "name": "OmniRoute", "kind": "roteador",
     "authKind": "apikey", "base": "",
     "transport": "um endpoint, varios modelos atras",
     "models": ["roteado pelo OmniRoute"], "famous": True},
    {"id": "anthropic", "name": "Anthropic API", "kind": "nuvem",
     "authKind": "apikey", "base": "https://api.anthropic.com/v1",
     "transport": "Anthropic Messages",
     "models": ["claude-sonnet-4-5", "claude-haiku-4-5"], "famous": True},
    {"id": "gemini", "name": "Google Gemini", "kind": "nuvem",
     "authKind": "apikey",
     "base": "https://generativelanguage.googleapis.com/v1beta",
     "transport": "Gemini generateContent",
     "models": ["gemini-2.5-pro", "gemini-2.5-flash"], "famous": True},
    {"id": "ollama", "name": "Ollama (local)", "kind": "local",
     "authKind": "local", "base": "http://127.0.0.1:11434",
     "transport": "API nativa Ollama",
     "models": ["llama3.2", "qwen2.5-coder:14b"], "famous": True},
    {"id": "lmstudio", "name": "LM Studio (local)", "kind": "local",
     "authKind": "local", "base": "http://127.0.0.1:1234/v1",
     "transport": "OpenAI-compativel local",
     "models": ["modelo carregado no LM Studio"], "famous": True},
    {"id": "openrouter", "name": "OpenRouter", "kind": "roteador",
     "authKind": "apikey", "base": "https://openrouter.ai/api/v1",
     "transport": "OpenAI-compativel",
     "models": ["qualquer modelo roteado"], "famous": True},
    {"id": "mistral", "name": "Mistral", "kind": "nuvem",
     "authKind": "apikey", "base": "https://api.mistral.ai/v1",
     "transport": "OpenAI-compativel", "models": ["mistral-large-latest"],
     "famous": False},
    {"id": "deepseek", "name": "DeepSeek", "kind": "nuvem",
     "authKind": "apikey", "base": "https://api.deepseek.com",
     "transport": "OpenAI-compativel", "models": ["deepseek-chat"],
     "famous": False},
    {"id": "groq", "name": "Groq", "kind": "nuvem",
     "authKind": "apikey", "base": "https://api.groq.com/openai/v1",
     "transport": "OpenAI-compativel", "models": ["llama-3.3-70b-versatile"],
     "famous": False},
    {"id": "azure", "name": "Azure OpenAI", "kind": "nuvem",
     "authKind": "apikey", "base": "", "transport": "deploy do seu recurso",
     "models": ["deploy configurado"], "famous": False},
    {"id": "xai", "name": "xAI", "kind": "nuvem",
     "authKind": "apikey", "base": "https://api.x.ai/v1",
     "transport": "OpenAI-compativel", "models": ["grok-4"], "famous": False},
    {"id": "custom", "name": "Manual (qualquer provedor)", "kind": "manual",
     "authKind": "apikey", "base": "",
     "transport": "OpenAI-compativel ou outro", "models": ["definir"],
     "famous": False},
]

# `target` diz qual escritor de apply.py usa: claude | opencode | codex |
# profile | none (record-only).
AGENT_PRESETS: list = [
    {"id": "claude", "name": "Claude Code", "kind": "CLI de agente",
     "cfg": "~/.claude/settings.json", "format": "json",
     "auth": "login do proprio Claude Code", "target": "claude",
     "writes": True, "skills": True, "famous": True, "note": ""},
    {"id": "opencode", "name": "OpenCode", "kind": "CLI de agente",
     "cfg": "~/.config/opencode/opencode.json", "format": "json",
     "auth": "secao de provider + env", "target": "opencode",
     "writes": True, "skills": True, "famous": True, "note": ""},
    {"id": "codex", "name": "Codex", "kind": "CLI de agente",
     "cfg": "~/.codex/config.toml", "format": "toml",
     "auth": "login do Codex ou env OPENAI_API_KEY", "target": "codex",
     "writes": True, "skills": False, "famous": True, "note": ""},
    {"id": "profile", "name": "Terminal (PowerShell / perfil do usuario)",
     "kind": "ambiente", "cfg": "$PROFILE", "format": "ps1",
     "auth": "variaveis de ambiente", "target": "profile",
     "writes": True, "skills": False, "famous": False,
     "note": "e por aqui que ATHENA_OLLAMA_HOST/MODEL chegam na Athena real"},
    {"id": "qoder", "name": "Qoder", "kind": "IDE/agente",
     "cfg": "~/.qoder/settings.json", "format": "proprio",
     "auth": "chave na propria config", "target": "none",
     "writes": False, "skills": True, "famous": True,
     "note": "sem chave de provedor/modelo verificavel no arquivo: o Thero "
             "so registra o modelo recomendado"},
    {"id": "vscode", "name": "VS Code", "kind": "editor",
     "cfg": "settings.json do usuario", "format": "json",
     "auth": "delegado a extensao instalada", "target": "none",
     "writes": False, "skills": False, "famous": True,
     "note": "o VS Code recebe provedor/modelo pela extensao (Cline, "
             "Continue, Roo), nao por conta propria"},
    {"id": "cline", "name": "Cline", "kind": "extensao VS Code",
     "cfg": "settings.json do VS Code (namespace cline)", "format": "json",
     "auth": "chave por provedor na UI da extensao", "target": "none",
     "writes": False, "skills": False, "famous": True, "note": ""},
    {"id": "roocode", "name": "Roo Code", "kind": "extensao VS Code",
     "cfg": "settings.json do VS Code (namespace Roo)", "format": "json",
     "auth": "chave por provedor na UI", "target": "none",
     "writes": False, "skills": False, "famous": False, "note": ""},
    {"id": "gemini-cli", "name": "Gemini CLI", "kind": "CLI de agente",
     "cfg": "~/.gemini/settings.json", "format": "json",
     "auth": "login ou GEMINI_API_KEY", "target": "none",
     "writes": False, "skills": False, "famous": False, "note": ""},
    {"id": "continue", "name": "Continue", "kind": "extensao IDE",
     "cfg": "~/.continue/config.json", "format": "json",
     "auth": "apiKey por provider no arquivo", "target": "none",
     "writes": False, "skills": False, "famous": False, "note": ""},
    {"id": "aider", "name": "Aider", "kind": "CLI de agente",
     "cfg": "~/.aider.conf.yml", "format": "yml", "auth": "env por provedor",
     "target": "none", "writes": False, "skills": False, "famous": False,
     "note": ""},
    {"id": "zed", "name": "Zed", "kind": "editor",
     "cfg": "~/.config/zed/settings.json", "format": "json",
     "auth": "variavel de ambiente por provedor", "target": "none",
     "writes": False, "skills": False, "famous": False, "note": ""},
    {"id": "cursor", "name": "Cursor", "kind": "IDE",
     "cfg": "ajustes da IDE", "format": "-",
     "auth": "conta Cursor; provedor proprio", "target": "none",
     "writes": False, "skills": False, "famous": True,
     "note": "a IDE nao expoe provedor por arquivo: so registra o modelo"},
    {"id": "manual", "name": "Manual (qualquer programa)", "kind": "manual",
     "cfg": "definir caminho", "format": "a definir", "auth": "definir",
     "target": "none", "writes": False, "skills": False, "famous": False,
     "note": ""},
]

# Preenchimento inicial (o usuario edita por cima). `preset` aponta para as
# listas acima; `id` e estavel e sobrevive a renomear o rotulo.
DEFAULT_PROVIDER_SEEDS: list = [
    {"id": "claude", "preset": "claude", "label": "Claude Code",
     "model": "sonnet", "roles": {"athena": True, "sentinel": False}},
    {"id": "openai", "preset": "openai", "label": "OpenAI",
     "model": "gpt-4o", "roles": {"athena": False, "sentinel": True}},
    {"id": "ollama", "preset": "ollama", "label": "Ollama (local)",
     "model": "llama3.2", "roles": {"athena": True, "sentinel": True}},
]

DEFAULT_AGENT_SEEDS: list = [
    {"id": "claude", "preset": "claude", "label": "Claude Code",
     "provider": "claude", "model": "sonnet"},
    {"id": "opencode", "preset": "opencode", "label": "OpenCode",
     "provider": "ollama", "model": "llama3.2"},
    {"id": "profile", "preset": "profile", "label": "Terminal (PowerShell)",
     "provider": "ollama", "model": "llama3.2"},
]


def provider_preset(pid: str) -> Optional[dict]:
    return next((p for p in PROVIDER_PRESETS if p["id"] == pid), None)


def agent_preset(aid: str) -> Optional[dict]:
    return next((a for a in AGENT_PRESETS if a["id"] == aid), None)


def default_providers() -> list:
    out = []
    for seed in DEFAULT_PROVIDER_SEEDS:
        pre = provider_preset(seed["preset"]) or {}
        auth_kind = pre.get("authKind", "apikey")
        out.append({
            "id": seed["id"],
            "label": seed["label"],
            "preset": seed["preset"],
            "kind": pre.get("kind", ""),
            "base": pre.get("base", ""),
            "transport": pre.get("transport", ""),
            "authKind": auth_kind,
            "authVar": ("THERO_%s_API_KEY" % seed["id"].upper())
                       if auth_kind == "apikey" else "",
            "model": seed["model"],
            "models": list(pre.get("models", [])),
            "enabled": True,
            "origin": "thero",
            "roles": dict(seed["roles"]),
            "authState": "nao verificado",
            "lastCheck": "",
        })
    return out


def default_agents() -> list:
    out = []
    for seed in DEFAULT_AGENT_SEEDS:
        pre = agent_preset(seed["preset"]) or {}
        out.append({
            "id": seed["id"],
            "label": seed["label"],
            "preset": seed["preset"],
            "kind": pre.get("kind", ""),
            "cfg": pre.get("cfg", ""),
            "format": pre.get("format", ""),
            "writes": bool(pre.get("writes", False)),
            "target": pre.get("target", "none"),
            "provider": seed["provider"],
            "model": seed["model"],
            "enabled": True,
            "skills": bool(pre.get("skills", False)),
            "origin": "thero",
            "status": "pendente",
            "note": pre.get("note", ""),
        })
    return out


LIMITS = ("local", "standard", "premium")


def default_limits() -> dict:
    """Teto de chamadas simultaneas por tipo de modelo (decisao do dono,
    2026-09-28). Os valores sao a recomendacao dele, nao um chute: `local` = 4
    porque o gargalo e o contexto/VRAM da maquina, nao a fatura; `standard` = 3
    e o meio-termo entre fila e custo; `premium` = 2 porque a cota cara estoura
    antes de qualquer fila. Quem OBSUSTA o teto e o Zeus (outro satellite,
    `2026-09-28-zeus-governador-de-modelos`); este modulo e a unica fonte dos
    numeros -- tela, CLI e ponte leem daqui.
    """
    return {"local": 4, "standard": 3, "premium": 2}


def default_routing() -> dict:
    # Cada slot comeca com o padrao que aquele proprio consumidor ja usa no
    # codigo dele: Athena = llama3.2 (athena/src/athena/settings.py), Sentinel
    # = qwen3-coder-next (sentinel/src/sentinel/settings.py:276).
    return {"mode": "zeus", "athena": "llama3.2",
            "sentinel": "qwen3-coder-next", "fallback": "Claude Code"}
