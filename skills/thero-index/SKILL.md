---
name: thero-index
description: Indexa a arquitetura do projeto atual com a Athena (.athena/). Use só quando o usuário pedir explicitamente.
disable-model-invocation: true
---

# thero-index

Rode na pasta do projeto atual (sem `cd` para a raiz do plugin):

`python3 <thero.py> --index`

`<thero.py>` fica duas pastas acima deste arquivo (`../../thero.py`); no Claude Code: `${CLAUDE_PLUGIN_ROOT}/thero.py`. Em sessão não interativa a clonagem automática da Athena é pulada: se faltar, avise o usuário.
