import json

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
