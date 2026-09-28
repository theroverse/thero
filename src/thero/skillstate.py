"""O que a tela de Skills precisa saber: quem instalou o que, e para onde vai.

Procedencia: NAO existe marcador no disco (ver a tabela de fatos). A origem
real e "esta pasta esta na lista do catalogo do Thero?", por isso
`thero_skill_names()` vem do proprio catalogo, nao de um registro paralelo
que poderia descer do passo. Consequencia assumida: uma copia propria do
usuario com nome de catalogo (ex.: "caveman", que ESTA em catalog.py) e
classificada como "thero" e nao sai pela interface -- pergunte 1 ao dono.
O manifesto abaixo e anotacao opcional do usuario, nao fonte de verdade.

Busca: o `npx skills search` nunca foi verificado nesta maquina (o npm local
esta quebrado), entao NAO invento subcomando. `search()` filtra o catalogo
conhecido e `NOTE` declara o que nao foi verificado.

Remocao e reimportacao: movem para a quarentena, nunca apagam (mesma politica
do backup de `apply.py`: tocar um arquivo sem saber o que tem dentro e
proibido). Nada aqui imprime: o stdout da ponte e o canal JSON.
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


def _read_skill_md(folder: Path) -> str:
    """Texto do SKILL.md para EXIBIR, sem fingir que leu.

    utf-8-sig tolera BOM; cai para cp1252 (o que o PowerShell 5.1 escreve)
    so quando o utf-8 falha. Falhou nas duas -> vazio, e a linha sai sem
    descricao: substituir byte ilegivel por U+FFFD produziria texto inventado
    na tela (mesma regra de `_read_text` em `apply.py`).
    """
    try:
        return (folder / "SKILL.md").read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        pass
    except OSError:
        return ""
    try:
        return (folder / "SKILL.md").read_text(encoding="cp1252")
    except (UnicodeDecodeError, OSError):
        return ""


def _read_desc(folder: Path) -> str:
    """Primeiro `description:` do SKILL.md, sem parser de YAML completo."""
    for line in _read_skill_md(folder).splitlines()[:24]:
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
            "desc": _read_desc(folder),
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
        # A Task 10 mostra o catalogo inteiro e marca o que ja esta na base:
        # sem esta flag a tela esconderia o que ainda nao foi instalado.
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
        tag = suffix if n == 1 else "%s_%d" % (suffix, n)
        candidate = quarantine / ("%s__%s" % (name, tag))
        if not candidate.exists():
            return candidate
        n += 1


def _is_folder_name(name) -> bool:
    """Um nome de skill e UM nivel de caminho, nada alem disso.

    O nome chega cru pelo canal JSON (`skills-uninstall` repassa
    `request["name"]` da janela). `root / name` com "../../Documentos"
    aponta para fora da base de skills, e a ponte moveria qualquer pasta
    para a quarentena. Comparar com `Path(name).name` descarta separador,
    caminho absoluto e unidade (`Path("C:/x").name` e "x").
    """
    if not isinstance(name, str):
        return False
    return name not in ("", ".", "..") and name == Path(name).name


def uninstall(name: str, base_dir: Optional[Path] = None,
              quarantine: Optional[Path] = None, local: bool = False) -> dict:
    if not _is_folder_name(name):
        return {"ok": False,
                "msg": "nome de skill invalido: %s" % str(name)[:60]}
    root = Path(base_dir) if base_dir else skills_base(local)
    folder = root / name
    if not folder.is_dir():
        return {"ok": False, "msg": "nao encontrei %s em %s" % (name, root)}
    if name in thero_skill_names():
        # DICT, nao excecao: a ponte da Task 8 le out["ok"] e devolve _err
        # no mesmo canal JSON. "esta na lista" e o que sabemos (A11).
        return {"ok": False,
                "msg": "%s esta na lista do Thero: a interface nao "
                       "desinstala skill de catalogo" % name}
    destination = _unique_quarantine_target(
        Path(quarantine) if quarantine else quarantine_dir(), name)
    try:
        shutil.move(str(folder), str(destination))
    except OSError as exc:
        # Mesma regra do B4 em apply.py: pasta travada e recusa com texto
        # legivel, nao traceback estourando o canal JSON da janela.
        return {"ok": False,
                "msg": "nao consegui mover %s: %s" % (name, exc)}
    return {"ok": True, "quarantine": str(destination),
            "msg": "movida para a quarentena: %s" % destination}


def import_skill(source: Path, base_dir: Optional[Path] = None,
                 local: bool = False,
                 quarantine: Optional[Path] = None) -> dict:
    src = Path(source)
    if not src.name:
        # Raiz de unidade/disco nao tem nome: o alvo seria a PROPRIA base e
        # o copytree derramaria o conteudo dela dentro dela mesma.
        return {"ok": False,
                "msg": "a pasta indicada nao tem nome de skill: %s" % src}
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
    if target.exists() and target.resolve() == src.resolve():
        # A14: a origem JA e o alvo -- mover para a quarentena aqui apagaria
        # a skill da propria tela antes de copiar o que nao existe mais.
        return {"ok": False,
                "msg": "%s ja e a pasta instalada: nao ha o que importar "
                       "sobre ela" % src}
    replaced = ""
    try:
        if target.exists():
            # A13: a copia antiga e do usuario e pode ter trabalho dentro --
            # vai para a quarentena (mesma regra do uninstall) antes da
            # nova entrar.
            aside = _unique_quarantine_target(
                Path(quarantine) if quarantine else quarantine_dir(),
                src.name)
            shutil.move(str(target), str(aside))
            replaced = str(aside)
        shutil.copytree(str(src), str(target))
    except OSError as exc:
        msg = "nao consegui importar %s: %s" % (src.name, exc)
        if replaced:
            msg += " (a copia anterior continua em %s)" % replaced
        return {"ok": False, "msg": msg}
    msg = "importada para %s" % target
    if replaced:
        msg += " (a copia anterior ficou em %s)" % replaced
    return {"ok": True, "path": str(target), "origin": "user", "msg": msg}


def install_command(repo: str, skill: str,
                    global_install: bool = True) -> list:
    return build_skill_install_command(repo, skill, global_install)


def save_manifest(manifest: dict, path: Optional[Path] = None) -> Path:
    """Registro opcional de procedencia propria do usuario.

    Nao e fonte de verdade da UI (a fonte e o catalogo) -- existe so para o
    usuario anotar o que ele mesmo instalou, se quiser. Nenhuma funcao deste
    modulo o le: sem um formato firmado com a janela, inventar a leitura agora
    seria mecanismo novo (pergunte 1 ao dono).
    """
    target = Path(path) if path else THERO_DIR / "skill-manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target
