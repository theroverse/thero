from __future__ import annotations

import os
import sys
from pathlib import Path

from thero.integrations.tool_repo import ensure_tool_repo
from thero.system.process import run_command

ATHENA_PATH_ENV_VAR = "THERO_ATHENA_PATH"

ATHENA_REPO_URL = "https://github.com/theroverse/athena.git"

ATHENA_ENTRY_SCRIPT = "athena.py"


def find_athena_script(entry_path: Path) -> Path | None:
    """
    Localiza o athena.py. Ordem:

    1. Variável de ambiente THERO_ATHENA_PATH (caminho explícito
       para o athena.py).
    2. Pasta irmã "athena/athena.py", assumindo o layout padrão do
       monorepo myscripts (thero/ e athena/ lado a lado).
    3. Cópia gerenciada em "~/.thero/tools/athena" — clonada (ou
       atualizada, se desatualizada) automaticamente via git,
       com confirmação do usuário. Cobre quem instalou só o
       thero, isolado, sem o layout do monorepo.
    """

    env_path = os.environ.get(ATHENA_PATH_ENV_VAR)

    if env_path:
        candidate = Path(env_path).expanduser()
        return candidate if candidate.is_file() else None

    sibling = entry_path.parent.parent / "athena" / "athena.py"

    if sibling.is_file():
        return sibling

    return ensure_tool_repo(
        "athena",
        ATHENA_REPO_URL,
        ATHENA_ENTRY_SCRIPT,
    )


def run_athena_index(entry_path: Path, max_files: int | None = None) -> bool:

    print()
    print("=" * 70)
    print("Athena — indexação de arquitetura")
    print("=" * 70)

    athena_script = find_athena_script(entry_path)

    if athena_script is None:
        print(
            "[ERROR] athena.py não disponível. Rode este comando "
            "num terminal interativo para permitir a instalação "
            "automática, instale a Athena "
            "(https://github.com/theroverse/athena) manualmente na "
            "pasta irmã de thero (ex.: ~/.myscripts/athena), ou "
            f"defina a variável de ambiente {ATHENA_PATH_ENV_VAR} "
            "apontando para o athena.py."
        )
        return False

    project_dir = str(Path.cwd())

    sys.stdout.flush()

    cmd = [
        sys.executable,
        str(athena_script),
        "index",
        project_dir,
    ]

    if max_files is not None:
        cmd += ["--max-files", str(max_files)]

    result = run_command(cmd, capture=False)

    return result.returncode == 0
