---
name: thero-audit
description: Audita o projeto atual com o thero e gera CLAUDE_AUDIT.md. Use só quando o usuário pedir explicitamente.
disable-model-invocation: true
---

# thero-audit

Rode na pasta do projeto atual (sem `cd` para a raiz do plugin):

`python3 <thero.py> --audit-only`

`<thero.py>` fica duas pastas acima deste arquivo (`../../thero.py`); no Claude Code: `${CLAUDE_PLUGIN_ROOT}/thero.py`. Depois leia `CLAUDE_AUDIT.md` gerado e resuma os achados.
