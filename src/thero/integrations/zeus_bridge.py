from __future__ import annotations

import os
import sys
from pathlib import Path

from thero.integrations.tool_repo import ensure_tool_repo
from thero.system.process import run_command

ZEUS_PATH_ENV_VAR = "THERO_ZEUS_PATH"

ZEUS_REPO_URL = "https://github.com/theroverse/zeus.git"

ZEUS_ENTRY_SCRIPT = "zeus.py"


def find_zeus_script(entry_path: Path) -> Path | None:
    """
    Localiza o zeus.py. Ordem:

    1. Variável de ambiente THERO_ZEUS_PATH (caminho explícito para
       o zeus.py).
    2. Pasta irmã "zeus/zeus.py", assumindo o layout padrão do
       monorepo myscripts (thero/ e zeus/ lado a lado).
    3. Cópia gerenciada em "~/.thero/tools/zeus" — clonada (ou
       atualizada, se desatualizada) automaticamente via git, com
       confirmação do usuário. Cobre quem instalou só o thero,
       isolado, sem o layout do monorepo (mesmo mecanismo usado
       para a Athena).
    """

    env_path = os.environ.get(ZEUS_PATH_ENV_VAR)

    if env_path:
        candidate = Path(env_path).expanduser()
        return candidate if candidate.is_file() else None

    sibling = entry_path.parent.parent / "zeus" / "zeus.py"

    if sibling.is_file():
        return sibling

    return ensure_tool_repo(
        "zeus",
        ZEUS_REPO_URL,
        ZEUS_ENTRY_SCRIPT,
    )


def run_zeus_plan(
    entry_path: Path,
    task: str,
    *,
    context: str | None = None,
) -> bool:

    print()
    print("=" * 70)
    print("Zeus — planejamento de tarefa")
    print("=" * 70)

    zeus_script = find_zeus_script(entry_path)

    if zeus_script is None:
        print(
            "[ERROR] zeus.py não disponível. Rode este comando num "
            "terminal interativo para permitir a instalação "
            "automática, instale o Zeus "
            "(https://github.com/theroverse/zeus) manualmente na "
            "pasta irmã de thero (ex.: ~/.myscripts/zeus), ou "
            f"defina a variável de ambiente {ZEUS_PATH_ENV_VAR} "
            "apontando para o zeus.py."
        )
        return False

    project_dir = str(Path.cwd())

    command = [
        sys.executable,
        str(zeus_script),
        "plan",
        task,
        project_dir,
    ]

    if context is not None:
        command += ["--context", context]

    sys.stdout.flush()

    result = run_command(
        command,
        capture=False,
    )

    return result.returncode == 0
