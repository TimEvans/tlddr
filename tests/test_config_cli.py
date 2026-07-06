import json
from pathlib import Path
from tlddr.cli import main
from tlddr.config import read_toml


def test_config_cli_writes_toml_and_state(tmp_path, capsys):
    corpus = tmp_path / "corpus"; corpus.mkdir(); (corpus / "a.txt").write_text("x")
    base = tmp_path / "run"
    rc = main(["config", "--preset", "careful", "--corpus", str(corpus),
               "--output", str(base), "--model", "opus"])
    assert rc == 0
    cfg = read_toml(base / "tlddr.toml")
    assert cfg["preset"] == "careful" and cfg["corpus"] == str(corpus)
    state = json.loads((base / ".tlddr" / "state_lock.json").read_text())
    assert state["config"]["model"] == "opus"
    assert state["corpus_fingerprint"].startswith("sha256:")
