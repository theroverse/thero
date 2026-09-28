import json
from pathlib import Path

import pytest

from thero import config, presets
from thero.cli import main, parse_args


def set_argv(monkeypatch, *args):
    monkeypatch.setattr("sys.argv", ["thero.py", *args])


@pytest.fixture
def store(tmp_path, monkeypatch):
    """config_path() resolve USERPROFILE/HOME NA CHAMADA (config.py:24-30),
    entao remapear as duas variaveis isola o store sem tocar no da maquina.
    Retorna o caminho do config.json vazio (ainda nao existe)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    return tmp_path / ".thero" / "config.json"


def cli(monkeypatch, *args):
    # O entry path e irrelevante neste ramo: o despacho do --config vem antes
    # de qualquer leitura de arquivo do instalador (cli.py:490-498).
    set_argv(monkeypatch, *args)
    main(Path("thero.py"))


# ——— defaults ———

def test_parse_args_has_the_three_config_flags(monkeypatch):
    set_argv(monkeypatch)
    args = parse_args()
    assert args.config is None            # None != []: "ausente" vs "--config" solto
    assert args.get is None
    assert args.list is False


def test_default_limits_are_the_owner_recommendation():
    assert presets.default_limits() == {"local": 4, "standard": 3, "premium": 2}
    assert presets.LIMITS == ("local", "standard", "premium")


def test_default_config_carries_limits_next_to_routing():
    cfg = config.default_config()
    assert cfg["limits"] == presets.default_limits()
    # Subconjunto, nao igualdade: o plano 2026-09-28-registro-de-equipe vai
    # acrescentar a chave `team` no mesmo dict, e uma igualdade exata faria as
    # duas tasks se canibalizarem por uma linha de teste.
    assert {"version", "providers", "agents", "routing", "preferences",
            "limits"} <= set(cfg)


# ——— escrever ———

def test_cli_config_set_writes_the_dotted_key(store, monkeypatch, capsys):
    cli(monkeypatch, "--config", "limits.local=6")
    assert "limits.local=6" in capsys.readouterr().out
    assert config.load(store)["limits"]["local"] == 6


def test_cli_config_write_keeps_the_other_sections(store, monkeypatch):
    cfg = config.default_config()
    cfg["providers"][0]["model"] = "opus"
    config.save(cfg, path=store)
    cli(monkeypatch, "--config", "limits.premium=1")
    after = config.load(store)
    assert after["limits"]["premium"] == 1
    assert after["providers"][0]["model"] == "opus"      # read-modify-write


def test_cli_and_the_bridge_read_the_same_bytes(store, monkeypatch, capsys):
    # O outro caminho (a ponte, Task 8 Step 4E) escreve via config.save; a CLI
    # le do disco na hora. Sem cache entre processos: e a regra do dono.
    cfg = config.default_config()
    cfg["limits"]["standard"] = 5
    config.save(cfg, path=store)
    cli(monkeypatch, "--config", "--get", "limits.standard")
    assert capsys.readouterr().out.strip() == "5"


# ——— ler ———

def test_cli_config_get_prints_only_the_value(store, monkeypatch, capsys):
    cli(monkeypatch, "--config", "--get", "limits.local")
    out = capsys.readouterr().out
    assert out.strip() == "4"                       # nada de banner, nada de prefixo
    assert "Engineering Stack" not in out


def test_cli_config_get_is_the_value_the_file_has(store, monkeypatch, capsys):
    cfg = config.default_config()
    cfg["limits"]["local"] = 7
    config.save(cfg, path=store)
    cli(monkeypatch, "--config", "--get", "limits.local")
    assert capsys.readouterr().out.strip() == "7"


def test_cli_config_get_of_an_unknown_key_is_silent_and_exits_1(
        store, monkeypatch, capsys):
    # git config --get: ausencia = silencio no stdout + exit 1. O script que
    # chama precisa distinguir "4 gravado" de "nada gravado ainda".
    set_argv(monkeypatch, "--config", "--get", "limits.inexistente")
    with pytest.raises(SystemExit) as boom:
        main(Path("thero.py"))
    assert boom.value.code == 1
    assert capsys.readouterr().out.strip() == ""


def test_cli_config_lists_dotted_scalar_pairs_sorted(store, monkeypatch, capsys):
    cli(monkeypatch, "--config", "--list")
    lines = [ln for ln in capsys.readouterr().out.splitlines() if "=" in ln]
    assert "limits.local=4" in lines
    assert "routing.mode=zeus" in lines
    assert lines == sorted(lines)
    assert not any(ln.startswith("providers") or ln.startswith("agents")
                   for ln in lines)


# ——— recusas ———

def test_cli_config_with_no_argument_prints_usage_and_exits_2(store, monkeypatch):
    set_argv(monkeypatch, "--config")
    with pytest.raises(SystemExit) as boom:
        main(Path("thero.py"))
    assert boom.value.code == 2


def test_cli_config_refuses_any_path_that_is_not_limits(store, monkeypatch):
    set_argv(monkeypatch, "--config", "routing.athena=llama3.2")
    with pytest.raises(SystemExit) as boom:
        main(Path("thero.py"))
    assert boom.value.code == 2
    assert not store.exists()                       # nao gravou nada


def test_cli_config_refuses_a_value_that_is_not_a_positive_int(store, monkeypatch):
    for bad in ("0", "-2", "muitos", "4.5"):
        set_argv(monkeypatch, "--config", "limits.local=%s" % bad)
        with pytest.raises(SystemExit):
            main(Path("thero.py"))
    assert config.load(store)["limits"]["local"] == 4


def test_cli_config_refuses_a_credential_shaped_key_even_under_limits(
        store, monkeypatch):
    # O dono: "sem nunca guardar nada que seja valor de chave de API".
    # LIMITS e lista fechada de tres nomes, entao isto e recusado por
    # construcao -- o teste impede que alguem abra a lista no futuro.
    set_argv(monkeypatch, "--config", "limits.apikey=sk-SEGREDO")
    with pytest.raises(SystemExit):
        main(Path("thero.py"))
    assert "apikey" not in config.load(store)["limits"]


def test_cli_config_never_introduces_a_bom(store, monkeypatch):
    cli(monkeypatch, "--config", "limits.local=2")
    assert store.read_bytes()[:3] != b"\xef\xbb\xbf"
    json.loads(store.read_text(encoding="utf-8"))   # strict: o BOM mataria aqui
