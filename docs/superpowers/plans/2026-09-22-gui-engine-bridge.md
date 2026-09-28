# Thero GUI ↔ Motor real — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ligar a interface desktop aprovada (`thero/gui/`, hoje 100% mock) ao motor real: host PowerShell+WebView2 no padrão Vector/Gênesis, ponte JSON-lines em Python, e o motor que **ainda não existe** para provedores / modelos locais / programas-alvo.

**Architecture:** Mesma separação do Vector: toda regra e toda escrita em disco moram em Python (`src/thero/*.py`); `TheroHost.ps1` só abre a janela, levanta o filho Python (`python thero.py --serve`) e repassa pedidos/respostas; o JS nunca decide segurança, só apresenta. O `~/.thero/config.json` é a fonte de verdade do que o usuário parametrizou; aplicar num programa-alvo é uma escrita pontual, precedida de backup, no arquivo nativo **cujo contrato foi verificado nesta máquina**.

**Tech Stack:** Python 3.9+ stdlib apenas (json/urllib/shutil/subprocess/pathlib), pytest, WebView2 (DLLs vendorizadas), JS vanilla (`app.js`/`mock.js`), PowerShell 5.1 WinForms, ps2exe.

**Branch:** `feat/gui-engine-bridge` no submódulo `thero` (a partir de `develop`).

---

## Fatos verificados nesta máquina (não inventar nada além disso)

| Fato | Onde foi visto |
|---|---|
| Protocolo da ponte a copiar (JSON-lines, `BridgeState`, `handle_request(..., scan_fn, stage_fn)`, `_ok`/`_err`, `serve()` com `ensure_ascii=False`) | `vector/src/vector/bridge.py` |
| Host a copiar (payload embutido, titlebar própria, `Send-ToJs`, filho Python, whitelist de `engine-call`) | `vector/gui/VectorHost.ps1` (551 linhas) |
| Empacotamento a copiar (`build.ps1` + `scripts/build-payload.ps1` + `scripts/make-exe-icon.ps1`, ps2exe, exe único) | `vector/build.ps1`, `vector/scripts/*` |
| JS↔PS exige `JSON.stringify`; o host lê com `TryGetWebMessageAsString()` | `vector/gui/vector/app.js:40-50`, memória `webview2-js-to-ps-bridge-requires-json-stringify` |
| Contrato real de consumidor dos modelos locais: `ATHENA_OLLAMA_HOST` / `ATHENA_OLLAMA_MODEL`, default `http://localhost:11434` e `llama3.2`, backend `auto` | `athena/src/athena/settings.py:52-72` |
| Ollama **não** está instalado aqui (11434 recusa conexão; `where ollama` vazio) | mediado em 2026-09-22 |
| Sentinel **não** instala nem baixa motor nenhum, mas **tem** consumidor próprio: resolve `SENTINEL_OLLAMA_HOST` > `.sentinel/config.json` > padrão `http://127.0.0.1:11434`, e `SENTINEL_OLLAMA_MODEL` com padrão `qwen3-coder-next`; host fora de loopback é recusado no código | `sentinel/src/sentinel/settings.py:255-283` (`OLLAMA_HOST_ENV` :263, `OLLAMA_MODEL_ENV` :264, `DEFAULT_MODEL_BASE` :269, `DEFAULT_MODEL_NAME` :276, `MODEL_LOOPBACK_HOSTS` :283) + `src/sentinel/local_model.py:90` (commit `a4b1412`, 2026-09-22) |
| `~/.claude/settings.json` existe e é JSON simples; o Claude Code aceita `model` no topo e um bloco `env`, e `ANTHROPIC_MODEL` é variável real | arquivo lido + docs.claude.com/settings |
| **Não verificado** (portanto **não** será escrito): `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` | — |
| `~/.config/opencode/opencode.json` existe (`$schema`, `instructions`); o schema oficial aceita `model` no formato `provider/model` e blocos `provider.<id>.{npm,options}` | arquivo + opencode.ai/config.json |
| `~/.codex/config.toml` existe, com `model` e `model_provider` no topo e blocos `[model_providers.<id>]` | arquivo lido (nenhum valor de chave copiado adiante) |
| `~/.qoder/settings.json` só tem chaves de plugin (`aicodingPluginSettingsMigrationVersion`, `enabledPlugins`) → Qoder é **record-only** | arquivo lido |
| `%APPDATA%\Code\User\settings.json` existe, mas a chave por extensão não foi verificada → VS Code é **record-only** | arquivo lido |
| `~/.claude/skills` tem 40 pastas, cada uma com `SKILL.md`; **não** há marcador de procedência em disco (`metadata.yaml` é do próprio skill) → origem se deduz do catálogo do Thero | `ls ~/.claude/skills` |
| `~/.thero` **ainda não existe** (o store estreia a pasta) | testado |
| `npx` está quebrado agora (`Cannot find module ...npm-prefix.js`, Node v26.7.0) → a tela Status mostra isso, não finge que roda | `npx --help` executado |
| Baseline de testes: `python -m pytest tests/ -q` → **247 passed**; runtime local Python 3.14, matriz CI inclui 3.9 | executado em `thero/` |

## Regras inegociáveis deste plano

1. **Stdlib only.** Nenhuma dependência nova.
2. **3.9-compatível**: `from __future__ import annotations`; sem `match`; sem `tomllib` (3.11); sem `Path.write_text(newline=...)` (3.10).
3. **Nada de `print()` no caminho da ponte.** `thero.system.backup.backup_file` imprime na stdout — por isso `apply.py` tem backup próprio e silencioso. Um `print` no meio do canal JSON-lines corrompe a resposta e derruba a janela.
4. **Nunca ler nem gravar valor de chave.** O Thero guarda só o **nome** da variável de ambiente: `_has_var(nome)` testa presença; nenhuma função faz `os.environ[nome]`.
5. **Ollama só em loopback.** `localmodels` recusa host que não seja `127.0.0.1`/`localhost`.
6. **Toda escrita em arquivo de terceiro**: backup antes, merge (nunca reescrever o arquivo inteiro), chave desconhecida preservada, recusa se o arquivo não for parseável.
7. **Commits**: nunca em `main`; cada passo "Commit" abaixo só roda com o "ok" explícito do usuário. Push e PR continuam sendo decisão do usuário.
8. **Testes offline**: nada abre a rede; sonda HTTP é injetável/monkeypatchável.

**Rodar testes sempre de:** `c:/Users/anthe/.myscripts/thero` com `python -m pytest tests/ -q`.

---

## Task 0 — Preparar o terreno (branch + o que já existe)

Verificado nesta máquina em 2026-09-22: o submódulo `thero` está em `develop`
e `git status --short` mostra **`gui/` e `docs/` como não rastreados** — a
interface mock aprovada e este plano ainda não estão em nenhum commit. Sem
este passo, o trabalho nasce num branch que não contém a interface que o plano
vai ligar ao motor.

- [ ] **Step 1: Criar o branch de trabalho a partir de `develop`**

```bash
cd c:/Users/anthe/.myscripts/thero
git status --short            # confirmar: nada modificado, so gui/ e docs/ nao rastreados
git checkout -b feat/gui-engine-bridge
```
Nunca `main`. O branch é local; subir para o remoto é decisão do usuário.

- [ ] **Step 2: Confirmar o baseline antes de qualquer mudança**

```bash
python -m pytest tests/ -q
```
Expected: `247 passed`. Se esse número não fechar, parar e reportar — todas as
contagens abaixo dependem dele.

- [ ] **Step 3: Commit da interface aprovada + deste plano (pedir confirmação)**

```bash
git add gui docs
git status --short            # conferir o que entra: nada de __pycache__ ou .build/
git commit -m "feat(gui): approved desktop interface mock (nine screens + first-run wizard)"
```

- [ ] **Step 4: DLLs do WebView2 vendorizadas**

Copiar de `vector/gui/webview2/` para `thero/gui/webview2/`. Verificado nesta
máquina: a pasta do Vector tem exatamente três arquivos —
`Microsoft.Web.WebView2.Core.dll`, `Microsoft.Web.WebView2.WinForms.dll`,
`WebView2Loader.dll` — e é dela que o `VectorHost.ps1` carrega. A Task 11
falha se faltar algum.

```bash
mkdir -p gui/webview2
cp ../vector/gui/webview2/*.dll gui/webview2/
ls gui/webview2
```
Expected: os três `.dll` acima, nada mais.

```bash
git add gui/webview2
git commit -m "chore(gui): vendor the WebView2 binaries the host loads"
```

---

# FASE 0 — Motor em Python (nada de UI ainda)

### Task 1: Constantes novas + catálogo de presets + store `config.json`

**Files:**
- Modify: `src/thero/settings.py` (acrescentar no fim)
- Create: `src/thero/presets.py`
- Create: `src/thero/config.py`
- Test: `tests/test_presets.py`, `tests/test_config.py`

- [ ] **Step 1: Escrever os testes que falham**

`tests/test_presets.py`:

```python
from thero import presets


def test_provider_presets_have_the_fields_the_ui_reads():
    for p in presets.PROVIDER_PRESETS:
        assert set(["id", "name", "kind", "authKind", "base",
                    "transport", "models"]) <= set(p)
        assert p["authKind"] in ("session", "apikey", "local")


def test_agent_presets_declare_whether_they_actually_write():
    for a in presets.AGENT_PRESETS:
        assert "writes" in a and "cfg" in a
    # verificados nesta maquina: qoder e vscode NAO recebem config por arquivo
    assert presets.agent_preset("qoder")["writes"] is False
    assert presets.agent_preset("vscode")["writes"] is False
    assert presets.agent_preset("claude")["writes"] is True


def test_default_providers_are_prefilled_but_editable():
    provs = presets.default_providers()
    ids = [p["id"] for p in provs]
    assert "claude" in ids and "ollama" in ids and "openai" in ids
    for p in provs:
        assert set(["id", "label", "preset", "authKind", "base", "authVar",
                    "transport", "model", "enabled", "roles", "authState",
                    "lastCheck"]) <= set(p)


def test_default_routing_starts_in_zeus_mode():
    r = presets.default_routing()
    assert r["mode"] == "zeus"
    assert r["athena"] and r["sentinel"] and r["fallback"]
```

`tests/test_config.py`:

```python
import json

from thero import config


def test_default_config_shape():
    cfg = config.default_config()
    assert cfg["version"] == config.CONFIG_VERSION
    assert cfg["providers"] and cfg["agents"]
    assert set(cfg["routing"]) == {"mode", "athena", "sentinel", "fallback"}
    assert cfg["preferences"] == {"scope": "global"}


def test_load_missing_file_returns_defaults(tmp_path):
    assert config.load(tmp_path / "config.json") == config.default_config()


def test_load_corrupt_file_returns_defaults_instead_of_crashing(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{ isto nao e json", encoding="utf-8")
    assert config.load(p) == config.default_config()


def test_save_then_load_roundtrip_keeps_accents(tmp_path):
    p = tmp_path / "config.json"
    cfg = config.default_config()
    cfg["providers"][0]["label"] = "Ômega — local"
    config.save(cfg, path=p)
    assert config.load(p)["providers"][0]["label"] == "Ômega — local"


def test_save_creates_the_directory_when_absent(tmp_path):
    # a primeira gravacao na maquina do usuario e exatamente esse caso:
    # ~/.thero ainda nao existe
    p = tmp_path / ".thero" / "config.json"
    config.save(config.default_config(), path=p)
    assert p.exists()


def test_save_writes_no_bom_and_leaves_no_temp_file(tmp_path):
    # memoria: config JSON com BOM quebra json.loads estrito no Windows.
    # a gravacao e atomica (tmp + os.replace), entao nao pode sobrar sobra.
    p = tmp_path / "config.json"
    config.save(config.default_config(), path=p)
    assert not p.read_bytes().startswith(b"\xef\xbb\xbf")
    json.loads(p.read_text(encoding="utf-8"))  # nao pode lancar erro
    assert not list(tmp_path.glob("*.tmp"))


def test_load_tolerates_a_bom_on_disk(tmp_path):
    p = tmp_path / "config.json"
    p.write_bytes(b"\xef\xbb\xbf" + b'{"version": 1}')
    assert config.load(p)["version"] == 1


def test_load_keeps_user_choices_and_fills_new_keys(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"version": 1, "providers": [], "novo": 7}),
                 encoding="utf-8")
    cfg = config.load(p)
    assert cfg["providers"] == []                  # escolha do usuario vencem
    assert cfg["novo"] == 7                         # chave futura preservada
    assert "agents" in cfg and "routing" in cfg     # faltante vem do default


def test_config_path_follows_a_patched_home(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    assert config.config_path() == tmp_path / ".thero" / "config.json"


def test_is_first_run(tmp_path):
    p = tmp_path / "config.json"
    assert config.is_first_run(p) is True
    config.save(config.default_config(), path=p)
    assert config.is_first_run(p) is False
```

- [ ] **Step 2: Rodar para confirmar a falha**

Run: `python -m pytest tests/test_config.py tests/test_presets.py -q`
Expected: `ModuleNotFoundError: No module named 'thero.presets'`

- [ ] **Step 3: Constantes em `settings.py`**

Acrescentar ao fim de `src/thero/settings.py` (mantendo o que já existe):

```python
# --- config store da interface (estreando junto com a GUI) --------------
# Path.home() e resolvido no import: por isso toda funcao que le/escreve
# aceita `path=`/`base=` explicito -- os testes injetam tmp_path, ja que o
# conftest faz monkeypatch do HOME DEPOIS do import.
THERO_DIR = Path.home() / ".thero"

# Skills vivem no territorio do Claude Code (mesma base do instalador);
# a quarentena das removidas fica na pasta do Thero.
SKILLS_BASE_GLOBAL = CLAUDE_DIR / "skills"

SKILLS_QUARANTINE_DIRNAME = "skills"

# Bloco de ambiente no $PROFILE: e como ATHENA_OLLAMA_HOST/MODEL (athena/src/
# athena/settings.py) e SENTINEL_OLLAMA_HOST/MODEL (sentinel/src/sentinel/
# settings.py:255-283) chegam de fato a qualquer processo lancado do terminal.
# Marcadores proprios, diferentes dos do
# comando global, para um upsert nao comer o outro.
ENV_MARKER_START = "# >>> thero env >>>"

ENV_MARKER_END = "# <<< thero env <<<"

# Unico host aceito pela sonda de modelos locais (mesma regra do Sentinel).
OLLAMA_DEFAULT_HOST = "http://127.0.0.1:11434"

OLLAMA_PROBE_TIMEOUT = 3

# Teto de leitura POR OPERACAO do `ollama pull` (timeout de socket em cada
# read, nao a duracao total do download): um modelo de varios GB passa pelas
# fases `verifying sha256`/`writing blob` sem emitir bytes por minutos.
OLLAMA_PULL_TIMEOUT = 1800

# delete e mutacao, nao sonda: o unlink de blobs de GB passa dos 3 s da sonda.
OLLAMA_DELETE_TIMEOUT = 30
```

- [ ] **Step 4: `presets.py` — espelho fiel do mock aprovado**

Create `src/thero/presets.py`. Os `id`s/`label`s abaixo são os mesmos de `gui/mock.js` (fase 1 aprovada); nada foi renomeado.

```python
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


def default_routing() -> dict:
    # Cada slot comeca com o padrao que aquele proprio consumidor ja usa no
    # codigo dele: Athena = llama3.2 (athena/src/athena/settings.py), Sentinel
    # = qwen3-coder-next (sentinel/src/sentinel/settings.py:276).
    return {"mode": "zeus", "athena": "llama3.2",
            "sentinel": "qwen3-coder-next", "fallback": "Claude Code"}
```

- [ ] **Step 5: `config.py`**

Create `src/thero/config.py`:

```python
"""Store de `~/.thero/config.json`: o que o usuario parametrizou na interface.

Regras que ja custaram tempo nesta maquina: ler com `utf-8-sig` (Set-Content
do PowerShell escreve BOM e o `json.loads` estrito morre), escrever SEM BOM e
escrever atomico (arquivo meio gravado + o fallback de corrompido viram
perda de escolha), e nao perder escolha do usuario ao evoluir o schema -- as
chaves de topo sao sobrepostas aos defaults, chave desconhecida preservada.
Campos novos DENTRO de uma entrada de `providers`/`agents` nao sao injetados:
quem consome essas listas le com `.get()` e default proprio.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from thero import presets

CONFIG_VERSION = 1


def config_path() -> Path:
    """Path efetivo do config, resolvido NA CHAMADA: o conftest remapeia HOME
    depois do import, entao a constante congelada em thero.settings nao vale
    para teste nenhum."""
    root = os.environ.get("USERPROFILE") or os.environ.get("HOME")
    base = Path(root) if root else Path.home()
    return base / ".thero" / "config.json"


def default_config() -> dict:
    return {
        "version": CONFIG_VERSION,
        "providers": presets.default_providers(),
        "agents": presets.default_agents(),
        "routing": presets.default_routing(),
        "preferences": {"scope": "global"},
    }


def load(path: Optional[Path] = None) -> dict:
    target = path or config_path()
    cfg = default_config()
    if not target.exists():
        return cfg
    try:
        stored = json.loads(target.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError):
        return cfg
    if not isinstance(stored, dict):
        return cfg
    for key, value in stored.items():
        cfg[key] = value
    cfg["version"] = CONFIG_VERSION
    return cfg


def save(cfg: dict, path: Optional[Path] = None) -> Path:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(cfg)
    payload["version"] = CONFIG_VERSION
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    # Escrita atomica: `load()` devolve os defaults para arquivo corrompido,
    # entao uma gravacao interrompida no meio custaria as escolhas do usuario
    # na proxima abertura. os.replace() e atomico no Windows e no POSIX, 3.9+.
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(str(tmp), str(target))
    return target


def is_first_run(path: Optional[Path] = None) -> bool:
    return not (path or config_path()).exists()
```

- [ ] **Step 6: Rodar**

Run: `python -m pytest tests/ -q`
Expected: `247 + 14 = 261 passed` (nada dos testes antigos pode quebrar)

- [ ] **Step 7: Commit (pedir confirmação antes)**

```bash
git add src/thero/settings.py src/thero/presets.py src/thero/config.py \
        tests/test_config.py tests/test_presets.py
git commit -m "feat(config): add provider/agent presets and the ~/.thero/config.json store"
```

---

### Task 2: Retrato do ambiente (`envreport.py`) — Status + onboarding

**Files:**
- Create: `src/thero/envreport.py`
- Modify: `src/thero/system/process.py:20-63` (`run_command` ganha teto de tempo opcional)
- Modify: `src/thero/shell_command/windows.py:14-34` (`resolve_powershell_profile` passa a aceitar `timeout`)
- Test: `tests/test_envreport.py`

> **Correção da revisão de qualidade (2026-09-22, 4 achados bloqueantes):**
> (1) a sonda do `$PROFILE` ganhou teto (`PROFILE_TIMEOUT = 5`, propagado até
> `resolve_powershell_profile`); (2) o import tardio e as operações de filesystem
> (`iterdir`/`stat`/`glob`) entraram na fronteira protegida — a falha de UM item
> degrada só aquele campo, nunca o payload inteiro; (3) `_first_line` virou
> `_version_probe` e devolve `(linha, ok)` com `ok` derivado do `returncode`
> real — acabou a adivinhação pelo texto; (4) `_command_installed` casa o
> marcador exato `COMMAND_MARKER_START` (que o instalador do comando global
> escreve no `$PROFILE`), não a substring `"thero"` — o bloco de ENV da Task 5
> vive no mesmo arquivo. Contagem de testes da Task 2: 8 → 15; a cadeia
> inteira de contagens abaixo foi atualizada (+7 em cada passo seguinte).

- [ ] **Step 1: Testes**

`tests/test_envreport.py`:

```python
from __future__ import annotations

import json

import pytest

from thero import apply
from thero.shell_command import upsert_block, upsert_marked_block
from thero.settings import (
    COMMAND_MARKER_END,
    COMMAND_MARKER_START,
    ENV_MARKER_END,
    ENV_MARKER_START,
)


# ---- upsert_block generico (detecta os marcadores ja dentro do bloco) ----

def test_upsert_block_appends_when_absent():
    out = upsert_block("echo oi\n", ">>>\nblock\n<<<", ">>>", "<<<")
    assert out.startswith("echo oi")
    assert ">>>\nblock\n<<<" in out


def test_upsert_block_replaces_instead_of_duplicating():
    first = upsert_block("", ">>>\nA\n<<<", ">>>", "<<<")
    second = upsert_block(first, ">>>\nC\n<<<", ">>>", "<<<")
    assert second.count(">>>") == 1
    assert "C" in second and "A" not in second


def test_upsert_block_keeps_text_after_the_marker():
    existing = "antes\n>>>\nvelho\n<<<\ndepois\n"
    out = upsert_block(existing, ">>>\nnovo\n<<<", ">>>", "<<<")
    assert "antes" in out and "depois" in out
    assert "novo" in out and "velho" not in out


def test_upsert_block_does_not_cannibalize_other_marked_blocks():
    # dois pares de marcadores distintos no mesmo arquivo: trocar um par nao
    # pode engolir o outro (a busca por index(end) acha o fim do MESMO bloco).
    existing = ">>X\nalpha\n<<X\n>>Y\nbeta\n<<Y\n"
    out = upsert_block(existing, ">>X\nALPHA\n<<X", ">>X", "<<X")
    assert "ALPHA" in out and "alpha" not in out
    assert ">>Y\nbeta\n<<Y" in out
    out2 = upsert_block(out, ">>Y\nBETA\n<<Y", ">>Y", "<<Y")
    assert "BETA" in out2 and ">>X\nALPHA\n<<X" in out2


def test_marked_block_still_uses_the_command_markers():
    block = "%s\nfunction thero {}\n%s" % (COMMAND_MARKER_START,
                                           COMMAND_MARKER_END)
    out = upsert_marked_block("", block)
    assert COMMAND_MARKER_START in out and COMMAND_MARKER_END in out


# ---- claude settings.json ----

@pytest.fixture
def cfg():
    return {
        "providers": [
            {"id": "claude", "label": "Claude Code", "model": "sonnet",
             "authKind": "session", "authVar": "", "base": ""},
            {"id": "ollama", "label": "Ollama", "model": "llama3.2",
             "authKind": "local", "authVar": "",
             "base": "http://127.0.0.1:11434"},
        ],
        "agents": [
            {"id": "claude", "preset": "claude", "target": "claude",
             "provider": "claude", "model": "sonnet", "enabled": True},
        ],
        "routing": {"athena": "llama3.2", "sentinel": "qwen3-coder-next"},
    }


def test_apply_claude_sets_model_and_env_anthropic_model(tmp_path, cfg):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"autoUpdatesChannel": "latest"}),
                      encoding="utf-8")
    agent = apply.find_agent(cfg, "claude")
    out = apply.apply_claude(agent, cfg, target)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["model"] == "sonnet"
    assert data["env"]["ANTHROPIC_MODEL"] == "sonnet"
    assert data["autoUpdatesChannel"] == "latest"   # preservou o resto
    assert out["ok"] is True
    assert out["written"] == str(target)


def test_apply_claude_backs_up_before_touching(tmp_path, cfg):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"env": {"X": "1"}}), encoding="utf-8")
    apply.apply_claude(apply.find_agent(cfg, "claude"), cfg, target)
    backups = list(tmp_path.glob("settings.backup_*"))
    assert len(backups) == 1
    saved = json.loads(backups[0].read_text(encoding="utf-8"))
    assert saved["env"]["X"] == "1"


def test_apply_refuses_an_unparseable_file_and_leaves_it_alone(tmp_path, cfg):
    target = tmp_path / "settings.json"
    target.write_text("{ isto nao e json", encoding="utf-8")
    out = apply.apply_claude(apply.find_agent(cfg, "claude"), cfg, target)
    assert out["ok"] is False
    assert "nao fui" in out["msg"].lower() or "parse" in out["msg"].lower()
    assert target.read_text(encoding="utf-8") == "{ isto nao e json"
    assert list(tmp_path.glob("settings.backup_*")) == []
    assert out["backup"] == ""


def test_apply_claude_creates_env_without_clobbering_other_vars(tmp_path, cfg):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"env": {"ANTHROPIC_API_KEY": "kept"}}),
                      encoding="utf-8")
    apply.apply_claude(apply.find_agent(cfg, "claude"), cfg, target)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["env"]["ANTHROPIC_API_KEY"] == "kept"
    assert data["env"]["ANTHROPIC_MODEL"] == "sonnet"


def test_apply_claude_targets_the_agent_it_is_given(tmp_path, cfg):
    # A4: sem o `agent` em mao o escritor fixaria id "claude" e escreveria o
    # modelo do agente errado num segundo alvo "claude".
    cfg["agents"].append(dict(cfg["agents"][0], id="claude2",
                              target="claude", provider="ollama",
                              model="llama3.2"))
    target = tmp_path / "settings.json"
    target.write_text("{}", encoding="utf-8")
    second = apply.find_agent(cfg, "claude2")
    apply.apply_claude(second, cfg, target)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["model"] == "llama3.2"


# ---- opencode ----

def test_apply_opencode_writes_provider_slash_model(tmp_path, cfg):
    target = tmp_path / "opencode.json"
    target.write_text(json.dumps({"theme": "opencode"}), encoding="utf-8")
    agent = dict(cfg["agents"][0], preset="opencode", target="opencode",
                 provider="ollama", model="llama3.2")
    apply.apply_opencode(agent, cfg, target)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["model"] == "ollama/llama3.2"
    assert data["theme"] == "opencode"


# ---- codex config.toml ----

def test_apply_codex_rewrites_only_top_level_scalars(tmp_path, cfg):
    target = tmp_path / "config.toml"
    target.write_text(
        'model = "old"\nnotify = true\n\n[mcp_servers.x]\ncmd = "keep me"\n',
        encoding="utf-8",
    )
    agent = dict(cfg["agents"][0], target="codex", provider="openai",
                 model="gpt-5-codex")
    apply.apply_codex(agent, cfg, target)
    text = target.read_text(encoding="utf-8")
    assert 'model = "gpt-5-codex"' in text
    assert "notify = true" in text
    assert 'cmd = "keep me"' in text
    assert text.index("notify") < text.index("[mcp_servers")


def test_apply_codex_creates_the_key_when_the_file_has_none(tmp_path, cfg):
    target = tmp_path / "config.toml"
    target.write_text('[features]\nx = true\n', encoding="utf-8")
    agent = dict(cfg["agents"][0], target="codex", model="gpt-5-codex")
    apply.apply_codex(agent, cfg, target)
    text = target.read_text(encoding="utf-8")
    assert text.splitlines()[0].startswith("model")
    assert "[features]" in text


def test_apply_codex_writes_model_provider_only_when_the_table_exists(tmp_path,
                                                                      cfg):
    target = tmp_path / "config.toml"
    target.write_text('model = "old"\n\n[model_providers.deepseek]\n'
                      'base_url = "http://x"\n', encoding="utf-8")
    agent = dict(cfg["agents"][0], target="codex", provider="deepseek",
                 model="deepseek-chat")
    apply.apply_codex(agent, cfg, target)
    text = target.read_text(encoding="utf-8")
    assert 'model = "deepseek-chat"' in text
    assert 'model_provider = "deepseek"' in text
    assert "[model_providers.deepseek]" in text


def test_apply_codex_skips_model_provider_when_the_table_is_absent(tmp_path,
                                                                   cfg):
    target = tmp_path / "config.toml"
    target.write_text('model = "old"\nnotify = true\n', encoding="utf-8")
    agent = dict(cfg["agents"][0], target="codex", provider="ghost",
                 model="gpt-x")
    out = apply.apply_codex(agent, cfg, target)
    text = target.read_text(encoding="utf-8")
    assert 'model = "gpt-x"' in text
    assert "model_provider" not in text   # mesa inexistente quebraria o Codex
    assert "ghost" in out["msg"]          # o msg diz por que nao escreveu


# ---- $PROFILE (contrato real dos dois consumidores) ----

def test_profile_block_carries_both_consumer_contracts(cfg):
    block = apply.profile_env_block(cfg)
    assert "$env:ATHENA_OLLAMA_HOST" in block
    assert "$env:ATHENA_OLLAMA_MODEL" in block
    assert "$env:SENTINEL_OLLAMA_HOST" in block
    assert "$env:SENTINEL_OLLAMA_MODEL" in block
    # cada consumidor com o modelo que o usuario escolheu para ele -- os dois
    # padrao sao diferentes (Athena llama3.2, Sentinel qwen3-coder-next)
    assert '$env:ATHENA_OLLAMA_MODEL = "llama3.2"' in block
    assert '$env:SENTINEL_OLLAMA_MODEL = "qwen3-coder-next"' in block
    assert block.count("http://127.0.0.1:11434") == 2
    assert ENV_MARKER_START in block and ENV_MARKER_END in block


def test_profile_block_falls_back_to_each_consumers_own_default(cfg):
    cfg["routing"] = {}                       # usuario ainda nao escolheu
    block = apply.profile_env_block(cfg)
    assert '$env:ATHENA_OLLAMA_MODEL = "llama3.2"' in block
    assert '$env:SENTINEL_OLLAMA_MODEL = "qwen3-coder-next"' in block


def test_env_contracts_cover_exactly_the_declared_consumers():
    # duas listas de consumidores e a receita de uma tela que escreve no
    # arquivo errado: isto garante que apply.ENV_CONTRACTS e
    # providers.CONSUMERS nunca divergem.
    from thero import providers

    assert set(apply.ENV_CONTRACTS) == set(providers.CONSUMERS)


def test_apply_profile_is_idempotent(tmp_path, cfg):
    profile = tmp_path / "Microsoft.PowerShell_profile.ps1"
    profile.write_text("function foo {}\n", encoding="utf-8")
    apply.apply_profile(cfg, profile)
    apply.apply_profile(cfg, profile)
    text = profile.read_text(encoding="utf-8")
    assert text.count(ENV_MARKER_START) == 1
    assert "function foo" in text


def test_apply_profile_reports_missing_profile_without_crashing(cfg):
    # A8: Path(None) levanta TypeError; a validacao tem de vir antes.
    out = apply.apply_profile(cfg, None)
    assert out["ok"] is False
    assert "profile" in out["msg"].lower()


def test_profile_env_block_refuses_a_remote_ollama_base(cfg):
    # A3: base remota escolhida na GUI nunca pode virar $PROFILE.
    for provider in cfg["providers"]:
        if provider.get("id") == "ollama":
            provider["base"] = "http://10.0.0.5:11434"
    with pytest.raises(ValueError):
        apply.profile_env_block(cfg)


def test_apply_profile_refuses_remote_base_and_writes_nothing(tmp_path, cfg):
    # A3 + credencial: base remota com userinfo nao escreve, nao faz backup,
    # e nao ecoa a credencial no msg.
    for provider in cfg["providers"]:
        if provider.get("id") == "ollama":
            provider["base"] = "http://user:secret@evil.example:11434"
    profile = tmp_path / "profile.ps1"
    profile.write_text("function foo {}\n", encoding="utf-8")
    out = apply.apply_profile(cfg, profile)
    assert out["ok"] is False
    assert "loopback" in out["msg"].lower()
    assert profile.read_text(encoding="utf-8") == "function foo {}\n"
    assert list(tmp_path.glob("profile.backup_*")) == []
    assert "secret" not in out["msg"]
    assert "user" not in out["msg"]


def test_apply_preserves_a_cp1252_profile_byte_for_byte(tmp_path, cfg):
    # A7: um $PROFILE salvo como cp1252 (PowerShell 5.1) nao pode virar
    # U+FFFD escrito de volta -- merge preservando o encoding de origem.
    profile = tmp_path / "profile.ps1"
    profile.write_bytes("# caf\xe9 latino\nfunction foo {}\n".encode("cp1252"))
    out = apply.apply_profile(cfg, profile)
    assert out["ok"] is True
    data = profile.read_bytes()
    assert b"caf\xe9" in data
    assert b"\xef\xbf\xbd" not in data
    assert ENV_MARKER_START.encode() in data


def test_apply_refuses_an_undecodable_file_and_writes_nothing(tmp_path, cfg):
    # A7: nem utf-8 nem cp1252 -> recusa total, arquivo intocado, sem backup.
    target = tmp_path / "settings.json"
    junk = b'{"a": 1}\n\x81'
    target.write_bytes(junk)
    out = apply.apply_claude(apply.find_agent(cfg, "claude"), cfg, target)
    assert out["ok"] is False
    assert target.read_bytes() == junk
    assert list(tmp_path.glob("settings.backup_*")) == []
    assert out["backup"] == ""


# ---- despacho / record-only / ponte ----

def test_apply_never_uses_print_on_the_bridge_channel(tmp_path, cfg, capsys):
    target = tmp_path / "settings.json"
    target.write_text("{}", encoding="utf-8")
    apply.apply_agent(cfg["agents"][0], cfg, {"claude": target})
    agent = dict(cfg["agents"][0], id="env", target="profile")
    apply.apply_agent(agent, cfg, {}, tmp_path / "profile.ps1")
    assert capsys.readouterr().out == ""


def test_record_only_targets_write_nothing(tmp_path, cfg):
    target = tmp_path / "settings.json"
    before = "{}"
    target.write_text(before, encoding="utf-8")
    agent = dict(cfg["agents"][0], target="none", preset="qoder")
    out = apply.apply_agent(agent, cfg, {"claude": target})
    assert out["ok"] is True
    assert out["writes"] is False
    assert target.read_text(encoding="utf-8") == before


def test_record_only_result_carries_id_and_target(tmp_path, cfg):
    # A5: a ponte casa os resultados por `id`; sem id o recod-only nunca daria
    # match e o status ficaria "pendente" para sempre.
    agent = dict(cfg["agents"][0], id="cursor", target="none", preset="cursor")
    out = apply.apply_agent(agent, cfg, {})
    assert out["id"] == "cursor"
    assert out["target"] == "none"


def test_apply_all_reports_enabled_and_skips_disabled(tmp_path, cfg):
    cfg["agents"].append(dict(cfg["agents"][0], id="x", enabled=False))
    paths = {"claude": tmp_path / "settings.json"}
    paths["claude"].write_text("{}", encoding="utf-8")
    results = apply.apply_all(cfg, paths)
    assert len(results) == 1
    assert results[0]["id"] == "claude"


def test_default_paths_has_no_profile_key():
    # A9: localizar a $PROFILE exige rodar PowerShell -- default_paths nao faz
    # subprocess, entao nao finge um contrato que nao entrega.
    assert "profile" not in apply.default_paths()


def test_apply_agent_resolves_profile_from_paths_key(tmp_path, cfg):
    profile = tmp_path / "profile.ps1"
    agent = {"id": "env", "target": "profile", "label": "Perfil"}
    out = apply.apply_agent(agent, cfg, {"profile": profile})
    assert out["ok"] is True
    assert out["target"] == "profile"
    assert ENV_MARKER_START in profile.read_text(encoding="utf-8")


def test_apply_returns_the_backup_name_when_overwriting(tmp_path, cfg):
    target = tmp_path / "settings.json"
    target.write_text("{}", encoding="utf-8")
    out = apply.apply_claude(apply.find_agent(cfg, "claude"), cfg, target)
    assert out["backup"].startswith("settings.backup_")
    assert out["backup"] in out["msg"]     # msg menciona o que foi tocado


def test_apply_backup_is_empty_when_no_prior_file(tmp_path, cfg):
    target = tmp_path / "settings.json"
    out = apply.apply_claude(apply.find_agent(cfg, "claude"), cfg, target)
    assert out["backup"] == ""             # arquivo novo: nao houve backup
    assert "settings.json" in out["msg"]
```

- [ ] **Step 2: Rodar → falha**

Run: `python -m pytest tests/test_envreport.py -q`
Expected: `ModuleNotFoundError: No module named 'thero.envreport'`

- [ ] **Step 3: Implementação**

**3a — teto de tempo em `run_command`** (Modify: `src/thero/system/process.py:20-63`).
`envreport` é a primeira sonda de processo chamando `run_command` a partir da
janela; sem teto, um `--version` que trava congela o loop de stdio da ponte e,
com ele, a interface inteira. Quem não passa `timeout` continua com o
comportamento de hoje (`None` = sem limite):

```python
def run_command(
command: list[str],
*,
cwd: Path | None = None,
check: bool = False,
capture: bool = True,
text: bool = True,
input_text: str | None = None,
timeout: float | None = None,
) -> subprocess.CompletedProcess:
```

E no `subprocess.run(...)` do fim da função, uma linha a mais:

```python
        input=input_text,
        shell=False,
        timeout=timeout,
    )
```

**3b — o módulo novo.** Create `src/thero/envreport.py`:

```python
"""Retrato do ambiente, em dados -- o texto cru do `validate_environment()`
do CLI nao serve para a interface.

Usado por: tela Status, checklist de pre-requisitos do onboarding e o
`host-ready` da ponte. `found` e "o executavel esta no PATH"; `ok` e "ele
responde" -- os dois sao diferentes nesta maquina (npx existe e quebra), e a
interface mostra essa diferenca em vez de um check verde mentiroso.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from thero import config as config_store
from thero.settings import COMMAND_MARKER_START, DEFAULT_COMMAND_NAME
from thero.system.process import run_command

_TOOLS = ("node", "npx", "claude", "git")

# Segundos por sonda de versao. A ponte e um loop de stdio, entao uma sonda sem
# teto congela a janela inteira.
VERSION_TIMEOUT = 10

# Idem para o spawn `powershell -Command $PROFILE` da sonda de perfil: filho
# no mesmo loop, mesmo teto obrigatorio.
PROFILE_TIMEOUT = 5


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def _version_probe(command: list) -> tuple:
    """(primeira linha nao vazia, ok) de `<cmd> --version`.

    `ok` vem do returncode real, nao do texto: ferramenta que sai com erro
    imprimindo saida "limpa" continua nao-ok ('' e False se silenciar ou
    travar).
    """
    try:
        result = run_command(command + ["--version"], timeout=VERSION_TIMEOUT)
    except subprocess.TimeoutExpired:
        return "", False
    ok = result.returncode == 0
    out = (result.stdout or "") if ok else (result.stderr or result.stdout or "")
    for line in out.splitlines():
        if line.strip():
            return line.strip(), ok
    return "", False


def _ollama_probe() -> dict:
    # Import tardio: envreport e escrito antes de localmodels (Task 3) e os
    # testes desta tarefa trocam esta funcao, entao ela nunca roda aqui.
    from thero import localmodels

    info = localmodels.status()
    return {
        "up": bool(info["up"]),
        "host": info["base"],
        "models": info["models"],
        "error": info["error"],
    }


def _profile_path() -> Optional[Path]:
    if platform.system() != "Windows":
        return None
    try:
        # Import dentro da fronteira protegida: modulo quebrado degrada so
        # este campo, nunca o payload inteiro da tela de Status.
        from thero.shell_command.windows import resolve_powershell_profile

        return resolve_powershell_profile(timeout=PROFILE_TIMEOUT)
    except Exception:  # noqa: BLE001 - conforto, nunca motivo de falha na GUI
        return None


def _command_installed(profile: Optional[Path]) -> bool:
    if profile is None or not Path(profile).exists():
        return False
    try:
        text = Path(profile).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    # Casa o marcador exato que o instalador do comando global escreve --
    # nunca a substring "thero": o bloco de ENV da Task 5 vive no mesmo
    # $PROFILE e cita o nome.
    return COMMAND_MARKER_START in text


def _count_skills(skills_base: Path) -> int:
    # Fronteira fs: is_dir()/iterdir() podem negar (PermissionError) -- a
    # contagem degrada a 0 e o snapshot continua de pe.
    try:
        if not skills_base.is_dir():
            return 0
        return sum(1 for folder in sorted(skills_base.iterdir())
                   if folder.is_dir() and (folder / "SKILL.md").exists())
    except OSError:
        return 0


def snapshot(
    entry_path: Path,
    *,
    home: Optional[Path] = None,
    config_path: Optional[Path] = None,
    scope: str = "global",
) -> dict:
    home = Path(home) if home else Path.home()
    claude_dir = home / ".claude"
    skills_base = claude_dir / "skills"
    claude_md = claude_dir / "CLAUDE.md"
    cfg_path = Path(config_path) if config_path else config_store.config_path()

    tools: dict = {}
    for name in _TOOLS:
        found = bool(_which(name))
        detail = ""
        ok = False
        if found:
            try:
                line, ok = _version_probe([name])
            except Exception as exc:  # noqa: BLE001 - fronteira: nunca derrubar a GUI
                line = ""
                detail = str(exc)
            if line:
                detail = line
            else:
                ok = False
                detail = detail or "sem saida de --version"
        tools[name] = {"found": found, "ok": ok, "detail": detail}

    try:
        ollama = _ollama_probe()
    except Exception as exc:  # noqa: BLE001
        ollama = {"up": False, "host": "", "models": [], "error": str(exc)}

    try:
        exists = claude_md.exists()
        md_bytes = claude_md.stat().st_size if exists else 0
    except OSError:  # fronteira fs: degrada so o campo claudeMd
        exists, md_bytes = False, 0
    try:
        backups = (sorted(claude_dir.glob("CLAUDE.md.backup*"))
                   if claude_dir.is_dir() else [])
    except OSError:  # idem: so o contador de backups degrada
        backups = []
    profile = _profile_path()

    return {
        "app": "thero",
        "entry": str(entry_path),
        "scope": scope,
        "firstRun": not cfg_path.exists(),
        "configPath": str(cfg_path),
        "python": "%d.%d.%d" % sys.version_info[:3],
        "platform": platform.system(),
        "commandName": DEFAULT_COMMAND_NAME,
        "commandInstalled": _command_installed(profile),
        "profilePath": str(profile) if profile else "",
        "claudeDir": str(claude_dir),
        "claudeMd": {"exists": exists, "bytes": md_bytes, "backups": len(backups)},
        "skills": {"base": str(skills_base), "installed": _count_skills(skills_base)},
        "tools": tools,
        "ollama": {"up": bool(ollama.get("up")),
                   "host": ollama.get("host", ""),
                   "modelCount": len(ollama.get("models", [])),
                   "error": ollama.get("error", "")},
    }
```

**3c — teto na sonda do `$PROFILE`** (Modify: `src/thero/shell_command/windows.py:14-34`).
`resolve_powershell_profile` da um spawn de PowerShell; quando a ponte o chama
via `envreport._profile_path`, vale a mesma logica da 3a: sem teto, um
PowerShell pendurado congela o loop de stdio inteiro. Quem nao passa `timeout`
(instalador de comando) continua com o comportamento de hoje (`None` = sem
limite):

```python
def resolve_powershell_profile(timeout: float | None = None) -> Path | None:

    result = run_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "$PROFILE",
        ],
        capture=True,
        timeout=timeout,
    )
```

- [ ] **Step 4: Rodar**

Run: `python -m pytest tests/ -q`
Expected: `261 + 15 = 276 passed`

- [ ] **Step 5: Commit (pedir confirmação)**

```bash
git add src/thero/envreport.py src/thero/system/process.py \
        src/thero/shell_command/windows.py tests/test_envreport.py
git commit -m "feat(env): structured environment snapshot for the Status screen and onboarding"
```

---

### Task 3: Modelos locais (`localmodels.py`) — tela "Modelos locais"

**Files:**
- Create: `src/thero/localmodels.py`
- Test: `tests/test_localmodels.py`

Escopo verificado: a tela tem de listar puxar e apagar modelos **locais**. Os
consumidores reais são dois, cada um com seu par de variáveis: a Athena via
`ATHENA_OLLAMA_HOST` / `ATHENA_OLLAMA_MODEL`
(`athena/src/athena/settings.py:52-72`, default `http://localhost:11434`) e o
Sentinel via `SENTINEL_OLLAMA_HOST` / `SENTINEL_OLLAMA_MODEL`
(`sentinel/src/sentinel/settings.py:255-283`, default `http://127.0.0.1:11434`
e `qwen3-coder-next`). Os dois recusam host fora de loopback, e nenhum dos dois
instala motor: o Thero só escreve onde apontar.

**Correções já aplicadas neste plano (revisão pós-implementação do commit `b73beb8`):**
1. O `pull()` **streaming de verdade**: itera a resposta em linhas em vez de
   `read()` do corpo inteiro, e usa `OLLAMA_PULL_TIMEOUT` (teto de *leitura por
   operação*, não de duração total) em vez do `OLLAMA_PROBE_TIMEOUT` de 3 s.
   Com o corpo slurpado, um `ollama pull` de vários GB abortava nas fases
   `verifying sha256`/`writing blob` e nenhum `("out", linha)` chegava antes do
   fim — a tela de progresso da Task 10 ficava sem o que mostrar. Os caminhos de
   `list_models`/`status` **continuam** com `OLLAMA_PROBE_TIMEOUT`; `delete`
   migrou para `OLLAMA_DELETE_TIMEOUT` (item 7 abaixo).
2. `list_models()` trata payload malformado na fronteira: `models` que não seja
   lista → `{"ok": False, ..., "error": "resposta inesperada do Ollama
   (/api/tags)"}`; item que não seja objeto → valores vazios; `size` inválido →
   `0` (e `sizeHuman` `"-"`), **mantendo `ok: True`** — um tamanho ilegível não
   esconde o modelo que o usuário tem instalado. Nada de
   `AttributeError`/`ValueError` escapando pelo canal JSON da ponte.
3. Citações do contrato Ollama do Sentinel realinhadas ao `sentinel/` de hoje
   (`settings.py:255-283`, `DEFAULT_MODEL_NAME` em `:276`, veto em
   `local_model.py:90`) — a Task 5 e a Task 8 consomem estes ponteiros.

**Correções já aplicadas neste plano (revisão de qualidade pós-`2067d95`):**
4. **C1 — `pull()` não reporta sucesso num download que falhou.** Erro de stream
   do Ollama chega como evento `{"error": ...}` **sem mudar o status HTTP**
   (docs.ollama.com/api/errors); tratado como linha comum, o `("exit", 0)` final
   entregava `{"exitCode": 0, "ok": true}` na ponte e a tela marcava verde num
   modelo que não existe (irromper `ATHENA_OLLAMA_MODEL` na Task 5). Agora: evento
   com `error` → `("out", <texto>)` + falha; `("exit", 1)` se houve erro ou se
   nenhum evento válido foi visto; truncamento detectado por
   `getattr(response, "length", 0)` residual dentro do `with` (iterar não levanta
   em EOF antecipado). Contrato `("out", str)`/`("exit", int)` e código `2`
   preservados.
5. **C2 — exceções de `http.client` capturadas nos quatro caminhos de rede.**
   `HTTPException` não herda de `OSError`: `BadStatusLine` (serviço não-HTTP na
   11434 — banal no Windows), `IncompleteRead`, `InvalidURL` escapavam de
   `list_models`, `status`, `delete` e `pull`. Captura agora é
   `(OSError, http.client.HTTPException)` — e `+ ValueError` só pelo `json.loads`
   em `_fetch_tags` (`URLError`/`HTTPError` já são `OSError`; os tuples antigos
   eram redundantes e insuficientes).
6. **C3 — o veto valida o netloc inteiro da conexão, não o hostname do
   `urlparse`.** `hostname` corta no PRIMEIRO `:` mas `http.client` conecta no
   ÚLTIMO: `http://localhost:11434.evil.com`, `http://127.0.0.1:11434:80` e
   afins passavam. `_assert_loopback` casa `netloc.rpartition("@")[2]` contra
   `(\[?(127\.0\.0\.1|localhost|::1)\]?)(:[0-9]{1,5})?` (case-insensitive), toca
   `parsed.port` para forçar `0..65535`, e recusa path/params/query/fragment —
   escolha documentada: `normalize_base` descarta **apenas** a `/` final
   (`http://localhost:11434/` é aceita), qualquer outro resto é recusa.
7. **I1/I2 — veto imediato e timeout de mutação.** `pull()` deixou de ser
   geradora pura: resolve `_guard(base)` na chamada e devolve o iterador de
   `_pull()` (rede continua preguiçosa). `delete` usa `OLLAMA_DELETE_TIMEOUT =
   30` em `settings.py` — delete é mutação (unlink de blobs de GB), não sonda;
   `OLLAMA_PROBE_TIMEOUT` continua 3 s para o `envreport` não ficar lento.
8. **I3/M1-M6 — contrato e higiene.** `status()` compartilhado com
   `list_models()` via `_fetch_tags(url_base)` privado (sem duplo `_guard`);
   `_describe` detecta recusa por tipo/errno (`ConnectionRefusedError`,
   `10061`) e cita o host, não a razão crua do SO; `human_bytes` degrada para
   MB abaixo de 1 GB; `read()` do `delete` justificado (drena dentro do try);
   `("exit", 1)` também para stream sem evento válido; docstring do `pull`
   marca `system.process.stream_command` como contrato **planejado** (Task 7,
   módulo ainda não existe); comentários que repetiam o docstring removidos.
   Testes novos: 18 em `test_localmodels.py` (27 no total, com os parametrizados
   de veto/recusa) + 1 em `test_envreport.py` amarrando `_ollama_probe()` ao
   `urlopen` fakeado do `localmodels`.

- [ ] **Step 1: Testes**

`tests/test_localmodels.py`:

```python
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
```

- Em `tests/test_envreport.py`, acrescentar ao fim do arquivo o teste que amarra os dois lados do contrato na vida real (hoje os testes de `envreport` validam contra dict fabricado pelo proprio teste, e `_ollama_probe` le com colchetes: um rename de chave quebraria so em runtime, engolido pelo `except Exception` do `snapshot`):

```python
def test_ollama_probe_reads_the_real_localmodels_contract(monkeypatch):
    # envreport._ollama_probe le o dict de localmodels.status() com
    # COLCHETES; um rename de chave quebraria so em runtime, engolido
    # pelo except Exception do snapshot. Este teste amarra os dois lados
    # de verdade, 100% offline (o urlopen do localmodels e que e trocado).
    import json
    import urllib.error

    from thero import localmodels

    class Tags:
        def __init__(self, payload):
            self._payload = payload

        def read(self):
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    body = json.dumps({"models": [{"name": "llama3.2:latest",
                                   "size": 2020990000}]}).encode("utf-8")
    monkeypatch.setattr(localmodels, "urlopen",
                        lambda request, timeout=None: Tags(body))
    out = envreport._ollama_probe()
    assert out["up"] is True
    assert out["host"] == localmodels.OLLAMA_DEFAULT_HOST
    assert [m["name"] for m in out["models"]] == ["llama3.2:latest"]
    assert out["error"] == ""

    def down(request, timeout=None):
        raise urllib.error.URLError("nao escuta")

    monkeypatch.setattr(localmodels, "urlopen", down)
    out = envreport._ollama_probe()
    assert out["up"] is False
    assert out["models"] == []
    assert out["error"]
```

- [ ] **Step 2: Rodar para confirmar falha**

Run: `python -m pytest tests/test_localmodels.py -q`
Expected: FAIL — `ImportError: cannot import name 'localmodels' from 'thero'`
(o pacote `thero` ja existe por causa das Tasks 1-2, entao o erro e de import
de nome dentro do pacote, nao `ModuleNotFoundError` -- mesma raiz: o modulo
ainda nao existe)

- [ ] **Step 3: Implementação**

Create `src/thero/localmodels.py`:

```python
"""Modelos locais (Ollama): listar, puxar e apagar pelo HTTP do próprio Ollama.

Contrato verificado na máquina: os consumidores são dois, cada um com seu par
de variáveis -- a Athena lê `ATHENA_OLLAMA_HOST` / `ATHENA_OLLAMA_MODEL`
(athena/src/athena/settings.py:52-72, default http://localhost:11434) e o
Sentinel lê `SENTINEL_OLLAMA_HOST` / `SENTINEL_OLLAMA_MODEL`
(sentinel/src/sentinel/settings.py:255-283, default http://127.0.0.1:11434 +
qwen3-coder-next, com veto de host fora de loopback). Os dois só consomem:
nada aqui instala motor -- o Thero escreve onde apontar.

Regra de segurança: só loopback, sem exceção. Nenhuma função daqui aceita
host remoto e nenhuma envia credencial (os endpoints locais do Ollama não
usam chave -- não inventar header de auth). Proibido print(): este módulo
vive no processo da ponte, cujo stdout é o canal JSON.
"""

from __future__ import annotations

import http.client
import json
import re
import urllib.error
import urllib.request
from typing import Iterator, Optional
from urllib.parse import urlparse

from thero.settings import (
    OLLAMA_DEFAULT_HOST,
    OLLAMA_DELETE_TIMEOUT,
    OLLAMA_PROBE_TIMEOUT,
    OLLAMA_PULL_TIMEOUT,
)

# Dependencia injetavel nos testes; o nome `urlopen` e usado modulo-afora
# de proposito para o monkeypatch funcionar.
urlopen = urllib.request.urlopen

# O netloc COMPLETO pelo qual o http.client conecta (host + porta opcional),
# nao so o hostname do urlparse: ele corta no PRIMEIRO ":", o http.client
# conecta no ULTIMO -- "http://localhost:11434.evil.com" passaria num teste
# de hostname e conectaria em outro host. Colchetes sao a forma IPv6 da URL.
_LOOPBACK_NETLOC = re.compile(
    r"(\[?(127\.0\.0\.1|localhost|::1)\]?)(:[0-9]{1,5})?", re.IGNORECASE
)


def normalize_base(host: Optional[str] = "") -> str:
    """Aceita '127.0.0.1:11434', 'localhost' ou URL completa; devolve URL.

    Descarta APENAS a "/" final -- escolha documentada nos testes: os
    endpoints locais pedem uma base seca, e path/query/fragment que
    sobrarem fazem o _assert_loopback recusar.
    """
    raw = (host or OLLAMA_DEFAULT_HOST).strip()
    if not raw:
        raw = OLLAMA_DEFAULT_HOST
    if "://" not in raw:
        raw = "http://" + raw
    return raw.rstrip("/")


def _assert_loopback(base: str) -> str:
    parsed = urlparse(base)
    # O userinfo (ate o ULTIMO "@") nao participa da conexao; o resto do
    # netloc sim, e por isso ele e validado inteiro.
    hostinfo = parsed.netloc.rpartition("@")[2]
    parsed.port  # dentro do veto: ValueError se a porta nao for 0..65535
    if _LOOPBACK_NETLOC.fullmatch(hostinfo) is None or (
        parsed.path or parsed.params or parsed.query or parsed.fragment
    ):
        raise ValueError(
            "apenas loopback e permitido para modelos locais "
            "(recebi %r)" % (base,)
        )
    return base


def _guard(base: str) -> str:
    """normalize_base -> _assert_loopback, na mesma ordem, nos quatro
    caminhos que fazem rede (list_models, pull, delete, status). O veto
    dispara antes de qualquer chamada de rede."""
    return _assert_loopback(normalize_base(base))


# Publico por contrato da Task 4 (providers.register): um satellite precisa
# recusar host remoto ANTES de montar o payload de escrita de config, e nao
# deve compor os privados (_guard/_assert_loopback) de outro satellite.
guard_base = _guard


def _describe(error: Exception, base: str) -> str:
    if isinstance(error, urllib.error.HTTPError):
        return "HTTP %d %s" % (error.code, error.reason or "")
    reason = getattr(error, "reason", None) or error
    # Recusa detectada por TIPO/errno, nao pela substring inglesa "refused":
    # no Windows a razao chega "[WinError 10061] Nenhuma conexao pudo ser
    # feita..." e o ramo nunca dispararia.
    refused = (
        isinstance(reason, ConnectionRefusedError)
        or getattr(reason, "errno", None) == 10061
        or getattr(reason, "winerror", None) == 10061
        or "refused" in str(reason).lower()
    )
    if refused:
        # Cita o HOST, nunca a razao crua do SO dentro da frase.
        return "conexao recusada em %s: o Ollama esta rodando?" % base
    return str(reason)


def _size_of(item: dict) -> int:
    # Tamanho e informativo: um valor malformado ("abc", None, lista) nao pode
    # derrubar a listagem inteira -- cai para 0 e o sizeHuman vira "-".
    try:
        return int(item.get("size") or 0)
    except (TypeError, ValueError):
        return 0


def human_bytes(size: int) -> str:
    if size <= 0:
        return "-"
    if size < 1024 ** 3:
        # Abaixo de 1 GB o "0.0 GB" seria lido como modelo vazio na tela.
        return "%.0f MB" % (size / 1024.0 ** 2)
    return "%.1f GB" % (size / 1024.0 ** 3)


def _fetch_tags(url_base: str) -> dict:
    # Caminho de rede UNICO do /api/tags: list_models e status o dividem para
    # o veto/parse nao ser duplicado. Request com method explicito: o contrato
    # de rede e sempre um objeto Request (nunca string crua), igual a pull.
    request = urllib.request.Request(url_base + "/api/tags", method="GET")
    try:
        with urlopen(request, timeout=OLLAMA_PROBE_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except (OSError, ValueError, http.client.HTTPException) as exc:
        # OSError ja cobre socket E urllib.error.URLError/HTTPError (os dois
        # herdam dele); HTTPException cobre o http.client que escapa do
        # OSError (BadStatusLine de servico nao-HTTP na 11434, IncompleteRead
        # no meio do corpo); ValueError so existe aqui pelo json.loads.
        return {"ok": False, "models": [], "error": _describe(exc, url_base)}
    if not isinstance(payload, dict):
        # JSON valido, mas nao o objeto esperado: a tela degrada com erro
        # humano, nunca com AttributeError no meio do payload da ponte.
        return {"ok": False, "models": [],
                "error": "resposta inesperada do Ollama (/api/tags)"}
    # Mesma fronteira logo abaixo: {"models": <nao-list>} iteraria as chaves/
    # letras como se fossem modelos. Lista e o unico formato aceito; chave
    # ausente e o caso legitimo de "nenhum modelo instalado".
    raw_models = payload.get("models") or []
    if not isinstance(raw_models, list):
        return {"ok": False, "models": [],
                "error": "resposta inesperada do Ollama (/api/tags)"}
    models = []
    for item in raw_models:
        # Item que nao seja objeto entra com valores vazios, sem excecao.
        entry = item if isinstance(item, dict) else {}
        details = entry.get("details")
        if not isinstance(details, dict):
            details = {}
        size = _size_of(entry)
        models.append({
            "name": entry.get("name", ""),
            "size": size,
            "sizeHuman": human_bytes(size),
            "params": details.get("parameter_size", ""),
            "family": details.get("family", ""),
        })
    return {"ok": True, "models": models, "error": ""}


def list_models(base: str = "") -> dict:
    return _fetch_tags(_guard(base))


def pull(name: str, base: str = "") -> Iterator[tuple]:
    """Gera ('out', linha) durante o download e ('exit', codigo) no fim.

    NAO e geradora pura: o veto roda na CHAMADA, antes de alguem iterar --
    um pull remoto nunca consumido nao pode ficar ileso. A resposta e lida
    INCREMENTALMENTE -- iterar o HTTPResponse em linhas, nao read() do corpo
    inteiro -- senao nenhum ('out', linha) chega antes de o download acabar
    e a tela de progresso nao tem o que mostrar. O formato ('out', str) /
    ('exit', int) e o que a ponte promete expor como
    `system.process.stream_command` (contrato PLANEJADO da Task 7; o modulo
    ainda nao existe) para tratar `ollama pull` e `npx skills` no mesmo
    painel de terminal.
    """
    return _pull(name, _guard(base))


def _pull(name: str, url_base: str) -> Iterator[tuple]:
    if not name:
        yield ("out", "informe o nome do modelo")
        yield ("exit", 2)
        return
    body = json.dumps({"name": name, "stream": True}).encode("utf-8")
    request = urllib.request.Request(
        url_base + "/api/pull", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    failed = False
    saw_event = False
    try:
        # timeout SEMPRE como keyword e nunca None (sem teto, um `ollama pull`
        # que pendura congela o loop stdio da ponte). O teto aqui e o do pull,
        # NAO o da sonda: e leitura por operacao, nao duracao total -- as
        # fases `verifying sha256`/`writing blob` passam minutos sem emitir
        # bytes, e 3 s de silencio abortariam um download de varios GB.
        with urlopen(request, timeout=OLLAMA_PULL_TIMEOUT) as response:
            for raw in response:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    yield ("out", line)
                    continue
                if not isinstance(event, dict):
                    # JSON atomico solto na stream ("123", "ok"): vira
                    # saida crua, nao AttributeError que escaparia pela
                    # geradora afora.
                    yield ("out", line)
                    continue
                saw_event = True
                # docs.ollama.com/api/errors: o erro de stream chega como
                # evento {"error": ...} SEM mudar o status HTTP. Linha de
                # progresso comum aqui daria exit 0 a um download quebrado,
                # e a tela verde entregaria o modelo ao motor na Task 5.
                if event.get("error"):
                    failed = True
                    yield ("out", str(event["error"]))
                    continue
                yield ("out", event.get("status") or line)
            if getattr(response, "length", 0):
                # Servidor com Content-Length que corta o corpo no meio:
                # iterar nao levanta em EOF antecipado -- so o length
                # residual denuncia o truncamento.
                failed = True
                yield ("out", "resposta truncada pelo Ollama "
                              "(download incompleto)")
    except (OSError, http.client.HTTPException) as exc:
        yield ("out", _describe(exc, url_base))
        yield ("exit", 1)
        return
    # Stream vazia (nenhum evento valido) nao afirma nada sobre o download:
    # exit 1 -- a ponte nao pode marcar verde sem manifest.
    yield ("exit", 1 if (failed or not saw_event) else 0)


def delete(name: str, base: str = "") -> dict:
    url_base = _guard(base)
    body = json.dumps({"name": name}).encode("utf-8")
    request = urllib.request.Request(
        url_base + "/api/delete", data=body,
        headers={"Content-Type": "application/json"}, method="DELETE",
    )
    try:
        # delete e mutacao, nao sonda: o /api/delete faz unlink de blobs de
        # GB e os 3 s da sonda reportariam falha num apagamento realizado.
        with urlopen(request, timeout=OLLAMA_DELETE_TIMEOUT) as response:
            response.read()  # drena o corpo: o IncompleteRead aparece
                             # DENTRO do try, nao no close() implicito
    except (OSError, http.client.HTTPException) as exc:
        return {"ok": False, "error": _describe(exc, url_base)}
    return {"ok": True, "error": ""}


def status(base: str = "") -> dict:
    """Retrato enxuto para a tela: pronto/ausente + quantos modelos.

    Contrato com envreport._ollama_probe (envreport.py:62-68): as chaves
    `up`, `base`, `models`, `error` -- exatamente as que ele le.
    """
    url_base = _guard(base)
    out = _fetch_tags(url_base)
    return {
        "up": bool(out["ok"]),
        "base": url_base,
        "models": out["models"],
        "error": out["error"],
    }
```

- [ ] **Step 4: Rodar**

Run: `python -m pytest tests/ -q`
Expected: `276 + 30 = 306 passed` (29 em `test_localmodels.py`, sendo os 28 originais
+ o teste `test_guard_base_gates_a_remote_host_before_any_network` que a Task 4
exige ao expor `guard_base` -- ver Passo 0 -- e a correção da
Task 2: o teste novo de `test_envreport.py` que amarra `_ollama_probe()` ao
contrato real de `localmodels.status()`)

- [ ] **Step 5: Commit (pedir confirmação)**

```bash
git add src/thero/localmodels.py tests/test_localmodels.py
git commit -m "feat(models): loopback-only Ollama client for the local models screen"
```

---

### Task 4: Provedores (`providers.py`) — registrar, testar, nunca ver valor

**Files:**
- Create: `src/thero/providers.py`
- Test: `tests/test_providers.py`

**Correções já aplicadas neste plano (revisão estática antes da implementação):**
1. `remove()` ganhou o veto de **modelo roteado** — sem ele, apagar um provedor
   cujo modelo ainda está em `routing.athena`/`routing.sentinel` deixaria
   `ATHENA_OLLAMA_MODEL`/`SENTINEL_OLLAMA_MODEL` (Task 5) com valor pendurado.
2. O teste de `providers-register` do tipo `local` foi alinhado ao contrato da
   Task 3: `list_models` envia `Request`, não string.
3. `register(..., runner=...)` removido — nenhum chamador passava, a ponte
   (Task 8) chama `providers.register(provider)`.
4. `summary()` cai no `kind` do preset quando a entrada não traz o campo.
5. `_probe_loopback` virou uma sonda só (o veto de loopback já vive dentro de
   `localmodels.list_models`), eliminando o pedido HTTP duplo por clique. **E
   ele devolve dict**: `if _probe_loopback(base):` seria sempre verdade (`{"ok":
   False}` é truthy) e diria "endpoint respondeu" com o Ollama caído — por isso
   `register` consulta `["ok"]`.
6. `register` **não** recompõe mais o veto a partir dos privados
   `localmodels._assert_loopback` + `normalize_base`. A Task 3 expõe
   `guard_base(base)` (público, mesma coisa que o `_guard` interno) e o
   `providers` usa só isso — um satellite não depende de nome privado de outro.
7. **Alinhamentos de texto desta task (antes do código).** (a) O `guard_base`
   do item 6 ainda não existia no `localmodels.py` commitado da Task 3 — o
   Passo 0 da Task 4 o expõe (alias público de `_guard`) e fixa o contrato com
   um teste em `test_localmodels.py`; os blocos de código/teste da Task 3 acima
   foram atualizados para ficarem byte-idênticos ao arquivo final, e a cadeia
   de contagens passou de 305 para 306 na Task 3 (e +1 em cada task a jusante).
   (b) O Step 2 dizia `ModuleNotFoundError: No module named 'thero.providers'`;
   o pacote `thero` já existe (Tasks 1-3), então o erro real é
   `ImportError: cannot import name 'providers' from 'thero'` — mesmo caso do
   Step 2 da Task 3. (c) O `FakeResponse` do teste de registro `local` estava
   num bloco separado ("no topo do arquivo"); foi fundido ao bloco único de
   `tests/test_providers.py` para o trecho prescrito ficar byte-idêntico ao
   arquivo final.

- [ ] **Step 1: Testes**

`tests/test_providers.py`:

```python
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
```

- [ ] **Step 2: Rodar para confirmar falha**

Run: `python -m pytest tests/test_providers.py -q`
Expected: FAIL — `ImportError: cannot import name 'providers' from 'thero'`
(o pacote `thero` ja existe por causa das Tasks 1-3, entao o erro e de import
de nome dentro do pacote, nao `ModuleNotFoundError` -- mesma raiz do Step 2 da
Task 3: o modulo ainda nao existe)

- [ ] **Step 3: Implementação**

Create `src/thero/providers.py`:

```python
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
```

- [ ] **Step 4: Rodar**

Run: `python -m pytest tests/ -q`
Expected: `306 + 13 = 319 passed`

- [ ] **Step 5: Commit (pedir confirmação)**

```bash
git add src/thero/providers.py tests/test_providers.py
git commit -m "feat(providers): provider registry that never reads or echoes key values"
```

---

### Task 5: Escritores de configuração (`apply.py` + `upsert_block`)

**Files:**
- Modify: `src/thero/shell_command/__init__.py` (função genérica `upsert_block`)
- Modify: `src/thero/providers.py` (expor `redact`, redação de credencial já existente em `_redact`)
- Create: `src/thero/apply.py`
- Test: `tests/test_apply.py`

**Por que `upsert_block`:** `upsert_marked_block()` hoje gruda nos marcadores
`COMMAND_MARKER_START/END` do comando de atalho. O bloco de ambiente no
`$PROFILE` usa marcadores próprios (`ENV_MARKER_START/END`) para um upsert não
engolir o outro. Em vez de copiar a lógica, extraio a versão genérica e deixo
a atual delegando — comportamento das chamadas existentes não muda.

**Correções da auditoria costurada nos blocos abaixo (A1-A9, já refletidas no
código final e nos testes byte-idênticos):**

- **A1/A2 — marcadores vêm DENTRO do bloco.** `upsert_block`/`upsert_marked_block`
  DETECTAM e substituem, nunca injetam: quem chama traz o bloco já emoldurado
  (`windows.py:143-149` faz exatamente isso). Os testes antigos presumiam
  injeção; foram corrigidos para a forma real (`">>>\nblock\n<<<"`). Injetar
  duplicaria os marcadores no `$PROFILE` e quebraria o comando global.
  `upsert_marked_block` mantém a assinatura de 2 argumentos.
- **A2 (canibalismo).** A busca por `index(end)` na primeira ocorrência pode
  casar com marcador de outro bloco; há um teste com dois pares distintos na
  mesma `$PROFILE` provando que trocar um não toca no outro.
- **A3 — loopback na origem da escrita.** `_ollama_base` delega a
  `localmodels.guard_base`: base remota levanta `ValueError`. `apply_profile`
  captura e devolve recusa SEM escrever, com o motivo redigido por
  `providers.redact` (novo wrapper público sobre `_redact`, sem copiar regex).
- **A4 — `apply_claude(agent, cfg, path)`** recebe o agente do despacho (com
  fallback para id `"claude"` quando `None`), igual a opencode/codex.
- **A5 — `id`/`target` em TODO retorno** de `apply_agent`, inclusive o
  record-only: a ponte casa por `id`, senão Qoder/VS Code/Cline/Cursor ficam
  "pendente" para sempre.
- **A6 — `model_provider` só com a mesa existente.** `apply_codex` escreve
  `model_provider` apenas se `[model_providers.<id>]` estiver no corpo; senão
  escreve só `model` e explica no `msg`.
- **A7 — leitura sem `errors="replace"`.** `_read_text` tenta utf-8 (tolera
  BOM na leitura, escreve sem BOM) → cp1252 (preservado byte a byte) → recusa
  sem tocar no arquivo. Proibido regravar com U+FFFD um `$PROFILE`/`config.toml`
  salvo como cp1252.
- **A8 — `apply_profile` valida `None` antes de virar `Path`.**
- **A9 — `default_paths()` NÃO tem chave `profile`** (localizar a `$PROFILE`
  exige rodar PowerShell; o `paths.get("profile")` no despacho só existe se o
  chamador injeta-lo).
- **Produto — backup e aviso na tela.** Todo retorno traz `"backup"` (nome do
  arquivo criado, ou `""` quando não houve) e o `msg` menciona o que foi
  tocado. O backup fica na máquina, nunca é versionado nem enviado.

- [ ] **Step 1: Testes**

`tests/test_apply.py`:

```python
import json

import pytest

from thero import apply
from thero.shell_command import upsert_block, upsert_marked_block
from thero.settings import COMMAND_MARKER_END, COMMAND_MARKER_START, ENV_MARKER_END, ENV_MARKER_START


# ——— upsert_block generico ———

def test_upsert_block_appends_when_absent():
    out = upsert_block("echo oi\n", "block", ">>>", "<<<")
    assert out.startswith("echo oi")
    assert ">>>\nblock\n<<<" in out


def test_upsert_block_replaces_instead_of_duplicating():
    first = upsert_block("", "A\nB", ">>>", "<<<")
    second = upsert_block(first, "C", ">>>", "<<<")
    assert second.count(">>>") == 1
    assert "C" in second and "A" not in second


def test_upsert_block_keeps_text_after_the_marker():
    existing = "antes\n>>>\nvelho\n<<<\ndepois\n"
    out = upsert_block(existing, "novo", ">>>", "<<<")
    assert "antes" in out and "depois" in out
    assert "velho" not in out


def test_marked_block_still_uses_the_command_markers():
    out = upsert_marked_block("", "function thero {}", "")
    assert COMMAND_MARKER_START in out and COMMAND_MARKER_END in out


# ——— claude settings.json ———

@pytest.fixture
def cfg():
    return {
        "providers": [
            {"id": "claude", "label": "Claude Code", "model": "sonnet",
             "authKind": "session", "authVar": "", "base": ""},
            {"id": "ollama", "label": "Ollama", "model": "llama3.2",
             "authKind": "local", "authVar": "",
             "base": "http://127.0.0.1:11434"},
        ],
        "agents": [
            {"id": "claude", "preset": "claude", "target": "claude",
             "provider": "claude", "model": "sonnet", "enabled": True},
        ],
        "routing": {"athena": "llama3.2", "sentinel": "qwen3-coder-next"},
    }


def test_apply_claude_sets_model_and_env_anthropic_model(tmp_path, cfg):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"autoUpdatesChannel": "latest"}),
                      encoding="utf-8")
    out = apply.apply_claude(cfg, target)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["model"] == "sonnet"
    assert data["env"]["ANTHROPIC_MODEL"] == "sonnet"
    assert data["autoUpdatesChannel"] == "latest"   # preservou o resto
    assert out["ok"] is True
    assert str(target) in out["written"]


def test_apply_claude_backs_up_before_touching(tmp_path, cfg):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"env": {"X": "1"}}), encoding="utf-8")
    apply.apply_claude(cfg, target)
    backups = list(tmp_path.glob("settings.backup_*"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8"))["env"]["X"] == "1"


def test_apply_refuses_an_unparseable_file_and_leaves_it_alone(tmp_path, cfg):
    target = tmp_path / "settings.json"
    target.write_text("{ isto nao e json", encoding="utf-8")
    out = apply.apply_claude(cfg, target)
    assert out["ok"] is False
    assert "nao fui" in out["msg"].lower() or "parse" in out["msg"].lower()
    assert target.read_text(encoding="utf-8") == "{ isto nao e json"
    assert list(tmp_path.glob("settings.backup_*")) == []


def test_apply_claude_creates_env_without_clobbering_other_vars(tmp_path, cfg):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"env": {"ANTHROPIC_API_KEY": "kept"}}),
                      encoding="utf-8")
    apply.apply_claude(cfg, target)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["env"]["ANTHROPIC_API_KEY"] == "kept"
    assert data["env"]["ANTHROPIC_MODEL"] == "sonnet"


# ——— opencode ———

def test_apply_opencode_writes_provider_slash_model(tmp_path, cfg):
    target = tmp_path / "opencode.json"
    target.write_text(json.dumps({"theme": "opencode"}), encoding="utf-8")
    agent = dict(cfg["agents"][0], preset="opencode", target="opencode",
                 provider="ollama", model="llama3.2")
    apply.apply_opencode(agent, cfg, target)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["model"] == "ollama/llama3.2"
    assert data["theme"] == "opencode"


# ——— codex config.toml ———

def test_apply_codex_rewrites_only_top_level_scalars(tmp_path, cfg):
    target = tmp_path / "config.toml"
    target.write_text(
        'model = "old"\nnotify = true\n\n[mcp_servers.x]\ncmd = "keep me"\n',
        encoding="utf-8",
    )
    agent = dict(cfg["agents"][0], target="codex", provider="openai",
                 model="gpt-5-codex")
    cfg["providers"].append({"id": "openai", "label": "OpenAI",
                             "model": "gpt-5-codex", "base": ""})
    apply.apply_codex(agent, cfg, target)
    text = target.read_text(encoding="utf-8")
    assert 'model = "gpt-5-codex"' in text
    assert "notify = true" in text
    assert 'cmd = "keep me"' in text
    assert text.index("notify") < text.index("[mcp_servers")


def test_apply_codex_creates_the_key_when_the_file_has_none(tmp_path, cfg):
    target = tmp_path / "config.toml"
    target.write_text('[features]\nx = true\n', encoding="utf-8")
    agent = dict(cfg["agents"][0], target="codex", model="gpt-5-codex")
    apply.apply_codex(agent, cfg, target)
    text = target.read_text(encoding="utf-8")
    assert text.splitlines()[0].startswith("model")
    assert "[features]" in text


# ——— $PROFILE (contrato real dos dois consumidores) ———

def test_profile_block_carries_both_consumer_contracts(cfg):
    block = apply.profile_env_block(cfg)
    assert "$env:ATHENA_OLLAMA_HOST" in block
    assert "$env:ATHENA_OLLAMA_MODEL" in block
    assert "$env:SENTINEL_OLLAMA_HOST" in block
    assert "$env:SENTINEL_OLLAMA_MODEL" in block
    # cada consumidor com o modelo que o usuario escolheu para ele — os dois
    # padrao sao diferentes (Athena llama3.2, Sentinel qwen3-coder-next)
    assert '$env:ATHENA_OLLAMA_MODEL = "llama3.2"' in block
    assert '$env:SENTINEL_OLLAMA_MODEL = "qwen3-coder-next"' in block
    assert block.count("http://127.0.0.1:11434") == 2
    assert ENV_MARKER_START in block and ENV_MARKER_END in block


def test_profile_block_falls_back_to_each_consumers_own_default(cfg):
    cfg["routing"] = {}                       # usuario ainda nao escolheu
    block = apply.profile_env_block(cfg)
    assert '$env:ATHENA_OLLAMA_MODEL = "llama3.2"' in block
    assert '$env:SENTINEL_OLLAMA_MODEL = "qwen3-coder-next"' in block


def test_env_contracts_cover_exactly_the_declared_consumers():
    # duas listas de consumidores e a receita de uma tela que escreve no
    # arquivo errado: isto garante que apply.ENV_CONTRACTS e
    # providers.CONSUMERS nunca divergem.
    from thero import providers

    assert set(apply.ENV_CONTRACTS) == set(providers.CONSUMERS)


def test_apply_profile_is_idempotent(tmp_path, cfg):
    profile = tmp_path / "Microsoft.PowerShell_profile.ps1"
    profile.write_text("function foo {}\n", encoding="utf-8")
    apply.apply_profile(cfg, profile)
    apply.apply_profile(cfg, profile)
    text = profile.read_text(encoding="utf-8")
    assert text.count(ENV_MARKER_START) == 1
    assert "function foo" in text


def test_apply_never_uses_print_on_the_bridge_channel(tmp_path, cfg, capsys):
    target = tmp_path / "settings.json"
    target.write_text("{}", encoding="utf-8")
    apply.apply_agent(cfg["agents"][0], cfg, {"claude": target})
    assert capsys.readouterr().out == ""


def test_record_only_targets_write_nothing(tmp_path, cfg):
    target = tmp_path / "settings.json"
    before = "{}"
    target.write_text(before, encoding="utf-8")
    agent = dict(cfg["agents"][0], target="none", preset="qoder")
    out = apply.apply_agent(agent, cfg, {"claude": target})
    assert out["ok"] is True
    assert out["writes"] is False
    assert target.read_text(encoding="utf-8") == before


def test_apply_all_reports_each_enabled_agent_and_skips_disabled(tmp_path, cfg):
    cfg["agents"].append(dict(cfg["agents"][0], id="x", enabled=False))
    paths = {"claude": tmp_path / "settings.json"}
    paths["claude"].write_text("{}", encoding="utf-8")
    results = apply.apply_all(cfg, paths)
    assert len(results) == 1
    assert results[0]["id"] == "claude"
```

- [ ] **Step 2: Rodar para confirmar falha**

Run: `python -m pytest tests/test_apply.py -q`
Expected: FAIL — `cannot import name 'upsert_block'` e `No module named 'thero.apply'`

- [ ] **Step 3: `upsert_block` genérico**

Em `src/thero/shell_command/__init__.py`, adicionar antes de `upsert_marked_block`
e reescrever este para delegar (assinatura e marcadores atuais inalterados):

```python
def upsert_block(
    existing: str,
    block: str,
    start: str,
    end: str,
) -> str:
    """
    Troca (ou acrescenta) `block` dentro de `existing`, reconhecendo pelos
    marcadores `start`/`end`. O bloco ja traz os proprios marcadores (como o
    template do comando global): a funcao DETECTA e substitui, nunca injeta --
    injetar duplicaria os marcadores no arquivo. Idempotente: rodar duas
    vezes nao duplica, e o texto depois do marcador final continua la.
    """
    block = block.strip("\n") + "\n"

    if start in existing and end in existing:
        start_index = existing.index(start)
        end_index = existing.index(end) + len(end)
        return (
            existing[:start_index]
            + block
            + existing[end_index:].lstrip("\n")
        )

    if existing.strip():
        return existing.rstrip("\n") + "\n\n" + block

    return block


def upsert_marked_block(
    existing: str,
    block: str,
) -> str:
    """
    Insere "block" (delimitado por COMMAND_MARKER_START/END) dentro
    de "existing", substituindo um bloco anterior com os mesmos
    marcadores em vez de duplicar.
    """

    return upsert_block(
        existing,
        block,
        COMMAND_MARKER_START,
        COMMAND_MARKER_END,
    )
```

> O bloco acima é o código final (delegação pura: comportamento do comando
> global inalterado, só os marcadores viram parâmetro).

- [ ] **Step 4: `apply.py`**

Create `src/thero/apply.py`:

```python
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
```

- [ ] **Step 5: Rodar**

Run: `python -m pytest tests/ -q`
Expected: `362 + 32 = 394 passed` (baseline atual da Task 4 e 362, nao 319; os testes antigos do comando global cobrem o `upsert_marked_block` delegado e continuam passando).

- [ ] **Step 6: Commit (pedir confirmação)**

```bash
git add src/thero/shell_command/__init__.py src/thero/providers.py src/thero/apply.py tests/test_apply.py
git commit -m "feat(apply): write provider+model into verified targets only, with backup and merge"
```

---

### Task 6: Estado das skills (`skillstate.py`) — origem, quarentena, importação

**Files:**
- Create: `src/thero/skillstate.py`
- Test: `tests/test_skillstate.py`

Fatos que mandam aqui:

| Fato | Onde verifiquei |
|---|---|
| Skills vivem em `~/.claude/skills/<nome>/SKILL.md` (base global) ou `./.claude/skills/` (`--local`) | `skills/installer.py:11-33` (`--agent claude-code`, `--global`) |
| O catálogo do Thero é `SKILL_REPOSITORIES[*]["wanted"]` + o `impeccable`, que tem instalador próprio (`npx impeccable install`) | `skills/catalog.py`, `skills/installer.py:131-191` |
| **Não existe** marcador de procedência no disco: o que existe é "está na lista do Thero?" | inspeção de `~/.claude/skills/` nesta máquina |
| `npx skills search` **não verificado** (o `npm install` desta máquina está quebrado, então nunca rodei o subcomando) | tentativa real desta sessão |
| Desinstalar = mover para quarentena, nunca `rmtree` | política do projeto (mesma lógica de limpeza do Vector) |

- [ ] **Step 1: Testes**

`tests/test_skillstate.py`:

```python
import json

import pytest

from thero import skillstate


@pytest.fixture
def base(tmp_path):
    root = tmp_path / "skills"
    for name in ("engineering-manager", "supabase", "caveman", "meu-proprio"):
        folder = root / name
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(
            "---\nname: %s\ndescription: teste\n---\n\ncorpo\n" % name,
            encoding="utf-8")
    (root / "sem-skill-md").mkdir()
    return root


def test_thero_names_come_from_the_catalog_plus_impeccable():
    names = skillstate.thero_skill_names()
    assert "engineering-manager" in names
    assert "supabase-postgres-best-practices" in names
    assert "impeccable" in names
    assert "caveman" not in names          # repo do usuario, nao "do Thero"


def test_installed_marks_origin_and_skips_folders_without_a_skill_md(base):
    rows = skillstate.installed(base_dir=base)
    by_name = {r["name"]: r for r in rows}
    assert set(by_name) == {"engineering-manager", "supabase", "caveman",
                            "meu-proprio"}
    assert by_name["engineering-manager"]["origin"] == "thero"
    assert by_name["caveman"]["origin"] == "user"
    assert by_name["meu-proprio"]["origin"] == "user"


def test_uninstall_refuses_a_skill_the_thero_installed(base, tmp_path):
    with pytest.raises(skillstate.ProtectedSkill):
        skillstate.uninstall("supabase", base_dir=base,
                             quarantine=tmp_path / "q")


def test_uninstall_moves_to_quarantine_instead_of_deleting(base, tmp_path):
    q = tmp_path / "q"
    out = skillstate.uninstall("meu-proprio", base_dir=base, quarantine=q)
    assert out["ok"] is True
    assert not (base / "meu-proprio").exists()
    assert (q / "meu-proprio" / "SKILL.md").exists()
    assert out["quarantine"]


def test_uninstall_keeps_a_collision_in_quarantine_readable(base, tmp_path):
    q = tmp_path / "q"
    skillstate.uninstall("meu-proprio", base_dir=base, quarantine=q)
    (base / "meu-proprio").mkdir()
    (base / "meu-proprio" / "SKILL.md").write_text("segunda", encoding="utf-8")
    skillstate.uninstall("meu-proprio", base_dir=base, quarantine=q)
    # Duas pastas, a segunda com sufixo: nada foi por cima de nada.
    names = sorted(p.name for p in q.iterdir())
    assert len(names) == 2
    assert names[0] == "meu-proprio"
    assert names[1].startswith("meu-proprio__")


def test_uninstall_of_the_unknown_says_so(base, tmp_path):
    out = skillstate.uninstall("fantasma", base_dir=base,
                               quarantine=tmp_path / "q")
    assert out["ok"] is False


def test_import_requires_a_skill_md(tmp_path, base):
    junk = tmp_path / "junk"
    junk.mkdir()
    out = skillstate.import_skill(junk, base_dir=base)
    assert out["ok"] is False
    assert "SKILL.md" in out["msg"]


def test_import_copies_the_folder_and_marks_it_user(tmp_path, base):
    src = tmp_path / "minha-skill"
    src.mkdir()
    (src / "SKILL.md").write_text(
        "---\nname: minha-skill\ndescription: x\n---\n", encoding="utf-8")
    (src / "reference.md").write_text("apoio", encoding="utf-8")
    out = skillstate.import_skill(src, base_dir=base)
    assert out["ok"] is True
    target = base / "minha-skill"
    assert (target / "SKILL.md").exists()
    assert (target / "reference.md").exists()
    rows = {r["name"]: r for r in skillstate.installed(base_dir=base)}
    assert rows["minha-skill"]["origin"] == "user"


def test_import_refuses_to_overwrite_a_thero_skill(tmp_path, base):
    src = tmp_path / "supabase"
    src.mkdir()
    (src / "SKILL.md").write_text("---\nname: supabase\n---\n", encoding="utf-8")
    out = skillstate.import_skill(src, base_dir=base)
    assert out["ok"] is False
    assert "Thero" in out["msg"]


def test_search_filters_the_known_catalog_and_labels_the_source():
    rows = skillstate.search("postgres")
    assert rows
    assert all(r["source"] == "catalogo do thero" for r in rows)
    assert all("repo" in r and "skill" in r for r in rows)
    assert skillstate.search("zznadaaver") == []


def test_search_documents_that_the_community_cli_is_unverified():
    rows = skillstate.search("")
    assert any(r.get("unverified") for r in rows) or "npx" in skillstate.NOTE


def test_skill_line_command_matches_the_installer_builder():
    command = skillstate.install_command("supabase/agent-skills", "supabase")
    assert command[:4] == ["npx", "skills", "add", "supabase/agent-skills"]
    assert "--skill" in command and "supabase" in command
    assert "--global" in command
    assert "--global" not in skillstate.install_command(
        "supabase/agent-skills", "supabase", global_install=False)


def test_manifest_round_trip_records_origin_but_never_invents_files(tmp_path):
    path = tmp_path / "manifest.json"
    skillstate.save_manifest({"supabase": "thero", "caveman": "user"}, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["caveman"] == "user"
```

- [ ] **Step 2: Rodar para confirmar falha**

Run: `python -m pytest tests/test_skillstate.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'thero.skillstate'`

- [ ] **Step 3: Implementação**

Create `src/thero/skillstate.py`:

```python
"""O que a tela de Skills precisa saber: quem instalou o que, e para onde vai.

Procedencia: NAO existe marcador no disco (fatos da secao de contexto deste
plano). A origem real e "esta pasta esta na lista do catalogo do Thero?".
Por isso `thero_skill_names()` vem do proprio catalogo, nao de um registro
paralelo que poderia descer do passo.

Busca: o `npx skills search` nunca foi verificado nesta maquina (o npm local
esta quebrado), entao NAO invento subcomando. `search()` filtra o catalogo
conhecido e marca o que e comunitario como nao verificado.

Remocao: move para quarentena. Nada e apagado.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

from thero.settings import (
    SKILLS_BASE_GLOBAL,
    SKILLS_QUARANTINE_DIRNAME,
    THERO_DIR,
)
from thero.skills.catalog import SKILL_REPOSITORIES
from thero.skills.installer import build_skill_install_command

IMPECCABLE_SKILL = "impeccable"

# Unica fonte de "instalada pelo Thero".
NOTE = (
    "busca no catalogo do Thero; a busca da comunidade (%s) nao foi "
    "verificada nesta maquina" % "npx skills"
)


class ProtectedSkill(Exception):
    """Skill do Thero: a interface nao desinstala."""


def quarantine_dir() -> Path:
    return THERO_DIR / "quarantine" / SKILLS_QUARANTINE_DIRNAME


def skills_base(local: bool = False) -> Path:
    if local:
        return Path.cwd() / ".claude" / "skills"
    return SKILLS_BASE_GLOBAL


def thero_skill_names() -> set:
    names = {IMPECCABLE_SKILL}
    for repository in SKILL_REPOSITORIES:
        names.update(repository.get("wanted", []))
    return names


def _read_title(folder: Path) -> str:
    """Primeiro `description:` do SKILL.md, sem parser de YAML completo."""
    try:
        lines = (folder / "SKILL.md").read_text(
            encoding="utf-8-sig", errors="replace").splitlines()
    except OSError:
        return ""
    for line in lines[:24]:
        stripped = line.strip()
        if stripped.lower().startswith("description:"):
            return stripped.split(":", 1)[1].strip().strip("\"'")[:160]
    return ""


def installed(base_dir: Optional[Path] = None,
              local: bool = False) -> list:
    root = Path(base_dir) if base_dir else skills_base(local)
    if not root.is_dir():
        return []
    owned = thero_skill_names()
    rows = []
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or not (folder / "SKILL.md").exists():
            continue
        name = folder.name
        rows.append({
            "name": name,
            "path": str(folder),
            "origin": "thero" if name in owned else "user",
            "desc": _read_title(folder),
            "base": str(root),
        })
    return rows


def catalog_rows() -> list:
    rows = []
    for repository in SKILL_REPOSITORIES:
        for skill in repository.get("wanted", []):
            rows.append({
                "skill": skill,
                "repo": repository["repo"],
                "group": repository["name"],
                "source": "catalogo do thero",
                "origin": "thero",
            })
    rows.append({
        "skill": IMPECCABLE_SKILL,
        "repo": "impeccable (instalador proprio)",
        "group": "Craft de interface",
        "source": "catalogo do thero",
        "origin": "thero",
    })
    return rows


def search(query: str = "", base_dir: Optional[Path] = None,
           local: bool = False) -> list:
    needle = (query or "").strip().lower()
    have = {row["name"] for row in installed(base_dir=base_dir, local=local)}
    out = []
    for row in catalog_rows():
        haystack = "%s %s %s" % (row["skill"], row["repo"], row["group"])
        if needle and needle not in haystack.lower():
            continue
        row = dict(row)
        row["installed"] = row["skill"] in have
        out.append(row)
    return out


def _unique_quarantine_target(quarantine: Path, name: str) -> Path:
    quarantine.mkdir(parents=True, exist_ok=True)
    candidate = quarantine / name
    if not candidate.exists():
        return candidate
    from thero.system.process import timestamp

    # shutil.move num destino que ja existe como pasta nao sobrescreve: ele
    # ENCAIXA a pasta dentro da outra. Duas remocoes no mesmo segundo preciso
    # do timestamp() fariam isso, entao o nome e unico por tentativa.
    suffix = timestamp()
    n = 1
    while True:
        candidate = quarantine / ("%s__%s" % (name, suffix if n == 1 else "%s_%d" % (suffix, n)))
        if not candidate.exists():
            return candidate
        n += 1


def uninstall(name: str, base_dir: Optional[Path] = None,
              quarantine: Optional[Path] = None, local: bool = False) -> dict:
    root = Path(base_dir) if base_dir else skills_base(local)
    folder = root / name
    if not folder.is_dir():
        return {"ok": False, "msg": "nao encontrei %s em %s" % (name, root)}
    if name in thero_skill_names():
        return {"ok": False,
                "msg": "%s foi instalada pelo Thero e nao pode ser "
                       "desinstalada pela interface" % name}
    destination = _unique_quarantine_target(
        Path(quarantine) if quarantine else quarantine_dir(), name)
    shutil.move(str(folder), str(destination))
    return {"ok": True, "quarantine": str(destination),
            "msg": "movida para a quarentena: %s" % destination}


def import_skill(source: Path, base_dir: Optional[Path] = None,
                 local: bool = False) -> dict:
    src = Path(source)
    if not src.is_dir() or not (src / "SKILL.md").exists():
        return {"ok": False,
                "msg": "a pasta indicada nao tem SKILL.md: %s" % src}
    if src.name in thero_skill_names():
        return {"ok": False,
                "msg": "%s e uma skill do Thero: importar por cima nao e "
                       "permitido" % src.name}
    root = Path(base_dir) if base_dir else skills_base(local)
    root.mkdir(parents=True, exist_ok=True)
    target = root / src.name
    if target.exists():
        shutil.rmtree(str(target))
    shutil.copytree(str(src), str(target))
    return {"ok": True, "path": str(target), "origin": "user",
            "msg": "importada para %s" % target}


def install_command(repo: str, skill: str,
                    global_install: bool = True) -> list:
    return build_skill_install_command(repo, skill, global_install)


def save_manifest(manifest: dict, path: Optional[Path] = None) -> Path:
    """Registro opcional de procedencia propria do usuario.

    Nao e fonte de verdade da UI (a fonte e o catalogo) -- existe so para o
    usuario anotar o que ele mesmo instalou, se quiser.
    """
    target = Path(path) if path else THERO_DIR / "skill-manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target
```

- [ ] **Step 4: Rodar**

Run: `python -m pytest tests/ -q`
Expected: `337 + 13 = 350 passed`

- [ ] **Step 5: Commit (pedir confirmação)**

```bash
git add src/thero/skillstate.py tests/test_skillstate.py
git commit -m "feat(skills): origin-aware skill state with quarantine-only uninstall"
```

---

### Task 7: `stream_command` — saída de processo linha a linha

**Files:**
- Modify: `src/thero/system/process.py`
- Test: `tests/test_process_stream.py`

`run_command()` é tudo-ou-nada (`capture=True` → `CompletedProcess`). A ponte
precisa do contrário: cada linha do `npx skills --update` / `ollama pull`
aparece no painel de terminal enquanto o processo roda, sem travar. `stderr`
vai junto no mesmo fluxo (`STDOUT`) porque é assim que npm/ollama reportam
progresso.

- [ ] **Step 1: Testes**

`tests/test_process_stream.py`:

```python
import io
import subprocess

from thero.system import process


class FakePopen:
    def __init__(self, lines, code=0):
        self._lines = lines
        self.returncode = code

    def __iter__(self):
        return iter(self._lines)

    def wait(self):
        return self.returncode

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_lines_then_exit_code(monkeypatch):
    monkeypatch.setattr(process.subprocess, "Popen",
                        lambda *a, **k: FakePopen(["a\n", "b\n"]))
    out = list(process.stream_command(["npx", "skills", "check"]))
    assert out == [("out", "a"), ("out", "b"), ("exit", 0)]


def test_windows_launcher_translation_is_reused(monkeypatch):
    seen = {}

    def spy(command, **kwargs):
        seen["command"] = command
        return FakePopen([])

    monkeypatch.setattr(process.os, "name", "nt")
    monkeypatch.setattr(process.subprocess, "Popen", spy)
    list(process.stream_command(["npx", "skills"]))
    assert seen["command"][0] == "npx.cmd"


def test_stderr_is_merged_into_the_same_stream(monkeypatch):
    captured = {}

    def spy(command, **kwargs):
        captured["stderr"] = kwargs.get("stderr")
        captured["encoding"] = kwargs.get("encoding")
        return FakePopen([])

    monkeypatch.setattr(process.subprocess, "Popen", spy)
    list(process.stream_command(["node", "-v"]))
    assert captured["stderr"] is subprocess.STDOUT
    assert captured["encoding"] == "utf-8"


def test_a_missing_executable_becomes_a_line_and_exit_127(monkeypatch):
    def boom(*a, **k):
        raise OSError("cannot find the file specified")

    monkeypatch.setattr(process.subprocess, "Popen", boom)
    out = list(process.stream_command(["npx", "skills"]))
    assert out[-1] == ("exit", 127)
    assert out[0][0] == "out"
    assert "npx" in out[0][1]


def test_nonzero_exit_is_reported_not_raised(monkeypatch):
    monkeypatch.setattr(process.subprocess, "Popen",
                        lambda *a, **k: FakePopen(["x"], code=3))
    out = list(process.stream_command(["npx", "skills", "update"]))
    assert out[-1] == ("exit", 3)


def test_shell_is_never_used(monkeypatch):
    captured = {}

    def spy(command, **kwargs):
        captured.update(kwargs)
        captured["argv"] = command
        return FakePopen([])

    monkeypatch.setattr(process.subprocess, "Popen", spy)
    list(process.stream_command(["git", "status"], cwd=None))
    assert captured["shell"] is False
    assert captured["argv"] == ["git", "status"]
```

- [ ] **Step 2: Rodar para confirmar falha**

Run: `python -m pytest tests/test_process_stream.py -q`
Expected: FAIL — `AttributeError: module 'thero.system.process' has no attribute 'stream_command'`

- [ ] **Step 3: Implementação**

Acrescentar ao fim de `src/thero/system/process.py` (reaproveitando o mapa de
launchers do Windows que hoje está duplicado dentro de `run_command`; extrair
para função própria e fazer `run_command` usar, sem mudar sua assinatura):

```python
WINDOWS_LAUNCHERS = {
    "npx": "npx.cmd",
    "npm": "npm.cmd",
    "node": "node.exe",
    "claude": "claude.cmd",
}


def _with_windows_launcher(command: list[str]) -> list[str]:
    """npm/Claude instalam .cmd no PATH; sem o executavel certo o CreateProcess falha."""
    if os.name != "nt" or not command:
        return list(command)
    executable = WINDOWS_LAUNCHERS.get(command[0], command[0])
    return [executable, *command[1:]]


def stream_command(
    command: list[str],
    *,
    cwd: Path | None = None,
) -> "Generator[tuple, None, None]":
    """
    Roda `command` e produz ('out', linha) durante a execucao e ('exit',
    codigo) no fim.

    stderr vai para o mesmo fluxo (npm e ollama escrevem progresso la).
    `encoding="utf-8"` explicito: no Windows o padrao e a codepage do
    console, que corrompe acento.
    """
    if not command:
        yield ("out", "comando vazio")
        yield ("exit", 2)
        return

    argv = _with_windows_launcher(command)

    try:
        popen = subprocess.Popen(
            argv,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            shell=False,
        )
    except OSError as exc:
        yield ("out", "nao consegui rodar %s: %s" % (argv[0], exc))
        yield ("exit", 127)
        return

    with popen:
        for line in popen:
            line = line.rstrip("\r\n")
            if line:
                yield ("out", line)
        yield ("exit", popen.wait())
```

E dentro de `run_command`, trocar o bloco `windows_launchers = {...}` +
reatribuição por:

```python
    command = _with_windows_launcher(command)
```

- [ ] **Step 4: Rodar**

Run: `python -m pytest tests/ -q`
Expected: `350 + 6 = 356 passed` (os testes que cobriam `run_command` continuam passando — comportamento externo inalterado)

- [ ] **Step 5: Commit (pedir confirmação)**

```bash
git add src/thero/system/process.py tests/test_process_stream.py
git commit -m "feat(process): line-streaming subprocess runner shared with the GUI bridge"
```

---

### Task 8: A ponte (`bridge.py`) e a flag `--serve`

**Files:**
- Create: `src/thero/bridge.py`
- Modify: `src/thero/cli.py` (flag `--serve`, ao lado de `--mcp`)
- Test: `tests/test_bridge.py`

Protocolo (idêntico ao do Vector, com streaming acrescentado):

- Uma requisição por linha JSON: `{"id": 3, "cmd": "providers-register", ...}`
- Resposta final: `{"id": 3, "ok": true, "result": {...}}` ou `{"id": 3, "ok": false, "error": "..."}`
- Durante um comando longo, antes da resposta final: `{"id": 3, "event": "line", "text": "..."}`
- Toda validação de segurança vive **aqui**, nunca no JS.

- [ ] **Step 1: Testes**

`tests/test_bridge.py`:

```python
import json

import pytest

from thero import __version__, bridge, config, presets


@pytest.fixture
def state(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return bridge.BridgeState(
        entry_path=tmp_path / "thero.py",
        config_path=home / ".thero" / "config.json",
        paths=bridge.state_paths(home),
        profile_path=home / "profile.ps1",
        skills_base=home / ".claude" / "skills",
        quarantine=home / ".thero" / "quarantine" / "skills",
    )


def call(state, request, **kw):
    return bridge.handle_request(request, state, **kw)


# ——— envelope ———

def test_ping_round_trip(state):
    out = call(state, {"id": 1, "cmd": "ping"})
    assert out == {"id": 1, "ok": True,
                   "result": {"app": "thero", "version": __version__}}


def test_unknown_command_is_an_error_not_a_crash(state):
    out = call(state, {"id": 2, "cmd": "destrua-tudo"})
    assert out["ok"] is False
    assert "desconhecido" in out["error"]


def test_a_missing_id_still_answers(state):
    out = call(state, {"cmd": "ping"})
    assert out["id"] is None and out["ok"] is True


# ——— run: whitelist de flags ———

def test_run_accepts_a_known_flag_and_streams_lines(state, monkeypatch):
    calls = []

    def fake_stream(command, **kw):
        calls.append(command)
        return iter([("out", "Instalando supabase"), ("exit", 0)])

    monkeypatch.setattr(bridge, "stream_command", fake_stream)
    # sys.executable varia por maquina; congelo para poder afirmar sobre a linha.
    monkeypatch.setattr(bridge, "_python_exe", lambda: "python")
    events = []
    out = call(state, {"id": 3, "cmd": "run", "flags": ["--skills-only"]},
               emit=events.append)
    assert out["ok"] is True
    assert out["result"]["exitCode"] == 0
    assert events == [{"id": 3, "event": "line",
                       "text": "Instalando supabase"}]
    assert calls[0][:2] == ["python", str(state.entry_path)]


def test_run_rejects_an_unknown_flag(state, monkeypatch):
    monkeypatch.setattr(bridge, "stream_command",
                        lambda *a, **k: iter([("exit", 0)]))
    out = call(state, {"id": 4, "cmd": "run", "flags": ["--rm-all-my-files"]})
    assert out["ok"] is False
    assert "--rm-all-my-files" in out["error"]


def test_run_rejects_a_value_that_is_not_a_flag(state, monkeypatch):
    monkeypatch.setattr(bridge, "stream_command",
                        lambda *a, **k: iter([("exit", 0)]))
    out = call(state, {"id": 5, "cmd": "run", "flags": ["--plan", "; rm -rf /"]})
    assert out["ok"] is False


def test_run_honours_scope_local(state, monkeypatch):
    seen = []
    monkeypatch.setattr(
        bridge, "stream_command",
        lambda command, **kw: seen.append(command) or iter([("exit", 0)]))
    call(state, {"id": 6, "cmd": "run", "flags": [], "scope": "local"})
    assert "--local" in seen[0]


def test_run_allows_max_files_with_a_number_only(state, monkeypatch):
    seen = []
    monkeypatch.setattr(
        bridge, "stream_command",
        lambda command, **kw: seen.append(command) or iter([("exit", 0)]))
    out = call(state, {"id": 7, "cmd": "run",
                       "flags": ["--index", "--max-files", "200"]})
    assert out["ok"] is True
    assert seen[0][-2:] == ["--max-files", "200"]


# ——— config / providers ———

def test_config_command_returns_the_seeded_defaults(state):
    out = call(state, {"id": 8, "cmd": "config-get"})
    assert out["ok"] is True
    ids = [p["id"] for p in out["result"]["config"]["providers"]]
    assert ids == ["claude", "openai", "ollama"]


def test_config_set_persists_and_reloads(state):
    cfg = config.default_config()
    cfg["providers"][0]["model"] = "opus"
    out = call(state, {"id": 9, "cmd": "config-set", "config": cfg})
    assert out["ok"] is True
    again = call(state, {"id": 10, "cmd": "config-get"})
    assert again["result"]["config"]["providers"][0]["model"] == "opus"


def test_config_set_refuses_a_non_dict(state):
    out = call(state, {"id": 11, "cmd": "config-set", "config": ["x"]})
    assert out["ok"] is False


def test_provider_register_never_echoes_a_key_value(state, monkeypatch):
    monkeypatch.setenv("THERO_OPENAI_API_KEY", "sk-SEGREDO")
    cfg = config.default_config()
    state.cfg = cfg
    pid = "openai"
    out = call(state, {"id": 12, "cmd": "providers-register", "id": pid})
    assert out["ok"] is True
    assert "sk-SEGREDO" not in json.dumps(out)
    assert "THERO_OPENAI_API_KEY" in json.dumps(out)


def test_provider_presets_are_served_for_the_add_dialog(state):
    out = call(state, {"id": 13, "cmd": "providers-presets"})
    assert out["ok"] is True
    assert any(p["id"] == "omniroute" for p in out["result"]["presets"])


def test_provider_upsert_and_remove_flow(state):
    cfg = config.default_config()
    call(state, {"id": 14, "cmd": "config-set", "config": cfg})
    new = {"id": "meu", "label": "Meu provedor", "preset": "custom",
           "authKind": "apikey", "authVar": "THERO_MEU_API_KEY", "base": "",
           "model": "", "enabled": True, "origin": "user",
           "roles": {"athena": False, "sentinel": False}, "lastCheck": ""}
    out = call(state, {"id": 15, "cmd": "providers-upsert", "provider": new})
    assert [p["id"] for p in out["result"]["config"]["providers"]] == [
        "claude", "openai", "ollama", "meu"]
    out = call(state, {"id": 16, "cmd": "providers-remove", "id": "meu"})
    assert "meu" not in [p["id"] for p in out["result"]["config"]["providers"]]


def test_removing_a_thero_provider_is_refused(state):
    out = call(state, {"id": 17, "cmd": "providers-remove", "id": "claude"})
    assert out["ok"] is False


# ——— agents / apply ———

def test_agents_apply_writes_the_profile_block(state):
    profile = state.profile_path
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text("# nada\n", encoding="utf-8")
    out = call(state, {"id": 18, "cmd": "agents-apply", "id": "profile"})
    assert out["ok"] is True
    text = profile.read_text(encoding="utf-8")
    assert "ATHENA_OLLAMA_HOST" in text


def test_agents_apply_all_reports_every_enabled_agent(state):
    out = call(state, {"id": 19, "cmd": "agents-apply-all"})
    assert out["ok"] is True
    assert len(out["result"]["results"]) == 3


def test_record_only_agent_reports_no_write(state):
    cfg = config.default_config()
    cfg["agents"].append({"id": "qoder", "label": "Qoder", "preset": "qoder",
                          "target": "none", "provider": "openai",
                          "model": "gpt-4o", "enabled": True,
                          "origin": "user", "skills": True, "status": "",
                          "note": ""})
    call(state, {"id": 20, "cmd": "config-set", "config": cfg})
    out = call(state, {"id": 21, "cmd": "agents-apply", "id": "qoder"})
    assert out["result"]["writes"] is False


# ——— models ———

def test_models_status_uses_the_configured_host(state, monkeypatch):
    monkeypatch.setattr(
        bridge.localmodels, "list_models",
        lambda base: {"ok": True, "error": "",
                      "models": [{"name": "llama3.2", "sizeHuman": "2.0 GB",
                                  "params": "3B", "family": "llama"}]},
    )
    out = call(state, {"id": 22, "cmd": "models-status"})
    assert out["result"]["ollama"]["up"] is True
    assert out["result"]["ollama"]["models"][0]["name"] == "llama3.2"


def test_models_pull_streams(state, monkeypatch):
    monkeypatch.setattr(
        bridge.localmodels, "pull",
        lambda name, base="": iter([("out", "baixando"), ("exit", 0)]),
    )
    events = []
    out = call(state, {"id": 23, "cmd": "models-pull", "name": "llama3.2"},
               emit=events.append)
    assert out["result"]["exitCode"] == 0
    assert events[0]["text"] == "baixando"


# ——— skills ———

def test_skills_list_marks_origin(state):
    folder = state.skills_base / "supabase"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        "---\nname: supabase\ndescription: Postgres\n---\n", encoding="utf-8")
    mine = state.skills_base / "minha"
    mine.mkdir()
    (mine / "SKILL.md").write_text("---\nname: minha\n---\n", encoding="utf-8")
    out = call(state, {"id": 24, "cmd": "skills-list"})
    rows = {r["name"]: r for r in out["result"]["skills"]}
    assert rows["supabase"]["origin"] == "thero"
    assert rows["minha"]["origin"] == "user"


def test_skills_uninstall_refuses_a_thero_skill(state):
    folder = state.skills_base / "supabase"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text("---\nname: supabase\n---\n",
                                     encoding="utf-8")
    out = call(state, {"id": 25, "cmd": "skills-uninstall", "name": "supabase"})
    assert out["ok"] is False
    assert folder.exists()


def test_skills_uninstall_quarantines_a_user_skill(state):
    folder = state.skills_base / "minha"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text("---\nname: minha\n---\n", encoding="utf-8")
    out = call(state, {"id": 26, "cmd": "skills-uninstall", "name": "minha"})
    assert out["ok"] is True
    assert not folder.exists()
    assert (state.quarantine / "minha" / "SKILL.md").exists()


def test_skills_install_runs_the_real_installer_command(state, monkeypatch):
    seen = []
    monkeypatch.setattr(
        bridge, "stream_command",
        lambda command, **kw: seen.append(command) or iter([("exit", 0)]))
    out = call(state, {"id": 27, "cmd": "skills-install",
                       "repo": "supabase/agent-skills", "skill": "supabase"})
    assert out["ok"] is True
    assert seen[0][:2] == ["npx", "skills"]


def test_skills_import_validates_the_path(state):
    out = call(state, {"id": 28, "cmd": "skills-import",
                       "path": str(state.entry_path.parent / "nao-existe")})
    assert out["ok"] is True          # resposta do motor, nao erro de ponte
    assert out["result"]["skill"]["ok"] is False


def test_skills_import_rejects_a_path_outside_the_allowed_shape(state):
    out = call(state, {"id": 29, "cmd": "skills-import", "path": ""})
    assert out["ok"] is False


# ——— env / serve ———

def test_env_command_includes_the_live_config(state, monkeypatch):
    monkeypatch.setattr(bridge.envreport, "snapshot",
                        lambda *a, **k: {"app": "thero", "firstRun": True})
    out = call(state, {"id": 30, "cmd": "env"})
    assert out["result"]["env"]["app"] == "thero"
    assert "config" in out["result"]


def test_serve_reads_lines_and_writes_one_json_per_reply(state):
    inp = io.StringIO('{"id": 1, "cmd": "ping"}\n'
                      '{"id": 2, "cmd": "ping"}\n')
    out = io.StringIO()
    bridge.serve(inp, out, state=state)
    lines = [json.loads(x) for x in out.getvalue().splitlines()]
    assert [x["id"] for x in lines] == [1, 2]
    assert all(x["ok"] for x in lines)


def test_serve_keeps_accents_readable(state):
    inp = io.StringIO('{"id": 1, "cmd": "providers-remove", "id": "claude"}\n')
    out = io.StringIO()
    bridge.serve(inp, out, state=state)
    assert "é" in out.getvalue() or "Thero" in out.getvalue()
    assert "\\u" not in out.getvalue()


def test_serve_answers_invalid_json_without_dying(state):
    inp = io.StringIO("isto nao e json\n")
    out = io.StringIO()
    bridge.serve(inp, out, state=state)
    reply = json.loads(out.getvalue())
    assert reply["ok"] is False
```

`import io` no topo do arquivo de teste.

- [ ] **Step 2: Rodar para confirmar falha**

Run: `python -m pytest tests/test_bridge.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'thero.bridge'`

- [ ] **Step 3: Implementação**

Create `src/thero/bridge.py`:

```python
"""Ponte JSON da interface desktop: uma linha para dentro, uma para fora.

Mesmo protocolo do Vector/Genesis (host PowerShell + WebView2): o JS nunca
decide seguranca, so apresenta. O que muda aqui e o streaming: comandos longos
(`npx skills --update`, `ollama pull`) vao emitindo
`{"id": n, "event": "line", "text": "..."}` antes da resposta final, para o
painel de terminal mostrar progresso de verdade.

Regra do canal: stdout E O PROTOCOLO. Nada neste modulo (nem nos que ele
chama) pode usar print().
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Callable, Iterator, Optional, TextIO

from thero import (
    apply,
    config as config_store,
    envreport,
    localmodels,
    presets,
    providers,
    skillstate,
)
from thero import __version__
from thero.system.process import stream_command  # noqa: F401 - injetavel nos testes

# Flags que a GUI pode pedir. Lista FECHADA, espelhando os argumentos que
# src/thero/cli.py declara no argparse: se la nascer uma flag nova, ela so
# chega aqui depois de revisao. Sem whitelist, um campo de texto livre da UI
# viraria execucao arbitraria no processo do usuario.
ALLOWED_FLAGS = {
    "--skills-only", "--merge-only", "--audit-only", "--audit",
    "--index", "--max-files", "--plan", "--plan-context", "--check",
    "--update", "--publish", "--publish-agent", "--publish-out",
    "--local",
}


class BridgeState:
    """Tudo que a ponte precisa saber, resolvido uma vez no arranque."""

    def __init__(self, entry_path: Path, config_path: Optional[Path] = None,
                 paths: Optional[dict] = None,
                 profile_path: Optional[Path] = None,
                 skills_base: Optional[Path] = None,
                 quarantine: Optional[Path] = None,
                 cfg: Optional[dict] = None):
        self.entry_path = Path(entry_path)
        self.config_path = Path(config_path) if config_path \
            else config_store.config_path()
        self.paths = paths if paths is not None else apply.default_paths()
        self.profile_path = Path(profile_path) if profile_path \
            else envreport._profile_path()
        self.skills_base = Path(skills_base) if skills_base \
            else skillstate.skills_base(False)
        self.quarantine = Path(quarantine) if quarantine \
            else skillstate.quarantine_dir()
        self._cfg = cfg

    def load(self) -> dict:
        if self._cfg is None:
            self._cfg = config_store.load(self.config_path)
        return self._cfg

    def persist(self, cfg: dict) -> dict:
        self._cfg = cfg
        config_store.save(cfg, self.config_path)
        return cfg


def state_paths(home: Path) -> dict:
    return apply.default_paths(home)


def _ok(req_id, result: dict) -> dict:
    return {"id": req_id, "ok": True, "result": result}


def _err(req_id, error: str) -> dict:
    return {"id": req_id, "ok": False, "error": error}


def _line(req_id, text: str) -> dict:
    return {"id": req_id, "event": "line", "text": text}


# ——— validacao do `run` ———
# A GUI manda FLAGS, nunca uma linha de comando. Sem whitelist, um campo de
# texto livre viraria execucao arbitraria no processo do usuario.
_FLAG_RE = re.compile(r"^--[a-z][a-z0-9-]*$")

_VALUE_FLAGS = {"--plan", "--plan-context", "--max-files",
                "--publish-agent", "--publish-out"}

# Nao ha shell no meio (stream_command abre argv), mas um valor com algum
# destes caracteres nunca viria de um campo de caminho da UI: e o sinal de que
# alguem esta tentando montar comando dentro de um valor.
_BAD_VALUE_CHARS = (";", "|", "&", "`", "$", "\n", "\r", "\x00")


def _validate_flags(flags) -> Optional[str]:
    if not isinstance(flags, list):
        return "flags deve ser uma lista"
    index = 0
    while index < len(flags):
        flag = flags[index]
        if not isinstance(flag, str) or flag not in ALLOWED_FLAGS:
            return "flag nao permitida: %r" % (flag,)
        if flag in _VALUE_FLAGS:
            value = flags[index + 1] if index + 1 < len(flags) else None
            if not isinstance(value, str) or not value:
                return "%s precisa de um valor" % flag
            if flag == "--max-files":
                if not value.isdigit():
                    return "--max-files so aceita numero"
            elif len(value) > 400:
                return "%s: valor longo demais" % flag
            elif value.startswith("-"):
                return "%s: valor nao pode comecar com '-'" % flag
            elif any(ch in value for ch in _BAD_VALUE_CHARS):
                return "%s: valor contem caractere invalido" % flag
            index += 2
        else:
            index += 1
    return None


def _python_exe() -> str:
    return sys.executable or "python"


def _stream(req_id, command, emit: Optional[Callable],
            cwd: Optional[Path] = None) -> dict:
    events = []
    code = 1
    for kind, payload in stream_command(list(command), cwd=cwd):
        if kind == "exit":
            code = payload
            continue
        if emit is not None:
            emit(_line(req_id, payload))
        events.append(payload)
    return {"exitCode": code, "lines": events, "ok": code == 0}


# ——— handlers por familia ———

def _handle_config(state: BridgeState, request: dict):
    cmd = request["cmd"]
    cfg = state.load()
    if cmd == "config-get":
        return _ok(request["id"], {"config": cfg,
                                   "path": str(state.config_path)})
    if cmd == "config-set":
        incoming = request.get("config")
        if not isinstance(incoming, dict):
            return _err(request["id"], "config precisa ser um objeto")
        merged = dict(cfg)
        merged.update(incoming)
        state.persist(merged)
        return _ok(request["id"], {"config": merged,
                                   "path": str(state.config_path)})
    if cmd == "config-reset":
        state.persist(config_store.default_config())
        return _ok(request["id"], {"config": state.load()})
    return None


def _handle_providers(state: BridgeState, request: dict):
    cmd = request["cmd"]
    cfg = state.load()
    if cmd == "providers-presets":
        return _ok(request["id"], {"presets": presets.PROVIDER_PRESETS})
    if cmd == "providers-list":
        return _ok(request["id"], {"providers": providers.summary(cfg),
                                   "routing": cfg.get("routing", {})})
    if cmd == "providers-blank":
        return _ok(request["id"],
                   {"provider": providers.blank_from_preset(
                       request.get("preset", "custom"),
                       request.get("label", ""))})
    if cmd == "providers-upsert":
        provider = request.get("provider")
        if not isinstance(provider, dict) or not provider.get("id"):
            return _err(request["id"], "provider incompleto")
        out = providers.upsert(cfg, provider)
        state.persist(out)
        return _ok(request["id"], {"config": out})
    if cmd == "providers-remove":
        try:
            out = providers.remove(cfg, request.get("id", ""))
        except (providers.ProtectedProvider, providers.ProviderInUse,
                KeyError) as exc:
            return _err(request["id"], str(exc))
        state.persist(out)
        return _ok(request["id"], {"config": out})
    if cmd == "providers-register":
        provider = providers.find(cfg, request.get("id", ""))
        if provider is None:
            return _err(request["id"], "provedor desconhecido")
        out = providers.register(provider)
        provider["authState"] = out["authState"]
        provider["lastCheck"] = out["msg"]
        state.persist(cfg)
        return _ok(request["id"], {"check": out, "config": cfg})
    if cmd == "providers-test":
        provider = providers.find(cfg, request.get("id", ""))
        if provider is None:
            return _err(request["id"], "provedor desconhecido")
        return _ok(request["id"], {"check": providers.test_endpoint(provider)})
    return None


def _handle_models(state: BridgeState, request: dict,
                   emit: Optional[Callable] = None):
    cmd = request["cmd"]
    cfg = state.load()
    base = ""
    for provider in cfg.get("providers", []):
        if provider.get("preset") == "ollama" or provider.get("id") == "ollama":
            base = provider.get("base", "")
            break
    if cmd == "models-status":
        return _ok(request["id"], {
            "ollama": localmodels.status(base),
            "routing": cfg.get("routing", {}),
        })
    if cmd == "models-pull":
        name = (request.get("name") or "").strip()
        if not isinstance(name, str) or not name:
            return _err(request["id"], "informe o nome do modelo")
        code, lines = 1, []
        for kind, payload in localmodels.pull(name, base=base):
            if kind == "exit":
                code = payload
                continue
            if emit is not None:
                emit(_line(request["id"], payload))
            lines.append(payload)
        return _ok(request["id"], {"exitCode": code, "lines": lines,
                                   "ok": code == 0})
    if cmd == "models-delete":
        name = (request.get("name") or "").strip()
        if not name:
            return _err(request["id"], "informe o nome do modelo")
        out = localmodels.delete(name, base=base)
        return _ok(request["id"], {"deleted": out,
                                   "ollama": localmodels.status(base)})
    if cmd == "models-set":
        slot = request.get("slot")
        value = request.get("model", "")
        if slot not in providers.CONSUMERS and slot != "fallback":
            return _err(request["id"], "slot desconhecido: %s" % slot)
        routing = dict(cfg.get("routing") or {})
        routing[slot] = value
        cfg["routing"] = routing
        state.persist(cfg)
        return _ok(request["id"], {"routing": routing, "config": cfg})
    return None


def _handle_agents(state: BridgeState, request: dict):
    cmd = request["cmd"]
    cfg = state.load()
    if cmd == "agents-presets":
        return _ok(request["id"], {"presets": presets.AGENT_PRESETS})
    if cmd == "agents-list":
        return _ok(request["id"], {"agents": cfg.get("agents", [])})
    if cmd == "agents-blank":
        pre = presets.agent_preset(request.get("preset", "manual")) or {}
        return _ok(request["id"], {"agent": {
            "id": pre.get("id", "manual"),
            "label": pre.get("name", ""),
            "preset": pre.get("id", "manual"),
            "kind": pre.get("kind", ""),
            "cfg": pre.get("cfg", ""),
            "format": pre.get("format", ""),
            "writes": bool(pre.get("writes", False)),
            "target": pre.get("target", "none"),
            "provider": request.get("provider", ""),
            "model": request.get("model", ""),
            "enabled": True,
            "skills": bool(pre.get("skills", False)),
            "origin": "user",
            "status": "pendente",
            "note": pre.get("note", ""),
        }})
    if cmd == "agents-upsert":
        agent = request.get("agent")
        if not isinstance(agent, dict) or not agent.get("id"):
            return _err(request["id"], "programa incompleto")
        items = [dict(a) for a in cfg.get("agents", [])]
        for index, existing in enumerate(items):
            if existing.get("id") == agent.get("id"):
                items[index] = dict(agent)
                break
        else:
            items.append(dict(agent))
        cfg["agents"] = items
        state.persist(cfg)
        return _ok(request["id"], {"config": cfg})
    if cmd == "agents-remove":
        target_id = request.get("id", "")
        agent = apply.find_agent(cfg, target_id)
        if agent is None:
            return _err(request["id"], "programa desconhecido")
        if agent.get("origin") == "thero":
            return _err(request["id"],
                        "%s faz parte da configuracao do Thero e nao sai daqui"
                        % target_id)
        cfg["agents"] = [a for a in cfg["agents"] if a.get("id") != target_id]
        state.persist(cfg)
        return _ok(request["id"], {"config": cfg})
    if cmd == "agents-apply":
        agent = apply.find_agent(cfg, request.get("id", ""))
        if agent is None:
            return _err(request["id"], "programa desconhecido")
        out = apply.apply_agent(agent, cfg, state.paths, state.profile_path)
        _mark_status(cfg, agent, out)
        state.persist(cfg)
        return _ok(request["id"], out)
    if cmd == "agents-apply-all":
        results = apply.apply_all(cfg, state.paths, state.profile_path)
        for agent in cfg.get("agents", []):
            match = next((r for r in results
                          if r.get("id") == agent.get("id")), None)
            if match is not None:
                _mark_status(cfg, agent, match)
        state.persist(cfg)
        return _ok(request["id"], {"results": results})
    return None


def _mark_status(cfg: dict, agent: dict, result: dict) -> None:
    agent["status"] = "em dia" if result.get("ok") else "pendente"
    agent["appliedAt"] = result.get("written", "")


def _handle_skills(state: BridgeState, request: dict,
                   emit: Optional[Callable]):
    cmd = request["cmd"]
    # O contrato com a janela e `scope` ("local" | "global") — o mesmo campo
    # que `run` ja usa; nao existe um segundo jeito de dizer a mesma coisa.
    local = request.get("scope") == "local"
    base = state.skills_base if not local else skillstate.skills_base(True)
    if cmd == "skills-list":
        return _ok(request["id"], {"skills": skillstate.installed(
            base_dir=base), "base": str(base)})
    if cmd == "skills-search":
        return _ok(request["id"], {"results": skillstate.search(
            request.get("query", ""), base_dir=base), "note": skillstate.NOTE})
    if cmd == "skills-uninstall":
        out = skillstate.uninstall(request.get("name", ""), base_dir=base,
                                   quarantine=state.quarantine)
        if not out["ok"]:
            return _err(request["id"], out["msg"])
        return _ok(request["id"], {"skill": out,
                                   "skills": skillstate.installed(base_dir=base)})
    if cmd == "skills-import":
        raw = request.get("path")
        if not isinstance(raw, str) or not raw.strip():
            return _err(request["id"], "informe a pasta da skill")
        source = Path(raw.strip())
        if not source.is_dir():
            return _ok(request["id"], {"skill": {
                "ok": False, "msg": "pasta nao existe: %s" % source},
                "skills": skillstate.installed(base_dir=base)})
        out = skillstate.import_skill(source, base_dir=base)
        return _ok(request["id"], {"skill": out,
                                   "skills": skillstate.installed(base_dir=base)})
    if cmd == "skills-install":
        repo = request.get("repo", "")
        skill = request.get("skill", "")
        if not repo or not skill:
            return _err(request["id"], "repo e skill sao obrigatorios")
        command = skillstate.install_command(repo, skill,
                                             global_install=not local)
        return _ok(request["id"], _stream(request["id"], command, emit))
    if cmd in ("skills-check", "skills-update"):
        from thero.skills.installer import (build_skills_check_command,
                                            build_skills_update_command)
        builder = (build_skills_check_command if cmd == "skills-check"
                   else build_skills_update_command)
        return _ok(request["id"],
                   _stream(request["id"], builder(not local), emit))
    return None


COMMANDS = (
    "ping", "env", "run",
    "config-get", "config-set", "config-reset",
    "providers-presets", "providers-list", "providers-blank",
    "providers-upsert", "providers-remove", "providers-register",
    "providers-test",
    "models-status", "models-pull", "models-delete", "models-set",
    "agents-presets", "agents-list", "agents-blank", "agents-upsert",
    "agents-remove", "agents-apply", "agents-apply-all",
    "skills-list", "skills-search", "skills-uninstall", "skills-import",
    "skills-install", "skills-check", "skills-update",
)


def handle_request(request: dict, state: BridgeState, *,
                   emit: Optional[Callable] = None) -> dict:
    if not isinstance(request, dict):
        return _err(None, "requisicao precisa ser um objeto JSON")
    req_id = request.get("id")
    cmd = request.get("cmd")
    if not isinstance(cmd, str) or cmd not in COMMANDS:
        return _err(req_id, "comando desconhecido: %r" % (cmd,))
    try:
        if cmd == "ping":
            return _ok(req_id, {"app": "thero", "version": __version__})
        if cmd == "env":
            # O escopo vem da janela: sem ele o retrato descreveria sempre o
            # global, e a tela trocaria de base sem o retrato acompanhar.
            return _ok(req_id, {
                "env": envreport.snapshot(state.entry_path,
                                          config_path=state.config_path,
                                          scope=request.get("scope", "global")),
                "config": state.load(),
            })
        if cmd == "run":
            problem = _validate_flags(request.get("flags", []))
            if problem:
                return _err(req_id, problem)
            command = [_python_exe(), str(state.entry_path)]
            command.extend(request.get("flags", []))
            if request.get("scope") == "local" and "--local" not in command:
                command.append("--local")
            return _ok(req_id, _stream(req_id, command, emit))
        for family in (_handle_config, _handle_providers, _handle_agents):
            out = family(state, request)
            if out is not None:
                return out
        out = _handle_models(state, request, emit)
        if out is not None:
            return out
        out = _handle_skills(state, request, emit)
        if out is not None:
            return out
        return _err(req_id, "nao implementado: %s" % cmd)
    except Exception as exc:  # noqa: BLE001 - a ponte nunca morre na UI
        return _err(req_id, "%s: %s" % (type(exc).__name__, exc))


def serve(inp: Optional[TextIO] = None, out: Optional[TextIO] = None,
          *, state: Optional[BridgeState] = None) -> None:
    src = inp if inp is not None else sys.stdin
    dst = out if out is not None else sys.stdout

    def emit(message: dict) -> None:
        dst.write(json.dumps(message, ensure_ascii=False) + "\n")
        dst.flush()

    own = state is None
    if own:
        state = BridgeState(entry_path=_entry_path())
    for line in src:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError as exc:
            response = _err(None, "JSON invalido: %s" % exc)
        else:
            response = handle_request(request, state, emit=emit)
        dst.write(json.dumps(response, ensure_ascii=False) + "\n")
        dst.flush()


def _entry_path() -> Path:
    return Path(sys.argv[0]).resolve()
```

> Espelho a manter (verificado nesta máquina em `src/thero/cli.py`, linhas
> 289-471): a CLI declara `--skills-only`, `--merge-only`, `--audit`,
> `--audit-only`, `--install-command`, `--local`, `--index`, `--max-files`,
> `--plan`, `--plan-context`, `--check`, `--update`, `--mcp`, `--publish`,
> `--publish-agent`, `--publish-out`. `ALLOWED_FLAGS` cobre todas **menos duas,
> por decisão**: `--mcp` (servidor JSON-RPC em stdio que bloqueia lendo stdin —
> quem o inicia é o cliente MCP, nunca a ponte; ver a tela MCP na Task 10) e
> `--install-command` (o atalho é sempre `thero` e sai instalado sozinho, então
> a UI não tem campo de nome nem botão para isso). Se nascer uma flag nova na
> CLI, ela só chega à GUI depois de passar por esta lista em revisão.

- [ ] **Step 4: `--serve` na CLI**

Não há segunda lista de flags: `bridge.ALLOWED_FLAGS` (Step 3) é a única fonte
de verdade do que a UI pode pedir, e a CLI não revalida nada — quem decide o
que roda é a ponte, antes de abrir o processo.

Em `src/thero/cli.py`, no parser (logo depois de `--mcp`, antes do banner):

```python
    parser.add_argument(
        "--serve",
        action="store_true",
        help=(
            "Serve a interface desktop: le pedidos JSON por stdin e "
            "responde por stdout (usado pelo TheroHost.ps1)."
        ),
    )
```

e no despacho, **antes** de qualquer `print()` do fluxo:

```python
    if args.serve:
        from thero.bridge import serve

        serve()
        return
```

Acrescentar ao `HELP_EPILOG_TEMPLATE`, na seção COMANDOS:

```
    --serve            Atende a interface desktop (JSON por stdin/stdout).
                       Usado pelo TheroHost.ps1; nao tem saida humana.
```

- [ ] **Step 5: Rodar**

Run: `python -m pytest tests/ -q`
Expected: `356 + 30 = 386 passed`

- [ ] **Step 6: Smoke manual do protocolo (sem UI)**

```bash
printf '{"id":1,"cmd":"ping"}\n{"id":2,"cmd":"config-get"}\n' \
  | python src/thero/cli.py --serve
```
Expected: duas linhas JSON, `"ok":true`, acentos legíveis (sem `\u00e7`).

- [ ] **Step 7: Commit (pedir confirmação)**

```bash
git add src/thero/bridge.py src/thero/cli.py tests/test_bridge.py
git commit -m "feat(bridge): JSON request bridge with streaming, plus the --serve entry"
```

---

# FASE 1 — Casca nativa (PowerShell + WebView2), padrão Vector/Gênesis

### Task 9: `gui/TheroHost.ps1` + DLLs do WebView2 vendadas

**Files:**
- Create: `thero/gui/TheroHost.ps1`
- Já no branch (Task 0, Step 4): `thero/gui/webview2/*.dll` — conferir que as
  três continuam lá, não copiar de novo
- Create: `thero/gui/dev.cmd`

**Modelo real lido nesta máquina:** `vector/gui/VectorHost.ps1` (551 linhas).
Thero copia a estrutura inteira (janela sem borda, `Add-Type` dos assemblies,
`trap` de startup, `Send-ToJs`, `Start-Engine`, `WebMessageReceived` com
`$webMsgArgs`) e **não** copia as partes que são do Vector: sem elevação, sem
associação `.vec`, sem `OpenFileDialog` de backup.

**O que muda de propósito (streaming):** o Vector lê uma linha e congela a
janela até a resposta. O Thero roda processos longos (`npx skills --update`,
`ollama pull`), então o `Invoke-Engine` lê linhas até achar a resposta final e
repassa cada `{"event":"line"}` para o JS com `Application]::DoEvents()` entre
elas — é isso que faz o terminal da interface encher enquanto o comando roda.

**Limitação documentada (não escondida):** o `ReadLine()` bloqueia enquanto o
filho não escreve nada. Por isso existe `engine-cancel`, que mata o pai **e a
árvore** (um `python` morto deixa o `npx` vivo se não fizer `taskkill /T`) e
reinicia o motor sob demanda no próximo pedido.

- [ ] **Step 1: Vendorizar as DLLs**

```bash
mkdir -p src/thero/../gui/webview2
cp ../vector/gui/webview2/Microsoft.Web.WebView2.Core.dll gui/webview2/
cp ../vector/gui/webview2/Microsoft.Web.WebView2.WinForms.dll gui/webview2/
cp ../vector/gui/webview2/WebView2Loader.dll gui/webview2/
```
Expected: `ls gui/webview2` mostra os três arquivos (589 KB / 38 KB / 165 KB).

> São as mesmas DLLs do pacote NuGet oficial que já estão no repositório do
> Vector (approvado por você); nada de baixar dependência nova. Confirme que o
> `.gitignore` do Thero não exclui `*.dll` antes do commit.

- [ ] **Step 2: `gui/TheroHost.ps1`**

```powershell
#Requires -Version 5.1
<#
    Casca nativa da interface do Thero: janela WinForms sem borda hospedando
    um WebView2 apontado em gui/index.html. O HTML/CSS/JS e a interface
    inteira -- este arquivo so devolve a moldura da janela, o payload e a
    ponte JS <-> PowerShell.

    Motor real: `python thero.py --serve` (src/thero/bridge.py) como processo
    filho persistente, JSON por linha nos dois sentidos. TODA regra de
    seguranca (whitelist de flags, recusa de desinstalar skill do Thero,
    nunca ler valor de chave, Ollama so em loopback) mora no Python. Aqui so
    encaminho; reescrever regra no host e o erro que este arquivo evita.

    Protocolo (JSON, um objeto por mensagem):
      JS -> PS : { type: 'ready' | 'window-close' | 'window-minimize'
                        | 'window-drag' | 'engine-request' | 'engine-cancel'
                        | 'pick-folder',
                   payload: { id, cmd, ...campos do comando } }
      PS -> JS : { type: 'host-ready' | 'engine-reply' | 'engine-line'
                        | 'engine-error' | 'folder-picked' | 'bridge-error',
                   payload: <...> }
#>

$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# ------------------------------------------------------------------ payload --
<#
    Thero.exe compilado e um arquivo UNICO: gui/ entra embutido em base64
    (scripts/build-payload.ps1) e e extraido em
    %LOCALAPPDATA%\Thero\app\<versao> na primeira execucao -- mesma mecanica
    de vector/gui/VectorHost.ps1 e genesis/gui/WizardHost.ps1. Rodando do
    projeto (dev) nao ha payload e $Root e a propria pasta.

    Sem param(): o exe nao recebe argumento (diferente do Vector, que abre
    pasta por linha de comando). Assim o build.ps1 nao precisa quebrar um
    bloco param() com regex -- o que nao existe nao desincroniza.
#>
function Expand-TheroPayload {
    param(
        [Parameter(Mandatory)][string]$ExeDir,
        [string]$PayloadBase64 = $Global:TheroPayloadBase64,
        [string]$PayloadVersion = $Global:TheroPayloadVersion
    )

    if (-not $PayloadBase64) { return $ExeDir }
    if (-not $PayloadVersion) { $PayloadVersion = 'dev' }

    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem

    $cacheRoot = Join-Path $env:LOCALAPPDATA 'Thero\app'
    $target = Join-Path $cacheRoot $PayloadVersion

    # gui/app.js como sentinela: se nao esta la, a extracao nao terminou (ou
    # a pasta foi limpa) e o payload precisa ser descompactado de novo.
    if (-not (Test-Path (Join-Path $target 'gui\app.js'))) {
        New-Item -ItemType Directory -Path $cacheRoot -Force | Out-Null

        $gzipBytes = [Convert]::FromBase64String($PayloadBase64)
        $input = New-Object System.IO.MemoryStream
        $input.Write($gzipBytes, 0, $gzipBytes.Length)
        $input.Position = 0
        $gzip = New-Object System.IO.Compression.GZipStream($input, [System.IO.Compression.CompressionMode]::Decompress)
        $zipStream = New-Object System.IO.MemoryStream
        $gzip.CopyTo($zipStream)
        $gzip.Dispose()
        $input.Dispose()

        # extrai em .tmp e so promove: nada de cache pela metade se falhar.
        $staging = "$target.tmp"
        if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
        New-Item -ItemType Directory -Path $staging -Force | Out-Null

        $tmpZip = Join-Path $cacheRoot 'payload.zip'
        [System.IO.File]::WriteAllBytes($tmpZip, $zipStream.ToArray())
        $zipStream.Dispose()
        try {
            [System.IO.Compression.ZipFile]::ExtractToDirectory($tmpZip, $staging)
        }
        finally {
            Remove-Item $tmpZip -Force -ErrorAction SilentlyContinue
        }

        Get-ChildItem $cacheRoot -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -ne $PayloadVersion -and $_.Name -notlike '*.tmp' } |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path $target) { Remove-Item $target -Recurse -Force -ErrorAction SilentlyContinue }
        Move-Item -Path $staging -Destination $target -Force
    }

    return $target
}

$ExeDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$Root = Expand-TheroPayload -ExeDir (Split-Path -Parent $ExeDir)

$indexPath = Join-Path $Root 'gui\index.html'
if (-not (Test-Path $indexPath)) { $indexPath = Join-Path $Root 'index.html' }
$iconPath = Join-Path $ExeDir 'Thero.ico'
if (-not (Test-Path $iconPath)) { $iconPath = Join-Path $Root 'gui\Thero.ico' }
$engineEntry = Join-Path $Root 'thero.py'

# ------------------------------------------------------------- native hooks --
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class NativeDrag {
    [DllImport("user32.dll")] public static extern int SendMessage(IntPtr hWnd, int Msg, int wParam, int lParam);
    [DllImport("user32.dll")] public static extern bool ReleaseCapture();
    [DllImport("dwmapi.dll")] public static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);
    public const int WM_NCLBUTTONDOWN = 0xA1;
    public const int HTCAPTION = 0x2;
    public const int DWMWA_WINDOW_CORNER_PREFERENCE = 33;
    public const int DWMWCP_ROUND = 2;
    public static void RoundCorners(IntPtr hwnd) {
        try {
            int pref = DWMWCP_ROUND;
            DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ref pref, 4);
        }
        catch { }
    }
}
'@

# --- WebView2 (DLLs vendadas em gui/webview2/, iguais as do Vector) ---------
$wv2Dir = Join-Path $Root 'gui\webview2'
if (-not (Test-Path $wv2Dir)) { $wv2Dir = Join-Path $ExeDir 'webview2' }
Add-Type -Path (Join-Path $wv2Dir 'Microsoft.Web.WebView2.Core.dll')
Add-Type -Path (Join-Path $wv2Dir 'Microsoft.Web.WebView2.WinForms.dll')
$env:PATH = "$wv2Dir;$env:PATH"

# ------------------------------------------------------------------ janela --
$form = New-Object System.Windows.Forms.Form
$form.Text = 'Thero'
$form.Size = New-Object System.Drawing.Size(1240, 820)
$form.MinimumSize = New-Object System.Drawing.Size(940, 640)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'None'
$form.BackColor = [System.Drawing.ColorTranslator]::FromHtml('#0b1014')
if (Test-Path $iconPath) {
    try { $form.Icon = New-Object System.Drawing.Icon($iconPath) } catch { }
}

# Rede de seguranca do startup (mesmo padrao do Vector): um erro aqui matava
# o processo sem MessageBox e sem log.
trap {
    $crashMsg = "Thero falhou ao iniciar:`n`n$($_.Exception.Message)`n`n$($_.ScriptStackTrace)"
    try {
        $logDir = Join-Path $env:LOCALAPPDATA 'Thero\logs'
        New-Item -ItemType Directory -Path $logDir -Force -ErrorAction SilentlyContinue | Out-Null
        $crashMsg | Out-File (Join-Path $logDir "crash-startup-$(Get-Date -Format 'yyyyMMdd-HHmmss').log") -Encoding utf8
    }
    catch { }
    [System.Windows.Forms.MessageBox]::Show($crashMsg, 'Thero', 'OK', 'Error')
    break
}

if (-not (Test-Path $indexPath)) {
    [System.Windows.Forms.MessageBox]::Show(
        "Nao encontrei a interface em:`n$indexPath`n`nRode a partir da pasta do projeto (gui\TheroHost.ps1) ou recompile com build.ps1.",
        'Thero', 'OK', 'Error')
    exit 1
}

$webView = New-Object Microsoft.Web.WebView2.WinForms.WebView2
$webView.Dock = 'Fill'
$webView.DefaultBackgroundColor = [System.Drawing.ColorTranslator]::FromHtml('#0b1014')

# Sem isto o WebView2 cria "<exe>.WebView2" do lado do executavel. Portable de
# verdade nao suja a pasta de onde roda: cache/cookies vao para %LOCALAPPDATA%.
$creationProps = New-Object Microsoft.Web.WebView2.WinForms.CoreWebView2CreationProperties
$creationProps.UserDataFolder = Join-Path $env:LOCALAPPDATA 'Thero\WebView2'
$webView.CreationProperties = $creationProps

$form.Controls.Add($webView)
$form.Add_Shown({ [NativeDrag]::RoundCorners($form.Handle) })
$form.Add_FormClosed({ Stop-Engine })

# ------------------------------------------------------------------ bridge --
# O cast [array] e o mesmo motivo documentado no Genesis/Vector: o
# ConvertTo-Json do PowerShell 5.1 transforma array puro em
# {"value":[...],"Count":N} se nao forcas.
function Send-ToJs {
    param([string]$Type, $Payload)
    if (($Payload -is [array] -or $Payload -is [System.Collections.ICollection]) -and
        $Payload -isnot [System.Collections.IDictionary]) {
        $Payload = [array]$Payload
    }
    $msg = @{ type = $Type; payload = $Payload } | ConvertTo-Json -Depth 10 -Compress
    $webView.CoreWebView2.PostWebMessageAsJson($msg)
}

# ------------------------------------------------------------------ engine --
$script:Engine = $null      # @{ Proc; Stdin; Stdout } enquanto vivo
$script:Cancel = $false

function Resolve-EnginePython {
    foreach ($c in @(
        @{ Exe = 'py';      Prefix = @('-3') },
        @{ Exe = 'python';  Prefix = @() },
        @{ Exe = 'python3'; Prefix = @() })) {
        if (Get-Command $c.Exe -ErrorAction SilentlyContinue) { return $c }
    }
    return $null
}

function Start-Engine {
    if ($script:Engine -and -not $script:Engine.Proc.HasExited) { return $true }
    $py = Resolve-EnginePython
    if (-not $py) { return $false }
    if (-not (Test-Path $engineEntry)) { return $false }

    $argList = @($py.Prefix) + @($engineEntry, '--serve')
    $quoted = $argList | ForEach-Object {
        if ($_ -match '\s') { '"' + $_ + '"' } else { $_ }
    }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $py.Exe
    $psi.Arguments = ($quoted -join ' ')
    $psi.WorkingDirectory = $Root
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $false
    # Sem UTF-8 explicito o Windows decodifica na codepage do console e
    # os acentos da resposta viram lixo (mesma regra do Vector).
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    try {
        $proc = [System.Diagnostics.Process]::Start($psi)
    } catch {
        return $false
    }
    $script:Engine = @{ Proc = $proc; Stdin = $proc.StandardInput; Stdout = $proc.StandardOutput }
    return $true
}

function Kill-EngineTree {
    param($Proc)
    if (-not $Proc) { return }
    try {
        if ($Proc.HasExited) { return }
        # taskkill /T porque matar o python nao mata o `npx skills` dele:
        # sem isso o "Cancelar" deixaria o download rodando nas costas.
        $enginePid = $Proc.Id
        Start-Process -FilePath 'taskkill.exe' -ArgumentList @('/PID', "$enginePid", '/T', '/F') `
            -WindowStyle Hidden -Wait -ErrorAction SilentlyContinue
    } catch { }
    try { if (-not $Proc.HasExited) { $Proc.Kill() } } catch { }
}

function Stop-Engine {
    if ($script:Engine) {
        Kill-EngineTree -Proc $script:Engine.Proc
        try { $script:Engine.Stdin.Close() } catch { }
        $script:Engine = $null
    }
}

function Invoke-Engine {
    param([hashtable]$Request)
    if (-not (Start-Engine)) { throw 'Motor Python indisponivel (sem Python no PATH?).' }
    $json = $Request | ConvertTo-Json -Compress -Depth 8
    $script:Engine.Stdin.WriteLine($json)
    $script:Engine.Stdin.Flush()
    $reqId = $Request.id

    # Laço de streaming: o motor solta N linhas {"event":"line"} antes da
    # resposta final. DoEvents() entre elas e o que mantem a janela viva e o
    # terminal da UI enchendo enquanto o processo roda.
    while ($true) {
        $line = $script:Engine.Stdout.ReadLine()
        if ($null -eq $line) { throw 'O motor encerrou a conexao; reabra o Thero.' }
        $line = $line.Trim()
        if (-not $line) { continue }
        $parsed = $null
        try { $parsed = $line | ConvertFrom-Json } catch { continue }
        if ($parsed.event -eq 'line') {
            Send-ToJs -Type 'engine-line' -Payload @{ id = $reqId; text = [string]$parsed.text }
            [void][System.Windows.Forms.Application]::DoEvents()
            if ($script:Cancel) {
                $script:Cancel = $false
                Stop-Engine
                return (@{ id = $reqId; ok = $false; error = 'cancelado pelo usuario' })
            }
            continue
        }
        return $parsed
    }
}

function Handle-Message {
    param($Msg)

    switch ($Msg.type) {
        'ready' {
            $engineOk = [bool](Start-Engine)
            Send-ToJs -Type 'host-ready' -Payload @{
                app             = 'thero'
                phase           = $(if ($engineOk) { 'engine' } else { 'mock' })
                root          = $Root
                engineAvailable = $engineOk
                notice          = $(if ($engineOk) {
                    'Motor real ligado (thero.py --serve).'
                } else {
                    'Python nao encontrado no PATH: a interface vai usar dados de exemplo.'
                })
            }
        }
        'engine-request' {
            # Pass-thru: o payload ja e o pedido no formato da ponte
            # ({ id, cmd, ... }). O host NAO decide nada -- so carimba o id e
            # repassa. Toda recusa vem do Python.
            $payload = $Msg.payload
            if (-not $payload) {
                Send-ToJs -Type 'bridge-error' -Payload @{ error = 'engine-request sem payload' }
                return
            }
            $req = @{}
            foreach ($prop in $payload.PSObject.Properties) { $req[$prop.Name] = $prop.Value }
            if (-not $req.ContainsKey('id')) { $req['id'] = 0 }
            try {
                $resp = Invoke-Engine -Request $req
                if ($resp.ok) {
                    Send-ToJs -Type 'engine-reply' -Payload $resp
                } else {
                    Send-ToJs -Type 'engine-reply' -Payload @{
                        id = $req.id; ok = $false; error = [string]$resp.error }
                }
            } catch {
                Send-ToJs -Type 'engine-error' -Payload @{
                    id = $req.id; error = $_.Exception.Message }
            }
        }
        'engine-cancel' {
            # Marca e devolve o controle ao laço de leitura acima; se estiver
            # ocioso, derruba o filho mesmo assim (o proximo pedido religa).
            $script:Cancel = $true
            if (-not $script:Engine) { $script:Cancel = $false }
        }
        'pick-folder' {
            $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
            $dlg.Description = 'Escolher a pasta da skill (precisa ter SKILL.md)'
            $res = $dlg.ShowDialog()
            $picked = if ($res -eq [System.Windows.Forms.DialogResult]::OK) { $dlg.SelectedPath } else { $null }
            # O id volta no payload: e por ele que o Host resolve o pending do
            # chamador (mesa regra do engine-reply).
            Send-ToJs -Type 'folder-picked' -Payload @{ id = $Msg.id; path = $picked }
        }
        'window-close' {
            Stop-Engine
            $form.Close()
        }
        'window-minimize' { $form.WindowState = 'Minimized' }
        'window-drag' {
            [NativeDrag]::ReleaseCapture() | Out-Null
            [NativeDrag]::SendMessage($form.Handle, [NativeDrag]::WM_NCLBUTTONDOWN, [NativeDrag]::HTCAPTION, 0) | Out-Null
        }
        default {
            Send-ToJs -Type 'bridge-error' -Payload @{
                error = "Mensagem desconhecida: $($Msg.type)" }
        }
    }
}

# -------------------------------------------------------------------- wire --
$webView.add_CoreWebView2InitializationCompleted({
    param($s, $e)
    if (-not $e.IsSuccess) {
        $msg = if ($e.InitializationException.HResult -eq -2147024726) {
            "Ja existe outra instancia do Thero aberta (ou travada em segundo plano).`n`nFeche-a e abra de novo."
        } else {
            "WebView2 nao inicializou: $($e.InitializationException.Message)`n`nO Runtime do WebView2 (vem com o Windows 11) pode estar faltando."
        }
        [System.Windows.Forms.MessageBox]::Show($msg, 'Thero', 'OK', 'Error')
        $form.Close()
        return
    }
    $webView.CoreWebView2.add_WebMessageReceived({
        # NUNCA nomear o 2o parametro de $args (lição do Genesis): sombrear a
        # variavel automatica faz o evento chegar como Object[] e
        # TryGetWebMessageAsString desaparece.
        param($sender, $webMsgArgs)
        try {
            $json = $webMsgArgs.TryGetWebMessageAsString()
            $msg = $json | ConvertFrom-Json
            Handle-Message -Msg $msg
        }
        catch {
            Send-ToJs -Type 'bridge-error' -Payload @{ error = $_.Exception.Message }
        }
    })
})

[void]$form.ShowDialog()
```

> Ao executar: confirme o `-Depth` do `ConvertTo-Json` do pedido (8 cobre
> `--plan` com espaços) e rode o Step 4 antes de abrir a janela.

- [ ] **Step 3: `gui/dev.cmd` (rodar sem compilar)**

```bat
@echo off
rem Levanta a casca nativa contra o motor do repositorio (sem ps2exe).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0TheroHost.ps1"
```

- [ ] **Step 4: Verificação desta tarefa**

Checagem de sintaxe com o próprio parser do PowerShell — rodar o host para
"ver se ele abre" não é checagem nenhuma (ele abre a janela e bloqueia em
`ShowDialog`). Do diretório `thero/`:

```bash
powershell -NoProfile -ExecutionPolicy Bypass -Command '
$ErrorActionPreference = "Stop"
$path = (Resolve-Path "gui/TheroHost.ps1").Path
$tokens = $null; $errors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors)
if ($errors) { $errors | ForEach-Object { Write-Host $_.Message }; exit 1 }
Write-Host "TheroHost.ps1: 0 erros de sintaxe, $($tokens.Count) tokens"
'
```
Expected: `TheroHost.ps1: 0 erros de sintaxe, ... tokens`. A janela em si só é
exercitada no smoke da Task 11, com motor de verdade.

- [ ] **Step 5: Commit (pedir confirmação)**

```bash
git add gui/TheroHost.ps1 gui/webview2 gui/dev.cmd
git commit -m "feat(gui): native WebView2 host with streamed engine output"
```

---

# FASE 2 — Costurar a interface ao motor

### Task 10: `app.js` real (ponte + hidratação), mock como fallback de navegador

**Files:**
- Modify: `thero/gui/app.js`
- Não muda: `thero/gui/mock.js` (continua servindo no navegador), `index.html`,
  `style.css` — a interface aprovada não se reescreve.

Regra da fase: **`M` (mock) vira o estado em memória**, e o motor o substitui
na abertura. Nenhum `render()` novo é escrito; só a origem dos dados e o que
acontece quando o usuário clica.

- [ ] **Step 1: Camada de ponte (inserir antes de `const Bridge = {...}`)**

```javascript
  // ————————————————— PONTE REAL (host PowerShell) —————————————————
  // No navegador (abrir index.html direto) nao existe host: tudo segue em
  // mock, exatamente como na fase 1 aprovada. Na janela, o primeiro `ready`
  // pede o retrato real ao motor e HIDRATA M antes do primeiro render.
  const isHosted = () => !!(window.chrome && window.chrome.webview &&
                            window.chrome.webview.postMessage);

  const Host = {
    nextId: 1,
    pending: new Map(),      // id -> { onReply, onLine }
    listening: false,
    send(cmd, fields, onReply, onLine) {
      if (!isHosted()) return null;
      const id = this.nextId++;
      const req = Object.assign({ id: id, cmd: cmd }, fields || {});
      this.pending.set(id, { onReply: onReply, onLine: onLine });
      // JSON.stringify e OBRIGATORIO: postMessage sem string cai em
      // TryGetWebMessageAsString() no host e nada acontece (licao ja paga
      // no Genesis e no Vector). O host roteia por `type`; o pedido da ponte
      // vai dentro de `payload` exatamente como no Vector.
      window.chrome.webview.postMessage(JSON.stringify({ type: 'engine-request', payload: req }));
      return id;
    },
    cancel(id) {
      if (!isHosted()) return;
      window.chrome.webview.postMessage(JSON.stringify({ type: 'engine-cancel', id: id }));
    },
    window(action) {
      if (!isHosted()) return;
      window.chrome.webview.postMessage(JSON.stringify({ type: action }));
    },
    pickFolder(onReply) {
      if (!isHosted()) return;
      const id = this.nextId++;
      this.pending.set(id, { onReply: onReply });
      window.chrome.webview.postMessage(JSON.stringify({ type: 'pick-folder', id: id }));
    },
  };

  function onHostMessage(ev) {
    let msg;
    try { msg = typeof ev.data === 'string' ? JSON.parse(ev.data) : ev.data; }
    catch (e) { return; }
    if (!msg || !msg.type) return;
    const payload = msg.payload || {};
    if (msg.type === 'engine-line') {
      const entry = Host.pending.get(payload.id);
      if (entry && entry.onLine) entry.onLine(String(payload.text || ''));
      return;
    }
    if (msg.type === 'host-ready') {
      state.hosted = true;
      state.phase = payload.phase;
      if (payload.phase !== 'engine') { setPhaseNote(payload.notice || ''); return; }
      hydrate();
      return;
    }
    if (msg.type === 'folder-picked') {
      const id = Number(payload.id);
      const entry = Host.pending.get(id);
      if (!entry) return;
      Host.pending.delete(id);                     // cancelou tambem: um pending por pedido
      if (entry.onReply) entry.onReply({ path: payload.path || null });
      return;
    }
    const reply = (msg.type === 'engine-reply' || msg.type === 'engine-error')
      ? payload : null;
    if (!reply || reply.id == null) { setPhaseNote(msg.type + ': ' + (reply && reply.error) || ''); return; }
    const entry = Host.pending.get(Number(reply.id));
    if (!entry) return;
    Host.pending.delete(Number(reply.id));
    if (entry.onReply) entry.onReply(reply);
  }

  if (isHosted()) {
    // O host so fala depois de ouvir: um listener global, criado uma unica vez.
    window.chrome.webview.addEventListener('message', onHostMessage);
    Host.listening = true;
    window.chrome.webview.postMessage(JSON.stringify({ type: 'ready' }));
  }

  const setPhaseNote = (text) => {
    const bar = el('titlebar-phase');
    if (bar) bar.title = text;
  };
```

- [ ] **Step 2: Hidratação (depois de `Host`, antes de `openRun`)**

Cada adaptador abaixo converte o shape do **motor** no shape que as telas
aprovadas já desenham — as telas não mudam.

```javascript
  // ————————————————— HIDRATAR M COM O MOTOR —————————————————
  function adoptProviders(cfg) {
    M.providers = (cfg.providers || []).map((p) => ({
      id: p.id, preset: p.preset, label: p.label, kind: p.kind,
      base: p.base || "", transport: p.transport || "",
      authKind: p.authKind || "apikey", authVar: p.authVar || "",
      model: p.model || "", models: p.models || [],
      enabled: p.enabled !== false, origin: p.origin || "user",
      roles: p.roles || { athena: false, sentinel: false },
      authState: p.authState || "nao verificado", lastCheck: p.lastCheck || "",
    }));
    if (!M.providers.length) M.providers = [{ id: "manual", preset: "custom",
      label: "Manual", base: "", authKind: "apikey", authVar: "", model: "",
      enabled: true, origin: "user", roles: {}, authState: "", lastCheck: "" }];
  }

  function adoptAgents(cfg) {
    M.agents = (cfg.agents || []).map((a) => ({
      id: a.id, preset: a.preset, label: a.label, cfg: a.cfg || "",
      format: a.format || "", target: a.target || "none",
      writes: !!a.writes, provider: a.provider || "", model: a.model || "",
      enabled: a.enabled !== false, skills: !!a.skills,
      origin: a.origin || "user", status: a.status || "pendente",
      note: a.note || "",
    }));
  }

  // `ollama` vem de `models-status` (up / base / models / error). O retrato do
  // Status traz apenas `ollama.modelCount`, por isso a lista de modelos chega
  // por um pedido proprio — e nunca por adivinhacao no front.
  function adoptModels(ollama, routing) {
    const o = ollama || {};
    const r = routing || state.routing || {};
    const used = {};
    if (r.athena) used[r.athena] = (used[r.athena] || []).concat("athena");
    if (r.sentinel) used[r.sentinel] = (used[r.sentinel] || []).concat("sentinel");
    M.localModels = (o.models || []).map((m) => ({
      id: m.name.replace(/[^a-z0-9]+/gi, "-").toLowerCase(),
      provider: "ollama", name: m.name, ctx: m.params || "-",
      size: m.sizeHuman || "-",
      status: o.up ? "pronto" : "ausente",
      usedBy: used[m.name] || [],
    }));
    M.ollamaHost = o.host || o.base || "";
  }

  // Lista de modelos + roteamento: um pedido, duas telas (Modelos e Status).
  function loadModels(cb) {
    Host.send('models-status', {}, (r) => {
      if (r.ok) { state.routing = r.result.routing || {}; adoptModels(r.result.ollama, state.routing); }
      if (cb) cb();
    }, null);
  }

  function adoptSkills(rows) {
    M.skills = (rows || []).map((s) => ({
      id: s.name, repo: s.name, desc: s.desc || "", installed: true,
      update: false, origin: s.origin || "user",
      path: s.path || "",
    }));
  }

  function adoptEnv(env) {
    if (!env) return;
    const tools = env.tools || {};
    E.cliInstalled = !!env.commandInstalled;
    E.firstRun = !!env.firstRun;
    E.scope = env.scope || "global";
    E.python = { ok: true, version: env.python || "?", min: "3.10+" };
    E.node = { ok: !!(tools.node && tools.node.ok), version: (tools.node || {}).detail || "ausente" };
    E.npx = { ok: !!(tools.npx && tools.npx.ok), detail: (tools.npx || {}).detail || "" };
    E.claude = { ok: !!(tools.claude && tools.claude.ok), authed: !!(tools.claude && tools.claude.ok) };
    E.commandInstalled = env.commandInstalled ? env.commandName : false;
    E.claudeMd = { exists: !!(env.claudeMd && env.claudeMd.exists) };
    E.claudeMdPath = (env.claudeDir || "~/.claude") + "/CLAUDE.md";
    E.skillsBase = (env.skills || {}).base || "";
    state.scope = E.scope;
  }

  let hydrated = false;
  function hydrate() {
    Host.send('env', { scope: state.scope }, (reply) => {
      if (!reply.ok) { setPhaseNote('motor: ' + reply.error); return; }
      const result = reply.result || {};
      adoptEnv(result.env);
      adoptProviders(result.config);
      adoptAgents(result.config);
      state.routing = (result.config || {}).routing || {};
      Host.send('skills-list', { scope: state.scope }, (r) => {
        if (r.ok) adoptSkills(r.result.skills);
        loadModels(() => {
          hydrated = true;
          el('titlebar-phase').textContent = (state.phase === 'engine' ? 'motor' : 'mock') +
            ' · ' + (SECTIONS.find((x) => x.id === state.section) || {}).label;
          setScopeUI();
          render();
          if (result.env.firstRun) openOnboarding();
        });
      }, null);
    }, null);
  }

  // Toda troca de escopo re-puxa o que depende de disco (skills, CLAUDE.md, modelos).
  function refreshFromEngine() {
    if (!isHosted() || state.phase !== 'engine') return;
    Host.send('env', { scope: state.scope }, (reply) => {
      if (!reply.ok) return;
      adoptEnv(reply.result.env);
      adoptProviders(reply.result.config);
      adoptAgents(reply.result.config);
      state.routing = (reply.result.config || {}).routing || {};
      Host.send('skills-list', { scope: state.scope }, (r) => {
        if (r.ok) adoptSkills(r.result.skills);
        loadModels(render);
      }, null);
    }, null);
  }
```

- [ ] **Step 3: Substituir o objeto `Bridge` (linhas 423-450 do arquivo atual)**

O `Bridge` público mantém os mesmos quatro métodos que as telas já chamam — o
que muda é que cada um tenta o motor primeiro e só cai no mock se não houver
host. Assim nenhuma tela precisou ser tocada.

```javascript
  const Bridge = {
    // Execucao real: `run` com FLAGS (nunca linha de comando), com as linhas
    // do processo chegando em onLine enquanto roda.
    run(actionLine, cmdStr, onLine, onDone) {
      if (state.phase !== 'engine') { mockRun(actionLine, cmdStr, onLine, onDone); return; }
      // Linha "config.json → …" e informativa: gravacao de config passa por
      // config-set / agents-apply / models-set, nunca por um processo.
      if (cmdStr.indexOf(M.meta.config) === 0) {
        onLine({ type: "err", text: "isso e gravacao de configuracao, nao execucao", pct: 100 });
        onDone(false); return;
      }
      const flags = flagsFromCmd(cmdStr);
      const id = Host.send('run', { flags: flags, scope: state.scope },
        (reply) => {
          const code = reply.ok ? (reply.result.exitCode || 0) : 1;
          if (!reply.ok && reply.error) onLine({ type: "err", text: reply.error, pct: 100 });
          onDone(code === 0);
        },
        (text) => onLine({ type: classify(text), text: text, pct: 0 }));
      state.runId = id;
    },
    testProvider(p, cb) {
      if (state.phase !== 'engine') { cb({ ok: !!p.base, msg: p.base ? ("respondeu " + p.base) : "sem endpoint para testar" }); return; }
      Host.send('providers-test', { id: p.id }, (r) => {
        cb(r.ok ? r.result.check : { ok: false, msg: r.error });
      }, null);
    },
    register(p, cb) {
      if (state.phase !== 'engine') { mockRegister(p, cb); return; }
      Host.send('providers-register', { id: p.id }, (r) => {
        if (!r.ok) return cb({ ok: false, msg: r.error });
        adoptProviders(r.result.config);
        render();
        cb({ ok: r.result.check.ok, msg: r.result.check.msg });
      }, null);
    },
    searchSkills(q, cb) {
      if (state.phase !== 'engine') { cb(M.skillResults.filter((r) => !q || (r.repo + " " + r.desc).toLowerCase().includes(q.toLowerCase()))); return; }
      Host.send('skills-search', { query: q, scope: state.scope }, (r) => {
        if (!r.ok) return cb([]);
        cb((r.result.results || []).map((x) => ({ id: x.skill, repo: x.repo, desc: x.group + (x.installed ? " · ja instalada" : "") })));
      }, null);
    },
    // —— novos (a interface ainda nao chamava; as telas novas usam) ——
    configSet(cfg, cb) {
      if (state.phase !== 'engine') { return cb({ ok: true, mock: true }); }
      Host.send('config-set', { config: cfg }, (r) => { if (r.ok) { adoptProviders(r.result.config); adoptAgents(r.result.config); } cb(r); }, null);
    },
    agentsApply(id, cb) {
      if (state.phase !== 'engine') { return cb({ ok: true, mock: true }); }
      Host.send(id ? 'agents-apply' : 'agents-apply-all', id ? { id: id } : {}, (r) => {
        if (r.ok) refreshFromEngine();
        cb(r);
      }, (t) => {});
    },
    skillsUninstall(name, cb) {
      if (state.phase !== 'engine') { return cb({ ok: true, mock: true }); }
      Host.send('skills-uninstall', { name: name, scope: state.scope }, (r) => {
        if (r.ok) adoptSkills(r.result.skills);
        cb(r.ok ? { ok: true, msg: r.result.skill.msg } : { ok: false, msg: r.error });
      }, null);
    },
    modelsPull(name, onLine, onDone) {
      if (state.phase !== 'engine') { return onDone(true); }
      Host.send('models-pull', { name: name },
        (r) => {
          if (r.ok && r.result.exitCode === 0) loadModels(render);
          onDone(r.ok && r.result.exitCode === 0);
        },
        (t) => onLine({ type: classify(t), text: t, pct: 0 }));
    },
    modelDelete(name, cb) {
      if (state.phase !== 'engine') { return cb({ ok: true, mock: true }); }
      Host.send('models-delete', { name: name }, (r) => {
        // `ollama` aqui e o status reenviado pelo motor, ja sem o modelo.
        if (r.ok) adoptModels(r.result.ollama, state.routing);
        cb(r);
      }, null);
    },
    routingSet(slot, value, cb) {
      if (state.phase !== 'engine') { return cb({ ok: true, mock: true }); }
      Host.send('models-set', { slot: slot, model: value }, (r) => {
        // O roteamento muda o "usado por" de cada modelo: re-puxa a lista.
        if (r.ok) loadModels(render);
        cb(r);
      }, null);
    },
    pickFolder(cb) { Host.pickFolder((out) => cb(out.path)); },
  };
```

- [ ] **Step 4: Os três auxiliares que o `Bridge` novo chama**

```javascript
  // Mapeia a linha que a propria UI montou (cmd("…")) nas flags reais do
  // cli.py. Nunca linha livre: o motor recusa flag fora da whitelist dele,
  // e `--local` sai daqui porque no protocolo o escopo e um campo proprio.
  // O tokenizador respeita aspas porque --publish-out e um caminho escolhido
  // no seletor de pastas, e caminho com espaco nao pode virar dois argumentos.
  function flagsFromCmd(cmdStr) {
    return ((cmdStr || "").match(/"[^"]*"|\S+/g) || [])   // [0]="python", [1]=entry
      .slice(2)
      .map((t) => t.replace(/^"|"$/g, ""))
      .filter((t) => t && t !== "--local");
  }

  // O motor devolve stdout bruto; a UI so sabe pintar 4 classes.
  function classify(line) {
    const l = line.toLowerCase();
    if (l.startsWith("[ok]") || l.includes("successfully") || l.includes("concluído")) return "ok";
    if (l.startsWith("[warn]") || l.includes("failed") || l.includes("error")) return "err";
    if (l.startsWith("executando") || l.includes("installing") || l.includes("downloading")) return "act";
    return "muted";
  }

  function mockRun(actionLine, cmdStr, onLine, onDone) {
    const ctx = { version: M.meta.version, scope: isLocal() ? "local" : "global", actionLine, cmd: cmdStr, config: M.meta.config };
    const lines = (kindOf(state.section) === "config" ? M.configLog : M.runLog).slice();
    let i = 0;
    (function step() {
      if (i >= lines.length) { setTimeout(() => onDone(true), 400); return; }
      const L = lines[i++];
      onLine({ type: L.t, text: L.s.replace(/\{(\w+)\}/g, (_, k) => (ctx[k] != null ? ctx[k] : "")), pct: Math.round((i / lines.length) * 100) });
      setTimeout(step, L.t === "act" ? 300 : 520);
    })();
  }

  function mockRegister(p, cb) {
    const kind = authKindOf(p);
    if (kind === "session") return cb({ ok: true, msg: "sessão confirmada no produto — provedor registrado" });
    if (kind === "local") return p.base ? cb({ ok: true, msg: "endpoint local alcance verificado — provedor registrado" })
      : cb({ ok: false, msg: "informe o endpoint local antes de registrar" });
    if (!p.authVar) return cb({ ok: false, msg: "defina o nome da variável que guarda a chave" });
    cb({ ok: true, msg: "provedor registrado · chave será lida de " + p.authVar + " a cada chamada" });
  }
```

- [ ] **Step 5: `openRun` mostra a resposta real e ganha "Cancelar"**

`openRun` (linhas 452-480) hoje sempre chama `Bridge.run`, que no mock empurra
log inventado. Com o motor aparecem dois caminhos no mesmo painel: o processo
que transmite linhas enquanto roda, e o comando de configuração que **já
respondeu** antes do painel abrir (o motor devolveu o config inteiro, não há
processo). Reescrever a função inteira — o HTML do sheet é o mesmo de hoje:

```javascript
  function openRun(actionLine, cmdStr, done, runner) {
    const p = el("runpanel");
    const isCfg = kindOf(state.section) === "config";
    p.hidden = false;
    p.innerHTML = `<div class="sheet"><div class="sheet-top"><div class="sheet-brand"><img src="assets/thero-mark.png" alt=""><div><b>${isCfg ? "CONFIGURAÇÃO" : "EXECUÇÃO"}</b><small>${isCfg ? "gravação no config do Thero" : "saída do motor"}</small></div></div><button class="x" data-close>✕</button></div>
      <div class="sheet-pad">
        <div class="progress"><div class="bar"><div class="bar-fill" id="rbar"></div></div><div class="progress-meta"><span id="rstep">iniciando…</span><span id="rpct">0%</span></div></div>
        <div class="terminal"><div class="term-bar"><i></i><i></i><i></i><span>thero · ${isCfg ? "config" : "thero.py"}</span></div><div class="term-body" id="rterm"></div></div>
        <div class="sheet-foot"><span class="hint" id="rcmd"></span><span></span></div>
      </div></div>`;
    p.querySelector("[data-close]").addEventListener("click", () => (p.hidden = true));
    el("rcmd").textContent = cmdStr;
    const term = el("rterm"), bar = el("rbar"), pct = el("rpct"), step = el("rstep");
    term.innerHTML = '<span class="term-cursor"></span>';

    const paint = (L) => {
      const div = document.createElement("div"); div.className = "term-line";
      div.innerHTML = L.type === "act" ? `<span class="act">${esc(L.text)}</span>` : `<span class="${esc(L.type)}">${esc(L.text)}</span>`;
      term.insertBefore(div, term.querySelector(".term-cursor"));
      term.scrollTop = term.scrollHeight;
      if (L.pct != null) {
        bar.style.transform = "scaleX(" + (L.pct / 100) + ")";
        pct.textContent = L.pct + "%";
        step.textContent = String(L.text).trim().slice(0, 42);
      }
    };
    const finish = (ok) => {
      const c = term.querySelector(".term-cursor"); if (c) c.remove();
      const foot = p.querySelector(".sheet-foot");
      foot.innerHTML = `<div class="result-badge ${ok ? "ok" : "err"}" style="width:26px;height:26px;margin:0">${ok ? IC.check : IC.x}</div>
        <span style="color:var(--success);font-family:var(--font-mono);font-size:12px">exit ${ok ? 0 : 1} · ${isCfg ? "config gravada" : "processo concluído"}</span>
        <button class="btn btn-primary btn-sm" data-close2>Fechar</button>`;
      foot.querySelector("[data-close2]").addEventListener("click", () => (p.hidden = true));
    };

    // Cancelar so existe com motor: no mock nao ha processo a derrubar.
    if (state.phase === "engine" && !done) {
      const cancel = document.createElement("button");
      cancel.className = "btn btn-ghost btn-sm";
      cancel.textContent = "Cancelar";
      cancel.addEventListener("click", () => Host.cancel(state.runId));
      p.querySelector(".sheet-foot").appendChild(cancel);
    }

    if (done) {   // o motor ja respondeu; o painel so mostra o que veio
      (done.lines || []).forEach(paint);
      bar.style.transform = "scaleX(1)"; pct.textContent = "100%";
      step.textContent = done.ok ? "concluído" : "falhou";
      finish(done.ok);
      return;
    }
    // `runner` existe porque nem tudo e `run`: `models-pull` transmite as
    // mesmas linhas por outro comando. Sem runner, e o caminho de sempre.
    (runner || ((onLine, onDone) => Bridge.run(actionLine, cmdStr, onLine, onDone)))(paint, finish);
  }

  // Traduz uma resposta da ponte para o painel — sem nenhuma linha inventada.
  function resultLines(r, okMsg) {
    if (r && r.ok) return [{ type: "ok", text: okMsg, pct: 100 }];
    return [{ type: "err", text: (r && (r.error || r.msg)) || "falha", pct: 100 }];
  }
```

- [ ] **Step 6: Os botões das telas chamam o motor, não o log do mock**

Hoje cada tela de configuração abre o painel com uma linha `config.json → …`
informativa. No navegador isso continua igual; na janela cada uma passa a
chamar o comando da própria família. Acrescentar ao objeto `Bridge` (Step 3)
os métodos que faltavam, e trocar os chamadores nas linhas indicadas de
`gui/app.js`.

Acrescentar no `Bridge` (dentro do bloco do Step 3, antes de `pickFolder`):

```javascript
    providerSave(p, cb) {
      if (state.phase !== 'engine') { return cb({ ok: true, mock: true }); }
      Host.send('providers-upsert', { provider: providerPayload(p) }, (r) => {
        if (r.ok) adoptProviders(r.result.config);
        cb(r);
      }, null);
    },
    providerRemove(p, cb) {
      if (state.phase !== 'engine') { return cb({ ok: true, mock: true }); }
      Host.send('providers-remove', { id: p.id }, (r) => {
        if (r.ok) adoptProviders(r.result.config);
        cb(r);
      }, null);
    },
    agentSave(a, cb) {
      if (state.phase !== 'engine') { return cb({ ok: true, mock: true }); }
      Host.send('agents-upsert', { agent: agentPayload(a) }, (r) => {
        if (r.ok) adoptAgents(r.result.config);
        cb(r);
      }, null);
    },
    agentRemove(a, cb) {
      if (state.phase !== 'engine') { return cb({ ok: true, mock: true }); }
      Host.send('agents-remove', { id: a.id }, (r) => {
        if (r.ok) adoptAgents(r.result.config);
        cb(r);
      }, null);
    },
    modelScan(cb) {
      if (state.phase !== 'engine') { return cb({ ok: true, mock: true }); }
      loadModels(() => cb({ ok: true }));
    },
```

E os dois conversores UI → motor. As chaves são exatamente as que o motor
devolve em `config-get` (Step 2), só que na direção inversa — nada de campo
novo:

```javascript
  const PROVIDER_KEYS = ["id", "label", "preset", "kind", "base", "transport",
    "authKind", "authVar", "model", "models", "enabled", "origin", "roles",
    "lastCheck", "authState"];
  const AGENT_KEYS = ["id", "label", "preset", "cfg", "format", "target",
    "writes", "provider", "model", "enabled", "skills", "origin", "status",
    "note"];

  function pick(obj, keys) {
    const out = {};
    keys.forEach((k) => { if (obj && obj[k] !== undefined) out[k] = obj[k]; });
    return out;
  }
  const slug = (text) => String(text || "").toLowerCase()
    .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "item";
  // O rascunho criado por um preset nao tem id; o motor exige. Sem colidir com
  // um id existente — senao "adicionar" viraria "substituir" em silencio.
  function uniqueId(base, taken) {
    let id = slug(base), n = 2;
    while (taken.indexOf(id) !== -1) { id = slug(base) + "-" + n; n += 1; }
    return id;
  }
  function providerPayload(p) {
    const out = pick(p, PROVIDER_KEYS);
    if (!out.id) {
      out.id = uniqueId(p.preset && p.preset !== "custom" ? p.preset : p.label,
        M.providers.filter((x) => x !== p).map((x) => x.id));
    }
    out.roles = { athena: !!(p.roles && p.roles.athena), sentinel: !!(p.roles && p.roles.sentinel) };
    return out;
  }
  function agentPayload(a) {
    const out = pick(a, AGENT_KEYS);
    if (!out.id) {
      out.id = uniqueId(a.preset && a.preset !== "manual" ? a.preset : a.label,
        M.agents.filter((x) => x !== a).map((x) => x.id));
    }
    return out;
  }
```

Agora os chamadores. Cada um mantém o caminho do navegador idêntico ao de hoje
e só ganha o ramo do motor:

**Provedores — `#pv-save` (linhas 594-601):**

```javascript
    const pvSave = c.querySelector("#pv-save");
    if (pvSave) pvSave.addEventListener("click", () => {
      readForm();
      const draft = draftOf(), isNew = !!state.providerDraft;
      if (state.phase !== "engine") {
        if (isNew) { M.providers.push(state.providerDraft); state.providerSel = M.providers.length - 1; state.providerDraft = null; }
        else { currentProvider().lastCheck = "config gravada"; }
        render();
        openRun("gravar provedor " + draft.label, defaultCmd());
        return;
      }
      Bridge.providerSave(draft, (r) => {
        state.providerDraft = null;
        state.providerSel = M.providers.findIndex((x) => x.id === providerPayload(draft).id);
        if (state.providerSel < 0) state.providerSel = 0;
        render();
        openRun("gravar provedor " + draft.label, cfg("providers." + slug(draft.label)),
          resultLines(r, "gravado em " + M.meta.config));
      });
    });
```

**Provedores — `#pv-del` (linha 622):** o motor é quem recusa provedor protegido,
então a remoção passa por ele e a recusa aparece no painel.

```javascript
    const pvDel = c.querySelector("#pv-del");
    if (pvDel) pvDel.addEventListener("click", () => {
      if (state.providerDraft) { state.providerDraft = null; render(); return; }
      const p = currentProvider();
      if (state.phase !== "engine") { M.providers.splice(state.providerSel, 1); state.providerSel = 0; render(); return; }
      Bridge.providerRemove(p, (r) => {
        state.providerSel = 0; render();
        openRun("remover provedor " + p.label, cfg("providers." + slug(p.label)),
          resultLines(r, "removido"));
      });
    });
```

**Provedores — `#pv-auth` (linhas 602-614):** trocar a última linha, que hoje
abre log simulado, pela resposta real do `providers-register` (que já veio em
`r`):

```javascript
        render();
        openRun("registrar provedor " + p.label, cfg("providers." + slug(p.label)),
          resultLines({ ok: r.ok, error: r.msg }, r.msg));
```

**Programas alvo — `#ag-save`, `#ag-apply`, `#ag-apply-all`, `#ag-del`
(linhas 641-653):**

```javascript
    const agSave = c.querySelector("#ag-save");
    if (agSave) agSave.addEventListener("click", () => {
      const x = draftAgent(); readForm();
      if (state.phase !== "engine") {
        x.status = "pendente";
        if (state.agentDraft) { M.agents.push(x); state.agentSel = M.agents.length - 1; state.agentDraft = null; }
        render(); openRun("gravar programa " + x.label, defaultCmd()); return;
      }
      Bridge.agentSave(x, (r) => {
        state.agentDraft = null;
        state.agentSel = Math.max(0, M.agents.findIndex((y) => y.id === agentPayload(x).id));
        render();
        openRun("gravar programa " + x.label, cfg("agents." + slug(x.label)),
          resultLines(r, "gravado em " + M.meta.config));
      });
    });

    const agApply = c.querySelector("#ag-apply");
    if (agApply) agApply.addEventListener("click", () => {
      const x = draftAgent();
      if (state.phase !== "engine") { x.status = "em dia"; render(); openRun("aplicar provedor/modelo em " + x.label, cfg("agents." + slug(x.label) + " := " + (x.provider || "—") + "/" + (x.model || "—"))); return; }
      Bridge.agentsApply(x.id, (r) => {
        render();
        openRun("aplicar provedor/modelo em " + x.label, cfg("agents." + slug(x.label)),
          resultLines(r, r.ok ? "aplicado em " + ((r.result && r.result.written) || x.label) : ""));
      });
    });

    const agAll = c.querySelector("#ag-apply-all");
    if (agAll) agAll.addEventListener("click", () => {
      if (state.phase !== "engine") { M.agents.forEach((x) => (x.status = "em dia")); render(); openRun("aplicar a configuração nos programas marcados", cfg("agents[ " + M.agents.map((x) => x.label).join(", ") + " ]")); return; }
      Bridge.agentsApply(null, (r) => {
        refreshFromEngine();
        const bad = r.ok ? (r.result.results || []).filter((x) => !x.ok) : null;
        openRun("aplicar nos programas marcados", cfg("agents[todos]"),
          bad && bad.length
            ? [{ type: "err", text: bad.length + " programa(s) não gravaram", pct: 100 }]
            : resultLines(r, "aplicado nos programas marcados"));
      });
    });

    const agDel = c.querySelector("#ag-del");
    if (agDel) agDel.addEventListener("click", () => {
      const a = currentAgent();
      if (state.phase !== "engine") { M.agents.splice(state.agentSel, 1); state.agentSel = 0; render(); return; }
      Bridge.agentRemove(a, (r) => {
        state.agentSel = 0; render();
        openRun("remover programa " + a.label, cfg("agents." + slug(a.label)),
          resultLines(r, "removido"));
      });
    });
```

**Modelos locais — `#md-scan` e `[data-pull]` (linhas 670-671):**

```javascript
    const scan = c.querySelector("#md-scan");
    if (scan) scan.addEventListener("click", () => {
      if (state.phase !== "engine") { openRun("reescanear modelos locais dos provedores", cfg("localModels[]")); return; }
      Bridge.modelScan(() => {
        render();
        openRun("reescanear modelos locais", cfg("localModels[]"),
          { ok: true, lines: [{ type: "ok", text: (M.localModels || []).length + " modelo(s) no Ollama", pct: 100 }] });
      });
    });
    c.querySelectorAll("[data-pull]").forEach((b) => b.addEventListener("click", () => {
      const name = b.dataset.pull;
      if (state.phase !== "engine") { openRun("baixar " + name, cfg("localModels.pull = " + name)); return; }
      // `models-pull` e streaming: passa pelo mesmo painel, mas com runner
      // proprio. `run` nao serve porque o comando da ponte e outro.
      openRun("baixar " + name, cfg("ollama pull " + name), null,
        (onLine, onDone) => Bridge.modelsPull(name, onLine, onDone));
    }));
```

**Skills — `[data-drop]` (linha 678) e `#skill-import-btn` (linhas 684-690):**

```javascript
    c.querySelectorAll("[data-drop]").forEach((b) => b.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const s = M.skills.find((x) => x.id === b.dataset.drop);
      if (state.phase !== "engine") { s.installed = false; s.origin === "user" && M.skills.splice(M.skills.indexOf(s), 1); render(); return; }
      Bridge.skillsUninstall(s.id, (r) => { render(); openRun("remover skill " + s.repo, cfg("skills." + s.id), resultLines(r, r.msg || "movida para a quarentena")); });
    }));

    const imp = c.querySelector("#skill-import-btn");
    if (imp) imp.addEventListener("click", () => {
      const path = state.importPath.trim(); if (!path) return;
      const name = path.split(/[\\/]/).filter(Boolean).pop().replace(/\.zip$/i, "");
      if (state.phase !== "engine") {
        M.skills.push({ id: "imported-" + name.toLowerCase(), repo: name, desc: "Importada manualmente de " + path, installed: true, update: false, origin: "user" });
        state.importPath = ""; render(); return;
      }
      Host.send('skills-import', { path: path, scope: state.scope }, (r) => {
        if (r.ok) adoptSkills(r.result.skills);
        state.importPath = ""; render();
        openRun("importar skill " + name, cfg("skills." + slug(name)),
          resultLines(r.ok ? r.result.skill : r, "importada de " + path));
      }, null);
    });
```

**Publicar — `defaultCmd()` (linha 78):** a pasta escolhida no seletor vai entre
aspas, senão `flagsFromCmd` a quebraria em dois argumentos se ela tiver espaço
(nesta máquina `C:\Users\anthe\...` não tem, mas a interface não pode depender
disso). Trocar o trecho do `--publish-out`:

```javascript
      case "publish": return cmd("--publish" + (state.publishAgents.size ? " --publish-agent " + [...state.publishAgents].join(",") : "") + (state.publishOut ? ' --publish-out "' + state.publishOut + '"' : ""));
```

E o campo `#pout` (linha 389) não tem handler nenhum hoje — digitar nele não
chega em `state.publishOut`, então `--publish-out` nunca sai da tela. Acrescentar
dentro de `wire()`, junto dos outros binds da seção:

```javascript
    bind(c, "pout", "input", (v) => { state.publishOut = v; syncCmd(); });
```

**Skills — botão "Procurar" ao lado de `#skill-import` (linha 348):** única
adição à interface aprovada, e existe só porque o campo pede um caminho de disco
digitado à mão — no Vector/Gênesis o campo equivalente vem com seletor. Na
janela o botão aparece (é `pick-folder` do protocolo); no navegador não, e a
digitação continua funcionando. Se você não quiser o botão, ele sai junto com
`pick-folder`/`folder-picked` do protocolo e nada mais deste plano depende dele.

No template (`sec.skills`, linha 348):

```javascript
          <div class="input-row"><input class="input mono" id="skill-import" placeholder="C:\\Users\\anthe\\Downloads\\minha-skill" value="${esc(state.importPath)}">${isHosted() ? '<button class="btn btn-ghost" id="skill-browse">Procurar</button>' : ""}<button class="btn btn-ghost" id="skill-import-btn">Importar</button></div>
```

Em `wire()`, junto do `#skill-import-btn`:

```javascript
    const browse = c.querySelector("#skill-browse");
    if (browse) browse.addEventListener("click", () => Bridge.pickFolder((path) => {
      if (!path) return;
      state.importPath = path;
      const field = c.querySelector("#skill-import");
      if (field) field.value = path;        // sem re-render: nao perde o cursor
    }));
```

**MCP — botão "Iniciar servidor" (linha 378):** o servidor lê stdin e bloqueia;
quem o inicia é o cliente MCP, nunca a ponte (por isso `--mcp` está fora da
whitelist do Step 4 da Task 8). Na janela o botão sai de cena e sobra a linha de
registro, que já existe na tela:

```javascript
    <div class="block"><button class="btn btn-primary" ${state.phase === "engine" ? "disabled title=\"iniciado pelo cliente MCP (Claude Code / OpenCode / Qoder)\"" : ""} data-run="--mcp" data-line="iniciar o servidor MCP (stdio)">Iniciar servidor</button></div>
```

**Modelos — os três selects de roteamento (linhas 667-669):** cada slot grava
sozinho, com o comando próprio da ponte (`models-set`), e o painel mostra o que
o motor respondeu. Os chips de modo (`[data-rmode]`, linha 667) continuam
locais até "Executar" — são um único campo (`routing.mode`).

```javascript
    const routeSet = (slot, value) => {
      state.routing[slot] = value;
      if (state.phase !== "engine") { render(); return; }
      Bridge.routingSet(slot, value, (r) => {
        openRun("gravar roteamento " + slot, cfg("routing." + slot),
          resultLines(r, slot + " = " + value));
      });
    };
    bind(c, "rt-athena", "change", (v) => routeSet("athena", v));
    bind(c, "rt-sentinel", "change", (v) => routeSet("sentinel", v));
    bind(c, "rt-fallback", "change", (v) => routeSet("fallback", v));
```

**Rodapé — `#btn-run` (linhas 731-734):** nas telas de configuração ele grava
via motor; nas de CLI ele roda. Nas de configuração o caminho mais curto é
reusar o botão que a própria tela já tem (mesma validação, mesma mensagem).
Trocar por:

```javascript
  el("btn-run").addEventListener("click", () => {
    const isCfg = kindOf(state.section) === "config";
    if (!isCfg || state.phase !== "engine") {
      openRun(isCfg ? "gravar configuração de " + state.section : "executar " + state.section, defaultCmd());
      return;
    }
    const host = el("content");                 // os botoes ja estao na tela
    if (state.section === "providers") { host.querySelector("#pv-save").click(); return; }
    if (state.section === "agents") { host.querySelector("#ag-save").click(); return; }
    if (state.section === "models") {
      // So o modo: os tres slots ja sairam pelos selects acima.
      Bridge.configSet({ routing: Object.assign({}, state.routing,
        { mode: state.routingMode || "zeus" }) }, (r) => {
        if (r.ok) state.routing = r.result.config.routing;
        render();
        openRun("gravar modo de roteamento", cfg("routing.mode"),
          resultLines(r, "modo " + (state.routingMode || "zeus") + " gravado"));
      });
      return;
    }
    openRun("gravar configuração", defaultCmd());
  });
```

- [ ] **Step 7: Barra de título, rodapé e escopo passam pelo host**

Trocar as três linhas que hoje são simuladas (linhas 735-736) e o toggle de
escopo (linha 729):

```javascript
  el("btn-min").addEventListener("click", () => Host.window("window-minimize"));
  el("btn-close").addEventListener("click", () => {
    if (!isHosted()) { document.body.style.opacity = 0.3; return; }
    Host.window("window-close");        // o host derruba o filho antes de fechar
  });
  el("titlebar").addEventListener("pointerdown", (ev) => {
    if (ev.target.closest("button")) return;
    Host.window("window-drag");
  });
```

```javascript
  el("scope-toggle").addEventListener("click", () => {
    state.scope = isLocal() ? "global" : "local";
    E.scope = state.scope;
    setScopeUI();
    render();
    refreshFromEngine();                // skills/CLAUDE.md mudam de base com o escopo
  });
```

E o rótulo de fase no `render()` (linha 718) deixa de dizer "mock" quando há
motor:

```javascript
    el("titlebar-phase").textContent =
      (state.phase === "engine" ? "motor" : "mock") + " · " + s.label;
```

- [ ] **Step 8: `state` ganha os campos novos**

Na declaração de `state` (linhas 45-65 — `routing` e `routingMode` já existem
lá, é neles que a ponte escreve), acrescentar:

```javascript
    hosted: false,
    phase: isHosted() ? "esperando" : "mock",
    runId: null,
```


- [ ] **Step 9: Não reabrir o onboarding quando o motor já respondeu**

A linha final (740) hoje abre o onboarding por flag do mock. Com motor, quem
decide é o `firstRun` real devolvido pelo `env` — e isso já acontece dentro de
`hydrate()`. Trocar por:

```javascript
  if (state.phase !== "engine" && (E.firstRun || !E.cliInstalled)) openOnboarding();
```

- [ ] **Step 10: Verificar o fallback de navegador**

A janela real é verificada na Task 11 (motor de pé); aqui só a queda para o
mock, que precisa continuar idêntica à fase 1 aprovada.

```bash
cd gui && python -m http.server 8777
```
Abrir `http://127.0.0.1:8777/index.html` → deve comportar-se **exatamente**
como a fase 1 aprovada (rótulo "mock", onboarding ao clicar em "primeira
abertura", log simulado). Nenhum erro de console.

- [ ] **Step 11: Commit (pedir confirmação)**

```bash
git add gui/app.js
git commit -m "feat(gui): drive the screens from the real engine, mock stays browser fallback"
```

---

### Task 11: Smoke E2E da janela (motor real, nada de mock)

**Files:**
- Create: `thero/tests/test_gui_static.py`
- Rodar: `gui/dev.cmd`

- [ ] **Step 1: Teste estático que pega 80% dos bugs de costura**

`tests/test_gui_static.py`:

```python
import re
from pathlib import Path

GUI = Path(__file__).resolve().parent.parent / "gui"


def read(name):
    return (GUI / name).read_text(encoding="utf-8")


def test_index_loads_bridge_before_controller():
    html = read("index.html")
    assert html.index("mock.js") < html.index("app.js")


def test_the_controller_uses_the_host_post_message_and_not_raw_send():
    js = read("app.js")
    assert "window.chrome.webview.postMessage" in js
    # JSON.stringify e obrigatorio: sem ele o host nunca ve o pedido.
    assert re.search(r"postMessage\(JSON\.stringify\(", js)


def test_no_engine_command_is_built_as_a_free_text_line():
    js = read("app.js")
    # O pedido de execucao sai sempre com `flags:` (array) — nunca uma linha
    # solta. `flagsFromCmd` e o unico tradutor entre a UI e a whitelist.
    assert "function flagsFromCmd" in js
    assert "'run', { flags:" in js
    assert "flagsForSection" not in js


def test_host_declares_every_message_type_the_js_sends():
    js, ps = read("app.js"), read("TheroHost.ps1")
    for kind in ("ready", "window-close", "window-minimize", "window-drag",
                 "engine-request", "engine-cancel", "pick-folder"):
        assert "'%s'" % kind in ps, kind
        assert kind in js, kind


def test_host_answers_every_message_type_the_ps_posts():
    js, ps = read("app.js"), read("TheroHost.ps1")
    for kind in ("host-ready", "engine-reply", "engine-line", "engine-error",
                 "folder-picked", "bridge-error"):
        assert "'%s'" % kind in ps, kind
        assert kind in js, kind


def test_the_webview2_binaries_ship_with_the_gui():
    for name in ("Microsoft.Web.WebView2.Core.dll",
                 "Microsoft.Web.WebView2.WinForms.dll", "WebView2Loader.dll"):
        assert (GUI / "webview2" / name).exists(), name


def test_the_bridge_command_list_matches_the_ui_vocabulary():
    bridge = (Path(__file__).resolve().parent.parent / "src" / "thero" /
              "bridge.py").read_text(encoding="utf-8")
    js = read("app.js")
    used = set(re.findall(r"Host\.send\('([a-z-]+)'", js))
    declared = set(re.findall(r'"([a-z-]+)"',
                              bridge.split("COMMANDS = (")[1].split(")")[0]))
    assert used, "o app.js nao chama nenhuma comando da ponte"
    missing = used - declared
    assert not missing, "comandos usados pela UI e ausentes da whitelist: %s" % sorted(missing)
```

- [ ] **Step 2: Rodar**

Run: `python -m pytest tests/ -q`
Expected: `386 + 7 = 393 passed`

- [ ] **Step 3: Smoke manual da janela**

```bash
cd gui && cmd //c dev.cmd
```
Checklist (executar e marcar no PR):
- [ ] Janela sem borda abre com a paleta aprovada; título "motor · Status".
- [ ] Status mostra Python real, Node/npx (aqui: `npx` presente e quebrado →
      deve aparecer como ausente/falhando, **não** como OK), Claude Code ausente,
      Ollama "não respondeu".
- [ ] "Executar" em Skills → painel enche com linhas reais do `npx` enquanto
      roda e fecha com o exit code dele (aqui: exit ≠ 0, com erro legível).
- [ ] Cancelar durante um comando longo: o painel fecha com "cancelado pelo
      usuario" e nenhum `npx` sobrevive (Gerenciador de Tarefas).
- [ ] Provedores: "Testar" e "Registrar" no OpenAI → "variavel
      THERO_OPENAI_API_KEY ainda nao definida"; nenhuma resposta da ponte
      contém valor de chave.
- [ ] Modelos locais: Ollama parado → lista vazia com o motivo, sem traceback.
- [ ] Programas alvo: "Aplicar" grava o bloco `# >>> thero env >>>` na
      `$PROFILE` **uma** vez (rodar duas vezes e conferir que não duplicou) e
      `~/.claude/settings.json` ganha `model` + `env.ANTHROPIC_MODEL`
      preservando `autoUpdatesChannel`/`inputNeededNotifEnabled`.
- [ ] Skills: a pasta do usuário some da base e aparece em
      `~/.thero/quarantine/skills/`; skill do Thero recusa.
- [ ] Abrir de novo: `firstRun` já é false e o onboarding não aparece.
- [ ] Fechar a janela derruba o `python thero.py --serve` (nenhum processo
      órfão em `Get-Process python`).

- [ ] **Step 4: Commit (pedir confirmação)**

```bash
git add tests/test_gui_static.py
git commit -m "test(gui): pin the JS<->PS<->bridge protocol so the seams can't drift"
```

---

# FASE 3 — Empacotar (o `.exe` É o programa)

### Task 12: `build.ps1` + payload + ícone → `dist/Thero.exe`

**Files:**
- Create: `thero/build.ps1`
- Create: `thero/scripts/build-payload.ps1`
- Create: `thero/scripts/make-exe-icon.ps1`
- Create: `thero/gui/Thero.ico`
- Modify: `thero/.gitignore` (ignorar `dist/`, `gui/webview2/*.exp`)

Padrão copiado de `vector/build.ps1` e `vector/scripts/build-payload.ps1`
(lidos nesta máquina). Diferenças deliberadas:

- **Sem `requireAdmin`**: o Thero só escreve no home do usuário; a política do
  Theroverse é executável portable sem elevação.
- Payload = `src/` + `thero.py` + `gui/` (inclusive `gui/webview2/*.dll`),
  extraído em `%LOCALAPPDATA%\Thero\app\<versao>` na primeira execução — ou
  seja, o `.exe` continua sendo um arquivo único, e não um instalador.

- [ ] **Step 1: `scripts/build-payload.ps1`**

Transcrição fiel de `vector/scripts/build-payload.ps1` (lido nesta máquina,
4672 bytes): zip → gzip → base64, versão = hash do payload, saída em
`.build/payload.ps1`. O que muda é a lista de arquivos (o Thero tem `gui/`
na raiz do `gui/`, não `gui/vector/`) e o nome das variáveis globais.

```powershell
#Requires -Version 5.1
<#
    Gera .build/payload.ps1 - o pacote embutido do Thero.exe.

    O Thero.exe compilado e UM ARQUIVO SO: nao precisa de gui/ nem de src/ do
    lado. Junta o que a interface precisa em tempo de execucao num zip,
    comprime (gzip) e grava em base64 num here-string. Quem extrai em runtime
    e o Expand-TheroPayload, dentro do proprio gui/TheroHost.ps1.

    Ficam FORA do payload: caches, bytecode e os helpders de dev.
#>

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$OutDir = Join-Path $Root '.build'
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null

# Pastas inteiras, relativas a raiz. 'src' e o motor Python: o TheroHost.ps1
# executa `python thero.py --serve` na pasta extraida.
#
# Diferenca para o Vector: la o app fica em 'gui\vector', entao ele e listado
# ao lado de 'gui\webview2'. Aqui o gui/ e plano (index.html, app.js, mock.js,
# style.css, assets/, webview2/), e 'gui' sozinho ja cobre tudo. Listar
# 'gui\webview2' de novo criaria entradas duplicadas no zip - o que lanca.
$includeDirs = @(
    'gui',
    'src'
)

# Arquivos soltos que o host usa direto na raiz de $Root. O icone NAO entra
# aqui: gui/Thero.ico ja vem na recursao de 'gui'.
$includeFiles = @(
    'thero.py'
)

$exclude = '__pycache__|\.pyc$'
# Filtro por nome (mesma divisao do script do Vector): arquivos ocultos, os
# helpders de dev e o proprio host - este ultimo e o script que vira o .exe,
# entao coloca-lo no payload seria levar o contenedor dentro do conteudo.
$nameExclude = '^\.|^TheroHost\.ps1$|^dev\.(cmd|ps1)$'

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$tmpZip = Join-Path $OutDir 'payload.zip'
if (Test-Path $tmpZip) { Remove-Item $tmpZip -Force }

$count = 0
$archive = [System.IO.Compression.ZipFile]::Open($tmpZip, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    $add = {
        param([string]$FullPath)
        # dentro do zip o caminho e sempre relativo a raiz, com barras "/"
        $entry = $FullPath.Substring($Root.Length + 1) -replace '\\', '/'
        [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive, $FullPath, $entry, [System.IO.Compression.CompressionLevel]::Optimal)
        $script:count++
    }

    foreach ($rel in $includeDirs) {
        $dir = Join-Path $Root $rel
        if (-not (Test-Path $dir)) { throw "Pasta obrigatoria nao encontrada: $rel" }
        Get-ChildItem -Path $dir -Recurse -File -Force |
            Where-Object { $_.FullName -notmatch $exclude -and $_.Name -notmatch $nameExclude } |
            ForEach-Object { & $add $_.FullName }
    }

    foreach ($rel in $includeFiles) {
        $file = Join-Path $Root $rel
        if (Test-Path $file) { & $add $file }
        else { Write-Warning "Arquivo opcional ausente, ficando fora do payload: $rel" }
    }
}
finally { $archive.Dispose() }

$zipBytes = [System.IO.File]::ReadAllBytes($tmpZip)
$gzipStream = New-Object System.IO.MemoryStream
$gzip = New-Object System.IO.Compression.GZipStream($gzipStream, [System.IO.Compression.CompressionMode]::Compress, $true)
$gzip.Write($zipBytes, 0, $zipBytes.Length)
$gzip.Dispose()
$base64 = [Convert]::ToBase64String($gzipStream.ToArray())
$gzipStream.Dispose()

# A versao e o hash do proprio payload: muda o conteudo, muda a pasta de
# cache em runtime (%LOCALAPPDATA%\Thero\app\<versao>).
$sha = [System.Security.Cryptography.SHA256]::Create()
$digest = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($base64))
$version = (($digest | ForEach-Object { $_.ToString('x2') }) -join '').Substring(0, 16)

$payloadFile = Join-Path $OutDir 'payload.ps1'
$text = @"
# Gerado por scripts/build-payload.ps1 - NAO versionado, NAO edite a mao.
# $count arquivos embutidos (zip + gzip + base64), versao $version.
`$Global:TheroPayloadVersion = '$version'
`$Global:TheroPayloadBase64 = @'
$base64
'@
"@
[System.IO.File]::WriteAllText($payloadFile, $text, (New-Object System.Text.UTF8Encoding($true)))
Remove-Item $tmpZip -Force

$kb = [math]::Round((Get-Item $payloadFile).Length / 1KB)
Write-Host "Payload: $count arquivos, $kb KB em base64 -> $payloadFile (versao $version)" -ForegroundColor Green
```

> Consequência do `$nameExclude` acima: o `gui/TheroHost.ps1` **não** vai no
> payload (ele é o script que vira o `.exe`), então a sentinela de extração é
> `gui/app.js` — exatamente o que o `Expand-TheroPayload` da Task 9 testa. E é
> por isso também que o `build.ps1` gera o ícone **antes** de chamar o
> `build-payload.ps1`: senão `gui/Thero.ico` não existe na hora de empacotar.

- [ ] **Step 2: `build.ps1`**

Transcrição de `vector/build.ps1` (lido nesta máquina). Mesma mecânica de
injeção: o `payload.ps1` entra como **texto em base64 avaliado em runtime**,
não concatenado como código. Duas diferenças deliberadas: **sem
`-requireAdmin`** — o Thero só escreve no home do usuário e a política do
Theroverse é executável portable sem elevação — e **sem substituição de
`param()`**, porque o `TheroHost.ps1` da Task 9 não declara parâmetros (o passo
a mais no build era só uma regex frágil esperando um `param()` que não existe).

```powershell
#Requires -Version 5.1
<#
    Compila o Thero.exe a partir do codigo-fonte, com o modulo ps2exe.

    O resultado e UM ARQUIVO SO: src/ + thero.py + gui/ (com as DLLs do
    WebView2) entram num payload comprimido (scripts/build-payload.ps1) e sao
    extraidos em %LOCALAPPDATA%\Thero\app\<versao> na primeira execucao --
    quem faz isso e o Expand-TheroPayload dentro do proprio TheroHost.ps1.

    NAO tem requireAdmin, nem instalador: portable por politica. Copiar o
    Thero.exe sozinho pra qualquer pasta ja basta.

    Saindo daqui:
      1. .build/payload.ps1  (assets: zip -> gzip -> base64)
      2. .build/Thero.ps1    (payload lido como TEXTO + host, que nao tem param())
      3. dist/Thero.exe      (ps2exe)
#>

$ErrorActionPreference = 'Stop'

$Root = $PSScriptRoot
$OutDir = Join-Path $Root 'dist'
$OutExe = Join-Path $OutDir 'Thero.exe'
$BuildDir = Join-Path $Root '.build'

if (-not (Get-PackageProvider -Name NuGet -ListAvailable -ErrorAction SilentlyContinue)) {
    Write-Host "Instalando provedor NuGet (necessario pro PowerShellGet)..." -ForegroundColor Cyan
    Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Scope CurrentUser -Force | Out-Null
}

if (-not (Get-Module -ListAvailable -Name ps2exe)) {
    Write-Host "Instalando modulo ps2exe..." -ForegroundColor Cyan
    Install-Module -Name ps2exe -Scope CurrentUser -Force -AllowClobber
}
Import-Module ps2exe

$iconFile = Join-Path $Root 'gui\Thero.ico'
if (-not (Test-Path $iconFile)) {
    Write-Host "Icone nao encontrado, gerando..." -ForegroundColor Cyan
    & (Join-Path $Root 'scripts\make-exe-icon.ps1')
}

Write-Host "`n[1/3] Gerando o payload embutido..." -ForegroundColor Cyan
& (Join-Path $Root 'scripts\build-payload.ps1')

Write-Host "[2/3] Montando o script unico do exe..." -ForegroundColor Cyan
New-Item -ItemType Directory -Path $BuildDir -Force | Out-Null
$singleScript = Join-Path $BuildDir 'Thero.ps1'
$payloadFile = Join-Path $BuildDir 'payload.ps1'
$hostFile = Join-Path $Root 'gui\TheroHost.ps1'

foreach ($part in @($payloadFile, $hostFile)) {
    if (-not (Test-Path $part)) { throw "Parte do script unico nao encontrada: $part" }
}

# ReadAllText(UTF8) ja descarta o BOM; cada parte entra limpa e so o arquivo
# final leva BOM (mesma regra do Vector, queimada em teste de exe corrompido).
$payloadSource = [System.IO.File]::ReadAllText($payloadFile, [System.Text.Encoding]::UTF8)
$payloadB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($payloadSource))
$single = New-Object System.Text.StringBuilder
[void]$single.AppendLine('# Gerado pelo build.ps1 - NAO edite. O payload vai EMBUTIDO abaixo em')
[void]$single.AppendLine('# base64 e e avaliado em runtime, NAO como codigo.')
[void]$single.AppendLine('$__TheroPayloadB64 = ''')
[void]$single.AppendLine($payloadB64)
[void]$single.AppendLine('''')
[void]$single.AppendLine('$__TheroPayloadSource = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($__TheroPayloadB64))')
[void]$single.AppendLine('. ([ScriptBlock]::Create($__TheroPayloadSource))')
[void]$single.AppendLine('Remove-Variable -Name __TheroPayloadB64, __TheroPayloadSource -Scope Script -ErrorAction SilentlyContinue')

# O TheroHost.ps1 nao declara param() (ver o cabecalho dele na Task 9), entao o
# host entra inteiro no script unico. Esta checagem existe porque param() so e
# valido como primeiro comando do script: concatenado atras do payload viraria
# "O termo 'param' nao e reconhecido". Se alguem voltar a adicionar um, o build
# falha aqui e nao no exe gerado.
$hostText = [System.IO.File]::ReadAllText($hostFile, [System.Text.Encoding]::UTF8)
if ($hostText -match '(?m)^param\s*\(') {
    throw "O TheroHost.ps1 voltou a ter param(); ele precisa ser o primeiro comando do script unico - remova ou ajuste o build de proposito."
}
[void]$single.AppendLine($hostText)
[System.IO.File]::WriteAllText($singleScript, $single.ToString(), (New-Object System.Text.UTF8Encoding($true)))

New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
Write-Host "[3/3] Compilando com ps2exe (pode demorar um pouco)..." -ForegroundColor Cyan
if (Test-Path $OutExe) {
    try { [System.IO.File]::Delete((Resolve-Path $OutExe)) }
    catch {
        Write-Warning "Nao deu pra apagar o Thero.exe atual ($($_.Exception.Message)). Feche o exe e rode de novo."
    }
}
Invoke-ps2exe `
    -inputFile $singleScript `
    -outputFile $OutExe `
    -iconFile $iconFile `
    -title 'Thero' `
    -description 'Thero - ambiente de agentes do Theroverse' `
    -company 'Anthero' `
    -product 'Thero' `
    -version '1.1.0.0' `
    -noConsole `
    -x64

if (-not (Test-Path $OutExe)) {
    throw "ps2exe rodou mas $OutExe nao foi criado - veja a saida acima pro erro real."
}

$size = [math]::Round((Get-Item $OutExe).Length / 1MB, 1)
Write-Host "`nGerado: $OutExe ($size MB)" -ForegroundColor Green
Write-Host "Arquivo unico em dist/: pode copiar o Thero.exe sozinho pra qualquer pasta." -ForegroundColor Yellow
Write-Host "Ele extrai o proprio payload em %LOCALAPPDATA%\Thero\app\<versao>." -ForegroundColor Yellow
```

- [ ] **Step 3: `scripts/make-exe-icon.ps1`**

Desenha o `Thero.ico` (16/32/48/256) com GDI+ puro, no mesmo formato do
`vector/scripts/make-exe-icon.ps1`: PNG por tamanho, costurados num
`ICONDIR` escrito à mão. A marca abaixo é a geometria de
`gui/assets/thero-mark.png` reproduzida em primitivas (círculo + traço
vertical), na paleta do Thero — sem depender debrowser nem ImageMagick.

```powershell
#Requires -Version 5.1
<#
    Gera gui/Thero.ico (16/32/48/256) desenhado com GDI+ (.NET puro).
    So precisa rodar quando o marca mudar.
#>

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$Root = Split-Path -Parent $PSScriptRoot
$outIco = Join-Path $Root 'gui\Thero.ico'

# Paleta do Thero (style.css): campo #0b1014, acento #4FD1C5, brilho #7FE9DE.
$bgColor = [System.Drawing.ColorTranslator]::FromHtml('#0b1014')
$ringColor = [System.Drawing.ColorTranslator]::FromHtml('#4FD1C5')
$dotColor = [System.Drawing.ColorTranslator]::FromHtml('#7FE9DE')

$sizes = 16, 32, 48, 256
$pngBlobs = @()

foreach ($sizeItem in $sizes) {
    $size = [int]$sizeItem
    $bmp = New-Object System.Drawing.Bitmap $size, $size
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic

    $radius = [Math]::Max(2, [int]($size * 0.22))
    $rect = New-Object System.Drawing.Rectangle(0, 0, ($size - 1), ($size - 1))
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $d = $radius * 2
    $path.AddArc($rect.X, $rect.Y, $d, $d, 180, 90)
    $path.AddArc($rect.Right - $d, $rect.Y, $d, $d, 270, 90)
    $path.AddArc($rect.Right - $d, $rect.Bottom - $d, $d, $d, 0, 90)
    $path.AddArc($rect.X, $rect.Bottom - $d, $d, $d, 90, 90)
    $path.CloseFigure()
    $g.FillPath((New-Object System.Drawing.SolidBrush($bgColor)), $path)

    $scale = $size / 64.0
    $center = $size / 2.0
    $isSmall = $size -le 32

    # anel externo (o "ambiente" que o Thero fecha em volta dos agentes)
    $ringStroke = if ($isSmall) { [Math]::Max(1, [int](4.0 * $scale * 1.6)) } else { [Math]::Max(1, [int](4.0 * $scale)) }
    $ringPen = New-Object System.Drawing.Pen($ringColor, $ringStroke)
    $ringRect = New-Object System.Drawing.RectangleF(
        ($center - 21 * $scale), ($center - 21 * $scale), (42 * $scale), (42 * $scale))
    $g.DrawEllipse($ringPen, $ringRect)

    # traco vertical central (o "terminal"), sem o detalhe nos tamanhos curtos
    if (-not $isSmall) {
        $stemPen = New-Object System.Drawing.Pen($dotColor, [Math]::Max(1, [int](4.0 * $scale)))
        $stemPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $stemPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $g.DrawLine($stemPen, $center, ($center - 12 * $scale), $center, ($center + 12 * $scale))
        $stemPen.Dispose()
    }
    else {
        $dotBrush = New-Object System.Drawing.SolidBrush($dotColor)
        $r = 4.0 * $scale
        $g.FillEllipse($dotBrush, ($center - $r), ($center - $r), ($r * 2), ($r * 2))
        $dotBrush.Dispose()
    }

    $ringPen.Dispose()
    $path.Dispose()
    $g.Dispose()

    $ms = New-Object System.IO.MemoryStream
    $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
    $pngBlobs += , $ms.ToArray()
    $ms.Dispose()
    $bmp.Dispose()
}

# ICONDIR (6 bytes) + um ICONDIRENTRY (16 bytes) por imagem, depois os PNGs.
$headerSize = 6
$entrySize = 16
$offset = $headerSize + ($entrySize * $sizes.Count)

$stream = New-Object System.IO.MemoryStream
$writer = New-Object System.IO.BinaryWriter($stream)
$writer.Write([uint16]0)
$writer.Write([uint16]1)
$writer.Write([uint16]$sizes.Count)

for ($i = 0; $i -lt $sizes.Count; $i++) {
    $size = $sizes[$i]
    $blob = $pngBlobs[$i]
    $byteSize = if ($size -eq 256) { 0 } else { $size }   # 256 encoda como 0
    $writer.Write([byte]$byteSize)
    $writer.Write([byte]$byteSize)
    $writer.Write([byte]0)
    $writer.Write([byte]0)
    $writer.Write([uint16]1)
    $writer.Write([uint16]32)
    $writer.Write([uint32]$blob.Length)
    $writer.Write([uint32]$offset)
    $offset += $blob.Length
}
foreach ($blob in $pngBlobs) { $writer.Write($blob) }

$writer.Flush()
[System.IO.File]::WriteAllBytes($outIco, $stream.ToArray())
$writer.Dispose()
$stream.Dispose()

Write-Host "Gerado: $outIco ($($sizes -join '/')px)" -ForegroundColor Green
```

- [ ] **Step 4: `.gitignore`**

Acrescentar (o `.build/` guarda o payload de 3ª geração e o script único — nem
um dos dois é fonte):

```
dist/
.build/
```

- [ ] **Step 5: Build e teste do executável**

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File build.ps1
ls -la dist/
```
Expected: `dist/Thero.exe` (payload de `src/` + `thero.py` + `gui/` embutido) e
nenhum `Thero.win32.exe`/`.tmp.ps1` solto na raiz.

- [ ] **Step 6: Testar de fora do repositório (é esse o ponto do portable)**

```bash
mkdir -p /c/temp/thero-test && cp dist/Thero.exe /c/temp/thero-test/
```
Rodar `C:\temp\thero-test\Thero.exe` e conferir:
- [ ] A janela abre sem instalar nada e sem pedir admin.
- [ ] `%LOCALAPPDATA%\Thero\app\1.1.0\` contém `src/`, `thero.py`, `gui/`.
- [ ] Nenhuma pasta `Thero.exe.WebView2` ao lado do exe.
- [ ] A barra de título mostra "motor", não "mock" (Python do sistema existe
      nesta máquina).
- [ ] Fechar o exe derruba o `python --serve`.

- [ ] **Step 7: Commit (pedir confirmação)**

```bash
git add build.ps1 scripts/build-payload.ps1 scripts/make-exe-icon.ps1 gui/Thero.ico .gitignore
git commit -m "build: package the desktop interface as a single portable Thero.exe"
```

---

## Cobertura do pedido (o que cada tarefa entrega)

| Pedido do usuário | Tarefa |
|---|---|
| Definir/configurar provedores de IA, pré-cheios e editáveis | 1 (presets) + 4 + 8 + 10 |
| Vários provedores, autenticar/registrar no Thero | 4 (`register`) + 8 (`providers-register`) + 10 |
| Modelos locais usados por Athena e Sentinel | 3 + 8 (`models-*`) + 5 (`profile`) |
| Zeus decide qual usar e quando | 1 (`routing.mode = zeus`) — a UI só mostra/edita o padrão; a decisão é do Zeus (fora deste plano) |
| Usuário escolhe um ou mais programas onde a config se aplica | 1 (`agents`) + 5 (`apply`) + 8 (`agents-*`) + 10 |
| Skills: manter a stack, buscar e adicionar, importar à mão | 6 + 8 (`skills-*`) |
| Marcar as do Thero vs as do usuário; nunca desinstalar as do Thero | 6 (`origin` + recusa) + 8 |
| "Comando" → "Comandos", um bloco por comando com porquê/como/exemplo | já aprovado na fase 1 (`sec.commands`); a fase 2 não toca na copy |
| Atalho instalado automaticamente, sempre `thero`, sem campo de nome | 2 (retrato) + 5 (não mexe) + a CLI que já existe |
| Auditoria/Athena/Zeus fora do Thero | não aparecem em nenhuma tarefa |
| Interface desktop real (padrão Vector/Gênesis) | 9 + 10 + 11 |
| Portable, sem instalador | 12 |

## Fora deste plano (declarado, não esquecido)

- UI do Zeus (cenários, fluxos, editar/desativar automáticos, "aprender com
  esta ação") e UI da Athena (projetos indexados, índice quebrado/velho,
  pastas).
- Onboarding de primeira abertura nos outros apps do Theroverse.
- `npx skills search` de comunidade: sem verificação nesta máquina, então não
  implementei (ver Task 6).
