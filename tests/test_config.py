from pathlib import Path
from tlddr.config import PRESETS, resolve_config, read_toml, write_toml


def test_presets_defined():
    assert PRESETS["quick"]["model"] == "sonnet"
    assert PRESETS["quick"]["interaction"] == "autonomous"
    assert PRESETS["careful"]["model"] == "opus"
    assert PRESETS["careful"]["interaction"] == "guided"


def test_preset_supplies_defaults():
    cfg = resolve_config("quick", {}, {})
    assert cfg["model"] == "sonnet" and cfg["effort"] == "medium"


def test_override_beats_preset():
    cfg = resolve_config("quick", {"model": "opus"}, {})
    assert cfg["model"] == "opus" and cfg["interaction"] == "autonomous"  # only model overridden


def test_toml_beats_preset_but_flag_beats_toml():
    toml_cfg = {"overrides": {"model": "opus"}}
    assert resolve_config("quick", {}, toml_cfg)["model"] == "opus"          # toml > preset
    assert resolve_config("quick", {"model": "sonnet"}, toml_cfg)["model"] == "sonnet"  # flag > toml


def test_toml_round_trip(tmp_path):
    p = tmp_path / "tlddr.toml"
    write_toml(p, {"corpus": "docs/x", "output": "chevron", "preset": "careful",
                   "overrides": {"model": "opus", "benchmark": True}})
    back = read_toml(p)
    assert back["corpus"] == "docs/x" and back["preset"] == "careful"
    assert back["overrides"]["model"] == "opus" and back["overrides"]["benchmark"] is True


def test_read_toml_absent_is_empty(tmp_path):
    assert read_toml(tmp_path / "none.toml") == {}
