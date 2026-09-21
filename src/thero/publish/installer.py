from __future__ import annotations

"""
Publicador das skills/comandos first-party do Theroverse.

Percorre o registro de capacidades e escreve, para cada agente escolhido
(claude / opencode / qoder), os arquivos nativos de skill/comando que o
agente carrega. É o complemento "descartável/em texto" ao servidor MCP.

Resolução de base por agente (com override explícito por ``out_dir``):
- claude   → ``~/.claude/skills`` (ou ``./.claude/skills`` com local=True)
- qoder    → env ``THERO_QODER_SKILLS_DIR`` → senão ``~/.qoder/skills``
- opencode → env ``THERO_OPENCODE_CMD_DIR``  → senão
             ``~/.config/opencode/command``

Os caminhos dos CLIs (athena.py / zeus.py / thero.py) são resolvidos em
tempo de publicação pelas bridges, então o comando embutido nas skills já
aponta para os scripts reais da máquina. Ferramenta sem script
disponível é pulada com aviso (não inventa caminho).
"""

import sys
from pathlib import Path

from thero.integrations.athena_bridge import find_athena_script
from thero.integrations.zeus_bridge import find_zeus_script
from thero.mcp import capabilities
from thero.publish import renderers
from thero.settings import CLAUDE_DIR


def base_dir_for(agent: str, *, local: bool, out_dir: Path | None) -> Path:
    """Diretório-alvo (por agente) onde os arquivos são escritos."""

    if out_dir is not None:
        return out_dir

    if agent == renderers.CLAUDE:
        return (Path.cwd() / ".claude" / "skills") if local else (CLAUDE_DIR / "skills")

    if agent == renderers.QODER:
        import os

        env = os.environ.get("THERO_QODER_SKILLS_DIR")
        return Path(env).expanduser() if env else Path.home() / ".qoder" / "skills"

    # opencode
    import os

    env = os.environ.get("THERO_OPENCODE_CMD_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".config" / "opencode" / "command"


def _script_for(kind: str, entry_path: Path) -> Path | None:
    if kind == capabilities.ATHENA:
        return find_athena_script(entry_path)
    if kind == capabilities.ZEUS:
        return find_zeus_script(entry_path)
    return entry_path  # thero


def _command_template(kind: str, script: Path, argv_template: list[str]) -> str:
    """Monta 'python <script> <argv...>' com placeholders <arg> no lugar."""

    parts = ["python", str(script)]
    parts += [a if not a.startswith("<") else a for a in argv_template]
    return " ".join(parts)


def _template_argv(cap: capabilities.Capability) -> list[str]:
    """
    argv com placeholders ``<prop>`` nos argumentos posicionais/obrigatórios,
    para a skill mostrar o formato do comando sem valores concretos.
    """

    fake = {
        prop: f"<{prop}>"
        for prop, spec in cap.input_schema.get("properties", {}).items()
        if prop in cap.input_schema.get("required", [])
    }
    return cap.build_argv(fake)


def publish(
    entry_path: Path,
    *,
    agents: list[str],
    local: bool = False,
    out_dir: Path | None = None,
    project_dir: Path | None = None,
) -> list[Path]:
    """
    Escreve as skills/comandos para os ``agents`` dados. Retorna a lista
    de arquivos escritos. Idempotente: sobrescreve só os nossos arquivos.
    """

    project_dir = project_dir or Path.cwd()
    written: list[Path] = []

    for agent in agents:
        base = base_dir_for(agent, local=local, out_dir=out_dir)

        for cap in capabilities.all_capabilities():
            script = _script_for(cap.kind, entry_path)

            if script is None:
                print(
                    f"[WARN] pulando '{cap.name}' em {agent}: script "
                    f"({cap.kind}) não resolvido. Rode 'thero --index' "
                    "(ou --plan) uma vez para instalar a ferramenta."
                )
                continue

            command = _command_template(cap.kind, script, _template_argv(cap))
            content = renderers.render(cap, agent, command)

            target = base / renderers.relative_path_for(cap, agent)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
            written.append(target)

        print(f"[OK] {agent}: {len([w for w in written if w.exists()])} arquivo(s) em {base}")

    return written


def resolve_agents(requested: str) -> list[str]:
    """Normaliza --publish-agent (aceita 'all' ou CSV de agentes)."""

    if requested == renderers.ALL:
        return list(renderers.AGENT_KINDS)

    agents = [a.strip() for a in requested.split(",") if a.strip()]
    unknown = [a for a in agents if a not in renderers.AGENT_KINDS]

    if unknown:
        raise ValueError(
            f"agente(s) desconhecido(s): {', '.join(unknown)}; "
            f"esperado um de {', '.join(renderers.AGENT_KINDS)} ou 'all'"
        )

    return agents


def serve_command(entry_path: Path) -> str:
    """Linha pronta para o usuário registrar o servidor MCP num agente."""

    return f"{sys.executable} {entry_path} --mcp"
