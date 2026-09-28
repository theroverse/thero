import json

from thero import config


def test_default_config_shape():
    cfg = config.default_config()
    assert cfg["version"] == config.CONFIG_VERSION
    assert cfg["providers"] and cfg["agents"]
    assert set(cfg["routing"]) == {"mode", "athena", "sentinel", "fallback"}
    assert cfg["preferences"] == {"scope": "global"}


def test_load_missing_file_returns_defaults(tmp_path):
    assert config.load(tmp_path / "config.json") == config.default_config()


def test_load_corrupt_file_returns_defaults_instead_of_crashing(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{ isto nao e json", encoding="utf-8")
    assert config.load(p)["version"] == config.CONFIG_VERSION


def test_save_then_load_roundtrip_keeps_accents(tmp_path):
    p = tmp_path / "config.json"
    cfg = config.default_config()
    cfg["providers"][0]["label"] = "Ômega — local"
    config.save(cfg, path=p)
    assert config.load(p)["providers"][0]["label"] == "Ômega — local"


def test_save_writes_no_bom(tmp_path):
    # memoria: config JSON com BOM quebra json.loads estrito no Windows
    p = tmp_path / "config.json"
    config.save(config.default_config(), path=p)
    assert not p.read_bytes().startswith(b"\xef\xbb\xbf")
    json.loads(p.read_text(encoding="utf-8"))  # nao pode lancar erro


def test_load_tolerates_a_bom_on_disk(tmp_path):
    p = tmp_path / "config.json"
    p.write_bytes(b"\xef\xbb\xbf" + b'{"version": 1}')
    assert config.load(p)["version"] == 1


def test_load_keeps_user_choices_and_fills_new_keys(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"version": 1, "providers": [], "novo": 7}),
                 encoding="utf-8")
    cfg = config.load(p)
    assert cfg["providers"] == []                  # escolha do usuario vencem
    assert cfg["novo"] == 7                         # chave futura preservada
    assert "agents" in cfg and "routing" in cfg     # faltante vem do default


def test_config_path_follows_a_patched_home(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    assert config.config_path() == tmp_path / ".thero" / "config.json"


def test_is_first_run(tmp_path):
    p = tmp_path / "config.json"
    assert config.is_first_run(p) is True
    config.save(config.default_config(), path=p)
    assert config.is_first_run(p) is False
