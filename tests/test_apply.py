from __future__ import annotations

import json

import pytest

from thero import apply
from thero.shell_command import upsert_block, upsert_marked_block
from thero.settings import (
    COMMAND_MARKER_END,
    COMMAND_MARKER_START,
    ENV_MARKER_END,
    ENV_MARKER_START,
)


# ---- upsert_block generico (detecta os marcadores ja dentro do bloco) ----

def test_upsert_block_appends_when_absent():
    out = upsert_block("echo oi\n", ">>>\nblock\n<<<", ">>>", "<<<")
    assert out.startswith("echo oi")
    assert ">>>\nblock\n<<<" in out


def test_upsert_block_replaces_instead_of_duplicating():
    first = upsert_block("", ">>>\nA\n<<<", ">>>", "<<<")
    second = upsert_block(first, ">>>\nC\n<<<", ">>>", "<<<")
    assert second.count(">>>") == 1
    assert "C" in second and "A" not in second


def test_upsert_block_keeps_text_after_the_marker():
    existing = "antes\n>>>\nvelho\n<<<\ndepois\n"
    out = upsert_block(existing, ">>>\nnovo\n<<<", ">>>", "<<<")
    assert "antes" in out and "depois" in out
    assert "novo" in out and "velho" not in out


def test_upsert_block_does_not_cannibalize_other_marked_blocks():
    # dois pares de marcadores distintos no mesmo arquivo: trocar um par nao
    # pode engolir o outro (a busca por index(end) acha o fim do MESMO bloco).
    existing = ">>X\nalpha\n<<X\n>>Y\nbeta\n<<Y\n"
    out = upsert_block(existing, ">>X\nALPHA\n<<X", ">>X", "<<X")
    assert "ALPHA" in out and "alpha" not in out
    assert ">>Y\nbeta\n<<Y" in out
    out2 = upsert_block(out, ">>Y\nBETA\n<<Y", ">>Y", "<<Y")
    assert "BETA" in out2 and ">>X\nALPHA\n<<X" in out2


def test_marked_block_still_uses_the_command_markers():
    block = "%s\nfunction thero {}\n%s" % (COMMAND_MARKER_START,
                                           COMMAND_MARKER_END)
    out = upsert_marked_block("", block)
    assert COMMAND_MARKER_START in out and COMMAND_MARKER_END in out


# ---- claude settings.json ----

@pytest.fixture
def cfg():
    return {
        "providers": [
            {"id": "claude", "label": "Claude Code", "model": "sonnet",
             "authKind": "session", "authVar": "", "base": ""},
            {"id": "ollama", "label": "Ollama", "model": "llama3.2",
             "authKind": "local", "authVar": "",
             "base": "http://127.0.0.1:11434"},
        ],
        "agents": [
            {"id": "claude", "preset": "claude", "target": "claude",
             "provider": "claude", "model": "sonnet", "enabled": True},
        ],
        "routing": {"athena": "llama3.2", "sentinel": "qwen3-coder-next"},
    }


def test_apply_claude_sets_model_and_env_anthropic_model(tmp_path, cfg):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"autoUpdatesChannel": "latest"}),
                      encoding="utf-8")
    agent = apply.find_agent(cfg, "claude")
    out = apply.apply_claude(agent, cfg, target)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["model"] == "sonnet"
    assert data["env"]["ANTHROPIC_MODEL"] == "sonnet"
    assert data["autoUpdatesChannel"] == "latest"   # preservou o resto
    assert out["ok"] is True
    assert out["written"] == str(target)


def test_apply_claude_backs_up_before_touching(tmp_path, cfg):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"env": {"X": "1"}}), encoding="utf-8")
    apply.apply_claude(apply.find_agent(cfg, "claude"), cfg, target)
    backups = list(tmp_path.glob("settings.backup_*"))
    assert len(backups) == 1
    saved = json.loads(backups[0].read_text(encoding="utf-8"))
    assert saved["env"]["X"] == "1"


def test_apply_refuses_an_unparseable_file_and_leaves_it_alone(tmp_path, cfg):
    target = tmp_path / "settings.json"
    target.write_text("{ isto nao e json", encoding="utf-8")
    out = apply.apply_claude(apply.find_agent(cfg, "claude"), cfg, target)
    assert out["ok"] is False
    assert "nao fui" in out["msg"].lower() or "parse" in out["msg"].lower()
    assert target.read_text(encoding="utf-8") == "{ isto nao e json"
    assert list(tmp_path.glob("settings.backup_*")) == []
    assert out["backup"] == ""


def test_apply_claude_creates_env_without_clobbering_other_vars(tmp_path, cfg):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"env": {"ANTHROPIC_API_KEY": "kept"}}),
                      encoding="utf-8")
    apply.apply_claude(apply.find_agent(cfg, "claude"), cfg, target)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["env"]["ANTHROPIC_API_KEY"] == "kept"
    assert data["env"]["ANTHROPIC_MODEL"] == "sonnet"


def test_apply_claude_targets_the_agent_it_is_given(tmp_path, cfg):
    # A4: sem o `agent` em mao o escritor fixaria id "claude" e escreveria o
    # modelo do agente errado num segundo alvo "claude".
    cfg["agents"].append(dict(cfg["agents"][0], id="claude2",
                              target="claude", provider="ollama",
                              model="llama3.2"))
    target = tmp_path / "settings.json"
    target.write_text("{}", encoding="utf-8")
    second = apply.find_agent(cfg, "claude2")
    apply.apply_claude(second, cfg, target)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["model"] == "llama3.2"


# ---- opencode ----

def test_apply_opencode_writes_provider_slash_model(tmp_path, cfg):
    target = tmp_path / "opencode.json"
    target.write_text(json.dumps({"theme": "opencode"}), encoding="utf-8")
    agent = dict(cfg["agents"][0], preset="opencode", target="opencode",
                 provider="ollama", model="llama3.2")
    apply.apply_opencode(agent, cfg, target)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["model"] == "ollama/llama3.2"
    assert data["theme"] == "opencode"


# ---- codex config.toml ----

def test_apply_codex_rewrites_only_top_level_scalars(tmp_path, cfg):
    target = tmp_path / "config.toml"
    target.write_text(
        'model = "old"\nnotify = true\n\n[mcp_servers.x]\ncmd = "keep me"\n',
        encoding="utf-8",
    )
    agent = dict(cfg["agents"][0], target="codex", provider="openai",
                 model="gpt-5-codex")
    apply.apply_codex(agent, cfg, target)
    text = target.read_text(encoding="utf-8")
    assert 'model = "gpt-5-codex"' in text
    assert "notify = true" in text
    assert 'cmd = "keep me"' in text
    assert text.index("notify") < text.index("[mcp_servers")


def test_apply_codex_creates_the_key_when_the_file_has_none(tmp_path, cfg):
    target = tmp_path / "config.toml"
    target.write_text('[features]\nx = true\n', encoding="utf-8")
    agent = dict(cfg["agents"][0], target="codex", model="gpt-5-codex")
    apply.apply_codex(agent, cfg, target)
    text = target.read_text(encoding="utf-8")
    assert text.splitlines()[0].startswith("model")
    assert "[features]" in text


def test_apply_codex_writes_model_provider_only_when_the_table_exists(tmp_path,
                                                                      cfg):
    target = tmp_path / "config.toml"
    target.write_text('model = "old"\n\n[model_providers.deepseek]\n'
                      'base_url = "http://x"\n', encoding="utf-8")
    agent = dict(cfg["agents"][0], target="codex", provider="deepseek",
                 model="deepseek-chat")
    apply.apply_codex(agent, cfg, target)
    text = target.read_text(encoding="utf-8")
    assert 'model = "deepseek-chat"' in text
    assert 'model_provider = "deepseek"' in text
    assert "[model_providers.deepseek]" in text


def test_apply_codex_skips_model_provider_when_the_table_is_absent(tmp_path,
                                                                   cfg):
    target = tmp_path / "config.toml"
    target.write_text('model = "old"\nnotify = true\n', encoding="utf-8")
    agent = dict(cfg["agents"][0], target="codex", provider="ghost",
                 model="gpt-x")
    out = apply.apply_codex(agent, cfg, target)
    text = target.read_text(encoding="utf-8")
    assert 'model = "gpt-x"' in text
    assert "model_provider" not in text   # mesa inexistente quebraria o Codex
    assert "ghost" in out["msg"]          # o msg diz por que nao escreveu


# ---- $PROFILE (contrato real dos dois consumidores) ----

def test_profile_block_carries_both_consumer_contracts(cfg):
    block = apply.profile_env_block(cfg)
    assert "$env:ATHENA_OLLAMA_HOST" in block
    assert "$env:ATHENA_OLLAMA_MODEL" in block
    assert "$env:SENTINEL_OLLAMA_HOST" in block
    assert "$env:SENTINEL_OLLAMA_MODEL" in block
    # cada consumidor com o modelo que o usuario escolheu para ele -- os dois
    # padrao sao diferentes (Athena llama3.2, Sentinel qwen3-coder-next)
    assert '$env:ATHENA_OLLAMA_MODEL = "llama3.2"' in block
    assert '$env:SENTINEL_OLLAMA_MODEL = "qwen3-coder-next"' in block
    assert block.count("http://127.0.0.1:11434") == 2
    assert ENV_MARKER_START in block and ENV_MARKER_END in block


def test_profile_block_falls_back_to_each_consumers_own_default(cfg):
    cfg["routing"] = {}                       # usuario ainda nao escolheu
    block = apply.profile_env_block(cfg)
    assert '$env:ATHENA_OLLAMA_MODEL = "llama3.2"' in block
    assert '$env:SENTINEL_OLLAMA_MODEL = "qwen3-coder-next"' in block


def test_env_contracts_cover_exactly_the_declared_consumers():
    # duas listas de consumidores e a receita de uma tela que escreve no
    # arquivo errado: isto garante que apply.ENV_CONTRACTS e
    # providers.CONSUMERS nunca divergem.
    from thero import providers

    assert set(apply.ENV_CONTRACTS) == set(providers.CONSUMERS)


def test_apply_profile_is_idempotent(tmp_path, cfg):
    profile = tmp_path / "Microsoft.PowerShell_profile.ps1"
    profile.write_text("function foo {}\n", encoding="utf-8")
    apply.apply_profile(cfg, profile)
    apply.apply_profile(cfg, profile)
    text = profile.read_text(encoding="utf-8")
    assert text.count(ENV_MARKER_START) == 1
    assert "function foo" in text


def test_apply_profile_reports_missing_profile_without_crashing(cfg):
    # A8: Path(None) levanta TypeError; a validacao tem de vir antes.
    out = apply.apply_profile(cfg, None)
    assert out["ok"] is False
    assert "profile" in out["msg"].lower()


def test_profile_env_block_refuses_a_remote_ollama_base(cfg):
    # A3: base remota escolhida na GUI nunca pode virar $PROFILE.
    for provider in cfg["providers"]:
        if provider.get("id") == "ollama":
            provider["base"] = "http://10.0.0.5:11434"
    with pytest.raises(ValueError):
        apply.profile_env_block(cfg)


def test_apply_profile_refuses_remote_base_and_writes_nothing(tmp_path, cfg):
    # A3 + credencial: base remota com userinfo nao escreve, nao faz backup,
    # e nao ecoa a credencial no msg.
    for provider in cfg["providers"]:
        if provider.get("id") == "ollama":
            provider["base"] = "http://user:secret@evil.example:11434"
    profile = tmp_path / "profile.ps1"
    profile.write_text("function foo {}\n", encoding="utf-8")
    out = apply.apply_profile(cfg, profile)
    assert out["ok"] is False
    assert "loopback" in out["msg"].lower()
    assert profile.read_text(encoding="utf-8") == "function foo {}\n"
    assert list(tmp_path.glob("profile.backup_*")) == []
    assert "secret" not in out["msg"]
    assert "user" not in out["msg"]


def test_apply_preserves_a_cp1252_profile_byte_for_byte(tmp_path, cfg):
    # A7: um $PROFILE salvo como cp1252 (PowerShell 5.1) nao pode virar
    # U+FFFD escrito de volta -- merge preservando o encoding de origem.
    profile = tmp_path / "profile.ps1"
    profile.write_bytes("# caf\xe9 latino\nfunction foo {}\n".encode("cp1252"))
    out = apply.apply_profile(cfg, profile)
    assert out["ok"] is True
    data = profile.read_bytes()
    assert b"caf\xe9" in data
    assert b"\xef\xbf\xbd" not in data
    assert ENV_MARKER_START.encode() in data


def test_apply_refuses_an_undecodable_file_and_writes_nothing(tmp_path, cfg):
    # A7: nem utf-8 nem cp1252 -> recusa total, arquivo intocado, sem backup.
    target = tmp_path / "settings.json"
    junk = b'{"a": 1}\n\x81'
    target.write_bytes(junk)
    out = apply.apply_claude(apply.find_agent(cfg, "claude"), cfg, target)
    assert out["ok"] is False
    assert target.read_bytes() == junk
    assert list(tmp_path.glob("settings.backup_*")) == []
    assert out["backup"] == ""


# ---- despacho / record-only / ponte ----

def test_apply_never_uses_print_on_the_bridge_channel(tmp_path, cfg, capsys):
    target = tmp_path / "settings.json"
    target.write_text("{}", encoding="utf-8")
    apply.apply_agent(cfg["agents"][0], cfg, {"claude": target})
    agent = dict(cfg["agents"][0], id="env", target="profile")
    apply.apply_agent(agent, cfg, {}, tmp_path / "profile.ps1")
    assert capsys.readouterr().out == ""


def test_record_only_targets_write_nothing(tmp_path, cfg):
    target = tmp_path / "settings.json"
    before = "{}"
    target.write_text(before, encoding="utf-8")
    agent = dict(cfg["agents"][0], target="none", preset="qoder")
    out = apply.apply_agent(agent, cfg, {"claude": target})
    assert out["ok"] is True
    assert out["writes"] is False
    assert target.read_text(encoding="utf-8") == before


def test_record_only_result_carries_id_and_target(tmp_path, cfg):
    # A5: a ponte casa os resultados por `id`; sem id o recod-only nunca daria
    # match e o status ficaria "pendente" para sempre.
    agent = dict(cfg["agents"][0], id="cursor", target="none", preset="cursor")
    out = apply.apply_agent(agent, cfg, {})
    assert out["id"] == "cursor"
    assert out["target"] == "none"


def test_apply_all_reports_enabled_and_skips_disabled(tmp_path, cfg):
    cfg["agents"].append(dict(cfg["agents"][0], id="x", enabled=False))
    paths = {"claude": tmp_path / "settings.json"}
    paths["claude"].write_text("{}", encoding="utf-8")
    results = apply.apply_all(cfg, paths)
    assert len(results) == 1
    assert results[0]["id"] == "claude"


def test_default_paths_has_no_profile_key():
    # A9: localizar a $PROFILE exige rodar PowerShell -- default_paths nao faz
    # subprocess, entao nao finge um contrato que nao entrega.
    assert "profile" not in apply.default_paths()


def test_apply_agent_resolves_profile_from_paths_key(tmp_path, cfg):
    profile = tmp_path / "profile.ps1"
    agent = {"id": "env", "target": "profile", "label": "Perfil"}
    out = apply.apply_agent(agent, cfg, {"profile": profile})
    assert out["ok"] is True
    assert out["target"] == "profile"
    assert ENV_MARKER_START in profile.read_text(encoding="utf-8")


def test_apply_returns_the_backup_name_when_overwriting(tmp_path, cfg):
    target = tmp_path / "settings.json"
    target.write_text("{}", encoding="utf-8")
    out = apply.apply_claude(apply.find_agent(cfg, "claude"), cfg, target)
    assert out["backup"].startswith("settings.backup_")
    assert out["backup"] in out["msg"]     # msg menciona o que foi tocado


def test_apply_backup_is_empty_when_no_prior_file(tmp_path, cfg):
    target = tmp_path / "settings.json"
    out = apply.apply_claude(apply.find_agent(cfg, "claude"), cfg, target)
    assert out["backup"] == ""             # arquivo novo: nao houve backup
    assert "settings.json" in out["msg"]
