from __future__ import annotations

"""
Renderizadores de arquivos de skill/comando por agente.

Dado o registro de ``Capability`` (fonte única de verdade), produz o
formato nativo de cada agente para que humanos e IAs descubram/invocuem
as ferramentas do Theroverse por *skills* e *slash-commands* — o
complemento "descartável" ao servidor MCP (que é o caminho programático).

Agentes suportados (todos consomem markdown com frontmatter; os nomes de
chave variam):

- ``claude``   → Agent Skill em ``<skills>/<name>/SKILL.md``
                 (frontmatter ``name`` + ``description``).
- ``qoder``    → mesmo formato de SKILL.md (Qoder lê skills nativas).
- ``opencode`` → comando custom em ``<command>/<name>.md``
                 (frontmatter ``description``; corpo = prompt).

Cada corpo instrui o agente a rodar o CLI real da ferramenta, com o
caminho absoluto já resolvido em tempo de publicação (passado pelo
installer via ``command_template``). Nenhum aqui toca a rede — só monta
texto — então os testes comparam strings.
"""

from thero.mcp import capabilities

# Identificadores de agente aceitos por --publish-agent.
CLAUDE = "claude"
QODER = "qoder"
OPENCODE = "opencode"
ALL = "all"

AGENT_KINDS = (CLAUDE, QODER, OPENCODE)


def _skill_frontmatter(name: str, description: str) -> str:
    # YAML escalar simples: as descrições não têm dois-pontos/aspas que
    # exijam quoting; mantemos em uma linha com quebra literal via |.
    safe = description.replace("\n", " ").strip()
    return f"---\nname: {name}\ndescription: {safe}\n---\n"


def _placeholder_command(command_template: str, cap: capabilities.Capability) -> str:
    return command_template.format(
        **{prop: f"<{prop}>" for prop in cap.input_schema.get("properties", {})}
    )


def _arg_table(cap: capabilities.Capability) -> str:
    props = cap.input_schema.get("properties", {})
    required = set(cap.input_schema.get("required", []))

    if not props:
        return "_Esta ferramenta não recebe argumentos._"

    lines = ["| Argumento | Tipo | Obrigatório | Descrição |", "|---|---|---|---|"]

    for prop, spec in props.items():
        ptype = spec.get("type", "string")

        if "enum" in spec:
            ptype = " | ".join(map(str, spec["enum"]))

        lines.append(
            f"| `{prop}` | {ptype} | {'sim' if prop in required else 'não'} "
            f"| {spec.get('description', '').strip()} |"
        )

    return "\n".join(lines)


def _body(cap: capabilities.Capability, command: str) -> str:
    return (
        f"# {cap.title}\n\n"
        f"{cap.description}\n\n"
        "## Como invocar\n\n"
        "Prefira a **ferramenta MCP** `theroverse` (registro único para "
        "Claude Code, OpenCode e Qoder — rode `thero --mcp`). Sem MCP, "
        "chame o CLI diretamente:\n\n"
        f"```bash\n{command}\n```\n\n"
        "## Argumentos\n\n"
        f"{_arg_table(cap)}\n"
    )


def render_skill_md(cap: capabilities.Capability, command: str) -> str:
    """SKILL.md no formato compartilhado Claude Code / Qoder."""

    return _skill_frontmatter(cap.name, cap.description) + "\n" + _body(cap, command)


def render_opencode_command(cap: capabilities.Capability, command: str) -> str:
    """Comando custom do OpenCode: frontmatter ``description`` + corpo."""

    safe = cap.description.replace("\n", " ").strip()
    front = f"---\ndescription: {safe}\n---\n"
    prompt = (
        f"Use a ferramenta **{cap.title}** do Theroverse. Rode:\n\n"
        f"```bash\n{command}\n```\n\n"
        "Argumentos (substitua os <placeholders>):\n\n"
        f"{_arg_table(cap)}\n"
    )
    return front + "\n" + prompt


def filename_for(cap: capabilities.Capability, agent: str) -> str:
    if agent in (CLAUDE, QODER):
        return "SKILL.md"
    return f"{cap.name}.md"


def relative_path_for(cap: capabilities.Capability, agent: str) -> str:
    """Caminho (relativo à base do agente) onde o arquivo é escrito."""

    if agent in (CLAUDE, QODER):
        # Skill em pasta própria com SKILL.md dentro.
        return f"{cap.name}/SKILL.md"
    return f"{cap.name}.md"


def render(cap: capabilities.Capability, agent: str, command: str) -> str:
    if agent == OPENCODE:
        return render_opencode_command(cap, command)
    return render_skill_md(cap, command)
