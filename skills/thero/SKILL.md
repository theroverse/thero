---
name: thero
description: Roda o thero (instala/atualiza Agent Skills, consolida o CLAUDE.md global). Use só quando o usuário pedir explicitamente.
argument-hint: "[skills|merge|check|update]"
disable-model-invocation: true
---

# thero

Script: `thero.py` na raiz do plugin, duas pastas acima desta (`../../thero.py`). No Claude Code: `${CLAUDE_PLUGIN_ROOT}/thero.py`.

Rode a partir da pasta do projeto atual, sem `cd` para a raiz do plugin:

| Argumento | Comando |
|-----------|---------|
| `skills` | `python3 <thero.py> --skills-only` |
| `merge` | `python3 <thero.py> --merge-only` |
| `check` | `python3 <thero.py> --check` |
| `update` | `python3 <thero.py> --update` |

Sem argumento ou argumento desconhecido: pergunte qual usar. O fluxo completo e a instalação do comando `thero` no shell pedem prompts interativos: mande o usuário rodar `thero` no próprio terminal.

`skills` e `merge` alteram `~/.claude` (global). Adicione `--local` só se o usuário pedir escopo do projeto. Mostre a saída do script; não a resuma.
