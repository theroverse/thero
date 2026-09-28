from thero import presets


def test_provider_presets_have_the_fields_the_ui_reads():
    for p in presets.PROVIDER_PRESETS:
        assert set(["id", "name", "kind", "authKind", "base",
                    "transport", "models"]) <= set(p)
        assert p["authKind"] in ("session", "apikey", "local")


def test_agent_presets_declare_whether_they_actually_write():
    for a in presets.AGENT_PRESETS:
        assert "writes" in a and "cfg" in a
    # verificados nesta maquina: qoder e vscode NAO recebem config por arquivo
    assert presets.agent_preset("qoder")["writes"] is False
    assert presets.agent_preset("vscode")["writes"] is False
    assert presets.agent_preset("claude")["writes"] is True


def test_default_providers_are_prefilled_but_editable():
    provs = presets.default_providers()
    ids = [p["id"] for p in provs]
    assert "claude" in ids and "ollama" in ids and "openai" in ids
    for p in provs:
        assert set(["id", "label", "preset", "authKind", "base", "authVar",
                    "transport", "model", "enabled", "roles", "authState",
                    "lastCheck"]) <= set(p)


def test_default_routing_starts_in_zeus_mode():
    r = presets.default_routing()
    assert r["mode"] == "zeus"
    assert r["athena"] and r["sentinel"] and r["fallback"]
