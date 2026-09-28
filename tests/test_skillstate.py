import json
from pathlib import Path

import pytest

from thero import skillstate


@pytest.fixture
def base(tmp_path):
    root = tmp_path / "skills"
    # "engineering-manager" e "supabase" estao no catalogo (medido); os dois
    # ultimos NAO estao -- sao a copia propria do usuario. `caveman` nao serve
    # de exemplo aqui: ela ESTA no catalogo (A11).
    for name in ("engineering-manager", "supabase", "minha-skill",
                 "meu-proprio"):
        folder = root / name
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(
            "---\nname: %s\ndescription: teste\n---\n\ncorpo\n" % name,
            encoding="utf-8")
    (root / "sem-skill-md").mkdir()
    return root


def test_thero_names_come_from_the_catalog_plus_impeccable():
    names = skillstate.thero_skill_names()
    assert "engineering-manager" in names
    assert "supabase-postgres-best-practices" in names
    assert "impeccable" in names
    # medido em 2026-09-28: catalog.py:73-79 traz o repo JuliusBrussee/caveman,
    # entao "caveman" E do Thero -- proteger por nome e isso que acontece.
    assert "caveman" in names
    assert "minha-skill" not in names
    assert "nao-existe-no-catalogo" not in names


def test_installed_marks_origin_and_skips_folders_without_a_skill_md(base):
    rows = skillstate.installed(base_dir=base)
    by_name = {r["name"]: r for r in rows}
    assert set(by_name) == {"engineering-manager", "supabase", "minha-skill",
                            "meu-proprio"}
    assert by_name["engineering-manager"]["origin"] == "thero"
    assert by_name["supabase"]["origin"] == "thero"
    assert by_name["minha-skill"]["origin"] == "user"
    assert by_name["meu-proprio"]["origin"] == "user"


def test_uninstall_refuses_a_skill_the_thero_installed(base, tmp_path):
    # A ponte (Task 8: `out = skillstate.uninstall(...)`, `if not out["ok"]`)
    # consome DICT e serializa no canal JSON: levantar excecao aqui quebraria
    # a ponte. Contrato real = {"ok": False} e a pasta continua no disco.
    q = tmp_path / "q"
    out = skillstate.uninstall("supabase", base_dir=base, quarantine=q)
    assert out["ok"] is False
    assert "Thero" in out["msg"]
    assert (base / "supabase" / "SKILL.md").exists()
    assert not q.exists()           # recusou antes de mover qualquer coisa


def test_uninstall_moves_to_quarantine_instead_of_deleting(base, tmp_path):
    q = tmp_path / "q"
    out = skillstate.uninstall("meu-proprio", base_dir=base, quarantine=q)
    assert out["ok"] is True
    assert not (base / "meu-proprio").exists()
    assert (q / "meu-proprio" / "SKILL.md").exists()
    assert out["quarantine"]


def test_uninstall_keeps_a_collision_in_quarantine_readable(base, tmp_path):
    q = tmp_path / "q"
    skillstate.uninstall("meu-proprio", base_dir=base, quarantine=q)
    (base / "meu-proprio").mkdir()
    (base / "meu-proprio" / "SKILL.md").write_text("segunda", encoding="utf-8")
    skillstate.uninstall("meu-proprio", base_dir=base, quarantine=q)
    # Duas pastas, a segunda com sufixo: nada foi por cima de nada.
    names = sorted(p.name for p in q.iterdir())
    assert len(names) == 2
    assert names[0] == "meu-proprio"
    assert names[1].startswith("meu-proprio__")


def test_uninstall_of_the_unknown_says_so(base, tmp_path):
    out = skillstate.uninstall("fantasma", base_dir=base,
                               quarantine=tmp_path / "q")
    assert out["ok"] is False


def test_uninstall_refuses_a_name_that_leaves_the_base(base, tmp_path):
    # O nome vem da janela pelo canal JSON ("skills-uninstall" repassa
    # request["name"] cru). Sem a guarda, root / "../../Documents" aponta
    # para fora da base de skills e a ponte moveria qualquer pasta para a
    # quarentena. Mesma classe da validacao de ids dos provedores (I4).
    q = tmp_path / "q"
    escape = base.parent / "fora-da-base"
    escape.mkdir()
    (escape / "SKILL.md").write_text("---\nname: fora\n---\n",
                                     encoding="utf-8")
    for bad in ("../fora-da-base", "..\\fora-da-base", "", ".", "..",
                str(escape), "a/b", 5, None):
        out = skillstate.uninstall(bad, base_dir=base, quarantine=q)
        assert out["ok"] is False, bad
        assert (escape / "SKILL.md").exists()
    assert not q.exists()


def test_uninstall_turns_a_move_failure_into_a_refusal(base, tmp_path,
                                                      monkeypatch):
    # Mesma regra do B4 em apply.py: uma pasta travada (PermissionError)
    # vira recusa com msg legivel, nao um traceback na janela.
    def boom(src, dst):
        raise PermissionError(5, "acesso negado")

    monkeypatch.setattr(skillstate.shutil, "move", boom)
    out = skillstate.uninstall("meu-proprio", base_dir=base,
                               quarantine=tmp_path / "q")
    assert out["ok"] is False
    assert "meu-proprio" in out["msg"]
    assert (base / "meu-proprio" / "SKILL.md").exists()


def test_import_requires_a_skill_md(tmp_path, base):
    junk = tmp_path / "junk"
    junk.mkdir()
    out = skillstate.import_skill(junk, base_dir=base)
    assert out["ok"] is False
    assert "SKILL.md" in out["msg"]


def test_import_copies_the_folder_and_marks_it_user(tmp_path, base):
    # nome proprio do teste (A13): nao colide com o fixture, senao a
    # importacao empurraria a pasta do fixture para a quarentena.
    src = tmp_path / "criada-por-mim"
    src.mkdir()
    (src / "SKILL.md").write_text(
        "---\nname: criada-por-mim\ndescription: x\n---\n", encoding="utf-8")
    (src / "reference.md").write_text("apoio", encoding="utf-8")
    out = skillstate.import_skill(src, base_dir=base)
    assert out["ok"] is True
    target = base / "criada-por-mim"
    assert (target / "SKILL.md").exists()
    assert (target / "reference.md").exists()
    rows = {r["name"]: r for r in skillstate.installed(base_dir=base)}
    assert rows["criada-por-mim"]["origin"] == "user"


def test_import_refuses_to_overwrite_a_thero_skill(tmp_path, base):
    src = tmp_path / "supabase"
    src.mkdir()
    (src / "SKILL.md").write_text("---\nname: supabase\n---\n",
                                  encoding="utf-8")
    out = skillstate.import_skill(src, base_dir=base)
    assert out["ok"] is False
    assert "Thero" in out["msg"]


def test_import_over_a_user_folder_quarantines_the_old_copy(tmp_path, base):
    # A13: reimportar NUNCA e um rmtree na copia antiga do usuario.
    q = tmp_path / "q"
    old = base / "criada-por-mim"
    old.mkdir()
    (old / "SKILL.md").write_text(
        "---\nname: criada-por-mim\n---\n\nrascunho antigo\n",
        encoding="utf-8")
    src = tmp_path / "criada-por-mim"
    src.mkdir()
    (src / "SKILL.md").write_text(
        "---\nname: criada-por-mim\ndescription: nova\n---\n",
        encoding="utf-8")
    out = skillstate.import_skill(src, base_dir=base, quarantine=q)
    assert out["ok"] is True
    assert "antigo" in (q / "criada-por-mim" / "SKILL.md").read_text(
        encoding="utf-8")
    assert "nova" in (base / "criada-por-mim" / "SKILL.md").read_text(
        encoding="utf-8")


def test_import_refuses_the_folder_that_is_already_installed(tmp_path,
                                                             base):
    # A14: origem == alvo. Sem a guarda, a propria skill da tela iria para a
    # quarentena e a copia seguinte quebraria sobre o caminho vazio.
    q = tmp_path / "q"
    mine = base / "minha-skill"
    out = skillstate.import_skill(mine, base_dir=base, quarantine=q)
    assert out["ok"] is False
    assert (mine / "SKILL.md").exists()
    assert not q.exists()


def test_import_refuses_a_root_that_has_no_folder_name(tmp_path, base):
    # Path("C:\\").name e "" -> o alvo seria a PROPRIA base, e o copytree
    # tentaria derramar o disco inteiro dentro dela. Checa antes de tocar
    # em qualquer arquivo, entao a raiz nunca precisa ter SKILL.md.
    anchor = Path(Path.cwd().anchor)
    out = skillstate.import_skill(anchor, base_dir=base,
                                  quarantine=tmp_path / "q")
    assert out["ok"] is False
    assert "nome" in out["msg"]      # recusa pelo alvo, nao pelo SKILL.md
    assert sorted(p.name for p in base.iterdir()) == [
        "engineering-manager", "meu-proprio", "minha-skill", "sem-skill-md",
        "supabase"]


def test_import_turns_a_copy_failure_into_a_refusal(tmp_path, base,
                                                   monkeypatch):
    # B4 tambem vale aqui: se o copytree estoura (pasta travada, disco
    # cheio), a janela recebe recusa legivel e a base nao ganha alvo pela
    # metade.
    calls = []

    def boom(src, dst, **kw):
        calls.append((src, dst))
        raise OSError(28, "sem espaco")

    monkeypatch.setattr(skillstate.shutil, "copytree", boom)
    src = tmp_path / "incompleta"
    src.mkdir()
    (src / "SKILL.md").write_text("---\nname: incompleta\n---\n",
                                  encoding="utf-8")
    out = skillstate.import_skill(src, base_dir=base)
    assert out["ok"] is False
    assert calls
    assert not (base / "incompleta").exists()
    assert "incompleta" in out["msg"]


def test_a_failed_copy_still_points_at_the_quarantined_old_copy(tmp_path,
                                                               base,
                                                               monkeypatch):
    # Se o copytree estoura DEPOIS de a copia antiga ter ido para a
    # quarentena, a base ficou sem a skill: a recusa tem de dizer onde o
    # trabalho do usuario esta, senao ele procura no escuro.
    def boom(src, dst, **kw):
        raise OSError(13, "negado")

    monkeypatch.setattr(skillstate.shutil, "copytree", boom)
    q = tmp_path / "q"
    old = base / "criada-por-mim"
    old.mkdir()
    (old / "SKILL.md").write_text("---\nname: criada-por-mim\n---\n\nvelha\n",
                                  encoding="utf-8")
    src = tmp_path / "criada-por-mim"
    src.mkdir()
    (src / "SKILL.md").write_text("---\nname: criada-por-mim\n---\n",
                                  encoding="utf-8")
    out = skillstate.import_skill(src, base_dir=base, quarantine=q)
    assert out["ok"] is False
    assert "copia anterior" in out["msg"]
    assert "criada-por-mim" in (q / "criada-por-mim" / "SKILL.md").read_text(
        encoding="utf-8")
    assert not (base / "criada-por-mim").exists()


def test_search_filters_the_known_catalog_and_labels_the_source(base):
    rows = skillstate.search("postgres", base_dir=base)
    assert rows
    assert all(r["source"] == "catalogo do thero" for r in rows)
    assert all("repo" in r and "skill" in r for r in rows)
    assert skillstate.search("zznadaaver", base_dir=base) == []


def test_search_flags_what_is_already_installed(base):
    # A Task 10 mostra o catalogo INTEIRO e marca o que ja esta la; se a
    # flag sumir, a tela esconde as skills nao instaladas.
    rows = {r["skill"]: r for r in skillstate.search("supabase",
                                                     base_dir=base)}
    assert rows["supabase"]["installed"] is True
    assert rows["supabase-postgres-best-practices"]["installed"] is False
    assert all("installed" in r for r in skillstate.search("",
                                                           base_dir=base))


def test_search_documents_that_the_community_cli_is_unverified(base):
    rows = skillstate.search("", base_dir=base)
    assert any(r.get("unverified") for r in rows) or "npx" in skillstate.NOTE


def test_skill_line_command_matches_the_installer_builder():
    command = skillstate.install_command("supabase/agent-skills", "supabase")
    assert command[:4] == ["npx", "skills", "add", "supabase/agent-skills"]
    assert "--skill" in command and "supabase" in command
    assert "--global" in command
    assert "--global" not in skillstate.install_command(
        "supabase/agent-skills", "supabase", global_install=False)


def test_manifest_round_trip_records_origin_but_never_invents_files(tmp_path):
    path = tmp_path / "manifest.json"
    skillstate.save_manifest({"supabase": "thero", "minha-skill": "user"},
                             path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["minha-skill"] == "user"
    assert path.exists()


def test_installed_of_a_base_that_does_not_exist_is_empty(tmp_path):
    # A janela abre com zero skills e com a base ainda criada pelo
    # instalador: ler uma pasta que nao existe e lista vazia, nao erro.
    assert skillstate.installed(base_dir=tmp_path / "nao-criada") == []


def test_installed_says_nothing_when_the_skill_md_has_no_description(base):
    # O doc de `_read_desc` promete a linha "sem descricao", nao um texto
    # emprestado de outro lugar: sem o campo, o valor e "".
    folder = base / "sem-descricao"
    folder.mkdir()
    (folder / "SKILL.md").write_text("---\nname: sem-descricao\n---\n",
                                     encoding="utf-8")
    rows = {r["name"]: r for r in skillstate.installed(base_dir=base)}
    assert rows["sem-descricao"]["desc"] == ""


def test_installed_reads_a_cp1252_skill_md_without_inventing_text(base):
    # O doc de `_read_skill_md` diz: utf-8-sig, senao cp1252 (o PowerShell
    # 5.1 escreve assim), senao vazio -- nunca U+FFFD, que seria texto
    # inventado na tela. Este arquivo e binario cp1252 invalido em utf-8.
    folder = base / "travada"
    folder.mkdir()
    (folder / "SKILL.md").write_bytes(
        "---\nname: travada\ndescription: Fun\u00e7\u00e3o interna\n---\n"
        .encode("cp1252"))
    rows = {r["name"]: r for r in skillstate.installed(base_dir=base)}
    assert rows["travada"]["desc"] == "Fun\u00e7\u00e3o interna"
    assert "\ufffd" not in rows["travada"]["desc"]


def test_path_helpers_point_where_the_ui_documents(base, tmp_path,
                                                   monkeypatch):
    # installed/uninstall recebem base e quarenta explicitas pela ponte, mas
    # o padrao (sem argumento) e o que a tela mostra: global em
    # ~/.claude/skills, local no cwd do projeto, quarenta sob ~/.thero.
    from thero import settings

    monkeypatch.setattr(skillstate, "THERO_DIR", tmp_path / ".thero")
    monkeypatch.setattr(skillstate, "SKILLS_BASE_GLOBAL",
                        tmp_path / "global" / "skills")
    assert skillstate.skills_base() == tmp_path / "global" / "skills"
    assert skillstate.skills_base(True) == Path.cwd() / ".claude" / "skills"
    quarenta = tmp_path / ".thero" / "quarantine"
    assert skillstate.quarantine_dir() == (
        quarenta / settings.SKILLS_QUARANTINE_DIRNAME)


def test_installed_gives_up_quietly_when_the_skill_md_cannot_be_read(base):
    # SKILL.md pode existir como DIRETORIO (instalador interrompido). Ler
    # falha com OSError: a linha sai sem descricao, e a skill continua na
    # lista -- a tela nao some com o que nao consegue descrever.
    folder = base / "quebrada"
    (folder / "SKILL.md").mkdir(parents=True)
    rows = {r["name"]: r for r in skillstate.installed(base_dir=base)}
    assert rows["quebrada"]["desc"] == ""


def test_installed_leaves_the_description_empty_when_no_codec_fits(base):
    # Nem utf-8 nem cp1252: 0x81 nao existe nas duas. O doc promete vazio,
    # nao caractere de reposicao -- texto inventado na tela.
    folder = base / "ilegivel"
    folder.mkdir()
    (folder / "SKILL.md").write_bytes(b"---\n\xff\x81---\n")
    rows = {r["name"]: r for r in skillstate.installed(base_dir=base)}
    assert rows["ilegivel"]["desc"] == ""


def test_a_third_removal_in_the_same_second_keeps_its_own_folder(base,
                                                                tmp_path,
                                                                monkeypatch):
    # O laco de sufixo so existe porque shutil.move ENCAIXA a pasta dentro
    # da outra quando o destino ja existe: tres remocoes no mesmo timestamp
    # tem de virar tres pastas, cada uma com o seu conteudo.
    from thero.system import process as system_process

    monkeypatch.setattr(system_process, "timestamp", lambda: "TSFIXO")
    q = tmp_path / "q"
    for body in ("primeira", "segunda", "terceira"):
        # A primeira volta reaproveita a pasta do fixture; depois dela a
        # pasta nao existe mais e e recriada.
        folder = base / "meu-proprio"
        folder.mkdir(exist_ok=True)
        (folder / "SKILL.md").write_text(body, encoding="utf-8")
        assert skillstate.uninstall("meu-proprio", base_dir=base,
                                    quarantine=q)["ok"] is True
    names = sorted(p.name for p in q.iterdir())
    assert names == ["meu-proprio", "meu-proprio__TSFIXO",
                     "meu-proprio__TSFIXO_2"]
    kept = sorted((q / n / "SKILL.md").read_text(encoding="utf-8")
                  for n in names)
    assert kept == ["primeira", "segunda", "terceira"]
