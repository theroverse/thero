---
name: thero-plan
description: Planeja uma tarefa com o Zeus sobre o índice da Athena (.claude/zeus-plan.md). Use só quando o usuário pedir explicitamente.
argument-hint: "<tarefa>"
disable-model-invocation: true
---

# thero-plan

Rode na pasta do projeto atual (sem `cd` para a raiz do plugin):

`python3 <thero.py> --plan "<tarefa>"`

`<thero.py>` fica duas pastas acima deste arquivo (`../../thero.py`); no Claude Code: `${CLAUDE_PLUGIN_ROOT}/thero.py`. Sem tarefa, pergunte. Depois leia `.claude/zeus-plan.md` e apresente o plano. Em sessão não interativa a clonagem automática do Zeus é pulada: se faltar, avise o usuário.
