from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from thero.mcp import capabilities
from thero.publish import installer, renderers


ENTRY = Path("/repo/thero/thero.py")


# -- renderizadores (string, sem disco) -------------------------------------


def test_render_skill_md_has_frontmatter_and_command():
    cap = capabilities.get_capability("athena_recall")
    text = renderers.render_skill_md(cap, "python athena.py recall <query>")

    assert text.startswith("---\nname: athena_recall\n")
    assert "description:" in text
    assert "python athena.py recall <query>" in text
    assert "`query`" in text  # tabela de argumentos


def test_render_opencode_uses_description_only_frontmatter():
    cap = capabilities.get_capability("zeus_plan")
    text = renderers.render_opencode_command(cap, "python zeus.py plan <task>")

    front = text.split("---")[1]
    assert "description:" in front
    assert "name:" not in front  # opencode não usa name
    assert "python zeus.py plan <task>" in text


def test_render_dispatches_by_agent():
    cap = capabilities.get_capability("thero_audit")
    claude = renderers.render(cap, "claude", "cmd")
    opencode = renderers.render(cap, "opencode", "cmd")

    assert claude.startswith("---\nname: thero_audit")
    assert opencode.startswith("---\ndescription:")


def test_arg_table_lists_required_flag():
    cap = capabilities.get_capability("athena_remember")
    table = renderers._arg_table(cap)

    assert "| `kind` |" in table
    assert "sim" in table  # kind é obrigatório


# -- base_dir / resolve_agents ----------------------------------------------


def test_base_dir_out_dir_wins(tmp_path):
    got = installer.base_dir_for("claude", local=False, out_dir=tmp_path / "x")
    assert got == tmp_path / "x"


def test_base_dir_claude_global_uses_claude_dir():
    with patch.object(installer, "CLAUDE_DIR", Path("/home/u/.claude")):
        got = installer.base_dir_for("claude", local=False, out_dir=None)
    assert got == Path("/home/u/.claude/skills")


def test_base_dir_claude_local_uses_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    got = installer.base_dir_for("claude", local=True, out_dir=None)
    assert got == tmp_path / ".claude" / "skills"


def test_resolve_agents_all_returns_three():
    assert installer.resolve_agents("all") == ["claude", "qoder", "opencode"]


def test_resolve_agents_csv():
    assert installer.resolve_agents("claude,opencode") == ["claude", "opencode"]


def test_resolve_agents_rejects_unknown():
    try:
        installer.resolve_agents("claude,xxx")
    except ValueError as exc:
        assert "xxx" in str(exc)
    else:
        raise AssertionError("deveria ter levantado ValueError")


# -- publish() ponta a ponta (escreve em disco isolado) ---------------------


def test_publish_writes_all_tools_for_claude(tmp_path):
    with patch(
        "thero.publish.installer.find_athena_script",
        return_value=Path("/repo/athena/athena.py"),
    ), patch(
        "thero.publish.installer.find_zeus_script",
        return_value=Path("/repo/zeus/zeus.py"),
    ):
        written = installer.publish(
            ENTRY,
            agents=["claude"],
            out_dir=tmp_path,
        )

    names = {p.name for p in written}
    # 5 capacidades, todas SKILL.md dentro de <name>/
    assert len(written) == 5
    assert names == {"SKILL.md"}
    assert (tmp_path / "athena_recall" / "SKILL.md").exists()
    assert (tmp_path / "zeus_plan" / "SKILL.md").exists()


def test_publish_opencode_writes_flat_md_named_by_tool(tmp_path):
    with patch(
        "thero.publish.installer.find_athena_script",
        return_value=Path("/repo/athena/athena.py"),
    ), patch(
        "thero.publish.installer.find_zeus_script",
        return_value=Path("/repo/zeus/zeus.py"),
    ):
        written = installer.publish(ENTRY, agents=["opencode"], out_dir=tmp_path)

    assert (tmp_path / "athena_recall.md").exists()
    assert any(p.name == "zeus_plan.md" for p in written)


def test_publish_skips_capability_when_script_unresolvable(tmp_path):
    # Zeus ausente → zeus_plan pulado; os demais ainda saem.
    with patch(
        "thero.publish.installer.find_athena_script",
        return_value=Path("/repo/athena/athena.py"),
    ), patch(
        "thero.publish.installer.find_zeus_script",
        return_value=None,
    ):
        written = installer.publish(
            ENTRY,
            agents=["claude"],
            out_dir=tmp_path,
        )

    names = {p.parent.name for p in written}
    assert "zeus_plan" not in names
    assert "athena_index" in names


def test_publish_embeds_resolved_command_path(tmp_path):
    with patch(
        "thero.publish.installer.find_athena_script",
        return_value=Path("/opt/athena/athena.py"),
    ), patch(
        "thero.publish.installer.find_zeus_script",
        return_value=Path("/opt/zeus/zeus.py"),
    ):
        installer.publish(ENTRY, agents=["claude"], out_dir=tmp_path)

    body = (tmp_path / "athena_index" / "SKILL.md").read_text(encoding="utf-8")
    # O installer embute o caminho via str(Path(...)), que é platform-native
    # (contra-barra no Windows). Compare com a mesma normalização para o
    # teste ser agnóstico de SO.
    assert str(Path("/opt/athena/athena.py")) in body
    assert "index" in body


def test_serve_command_mentions_mcp_flag():
    line = installer.serve_command(Path("/x/thero.py"))
    assert "--mcp" in line and "thero.py" in line
