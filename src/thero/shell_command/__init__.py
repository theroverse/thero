from __future__ import annotations

import os
from pathlib import Path

from thero.settings import COMMAND_MARKER_END, COMMAND_MARKER_START


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


def install_global_command(
    command_name: str,
    entry_path: Path,
    local: bool = False,
) -> None:

    print()
    print("=" * 70)
    print(
        "Local command" if local else "Global command"
    )
    print("=" * 70)

    if os.name == "nt":
        from thero.shell_command.windows import (
            install_global_command_windows,
            install_local_command_windows,
        )

        if local:
            install_local_command_windows(command_name, entry_path)
        else:
            install_global_command_windows(command_name, entry_path)
    else:
        from thero.shell_command.posix import (
            install_global_command_posix,
            install_local_command_posix,
        )

        if local:
            install_local_command_posix(command_name, entry_path)
        else:
            install_global_command_posix(command_name, entry_path)
