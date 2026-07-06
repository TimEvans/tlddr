from pathlib import Path
from tlddr.cli import resolve_base, Paths


def test_resolve_base_prefers_flag_over_env(monkeypatch):
    monkeypatch.setenv("TLDDR_OUTPUT", "env-dir")
    assert resolve_base(Path("flag-dir")) == Path("flag-dir")


def test_resolve_base_uses_env_when_no_flag(monkeypatch):
    monkeypatch.setenv("TLDDR_OUTPUT", "env-dir")
    assert resolve_base(None) == Path("env-dir")


def test_paths_derives_layout_from_base():
    p = Paths(Path("/out/run1"))
    assert p.work == Path("/out/run1/.tlddr")
    assert p.extracted == Path("/out/run1/.tlddr/extracted")
    assert p.thumbnails == Path("/out/run1/.tlddr/thumbnails")
    assert p.nodes == Path("/out/run1/.tlddr/nodes")
    assert p.enrichment == Path("/out/run1/.tlddr/enrichment")
    assert p.sections == Path("/out/run1/.tlddr/sections.json")
    assert p.questions == Path("/out/run1/.tlddr/questions.json")
    assert p.claims == Path("/out/run1/.tlddr/claims.json")
    assert p.vault == Path("/out/run1/vault")
    assert p.report == Path("/out/run1/report")


def test_default_base_is_cwd(monkeypatch):
    monkeypatch.delenv("TLDDR_OUTPUT", raising=False)
    assert resolve_base(None) == Path(".")


def test_env_still_overrides_default(monkeypatch):
    monkeypatch.setenv("TLDDR_OUTPUT", "envbase")
    assert resolve_base(None) == Path("envbase")


def test_flag_beats_env(monkeypatch):
    monkeypatch.setenv("TLDDR_OUTPUT", "envbase")
    assert resolve_base(Path("flagbase")) == Path("flagbase")


def test_fresh_base_uses_hidden_tlddr(tmp_path):
    p = Paths(tmp_path)
    assert p.work == tmp_path / ".tlddr"
    assert p.extracted == tmp_path / ".tlddr" / "extracted"
    assert p.state_lock == tmp_path / ".tlddr" / "state_lock.json"
    assert p.config == tmp_path / "tlddr.toml"


def test_legacy_work_dir_is_honored_when_present(tmp_path):
    (tmp_path / "work").mkdir()
    assert Paths(tmp_path).work == tmp_path / "work"


def test_hidden_wins_when_both_present(tmp_path):
    (tmp_path / "work").mkdir()
    (tmp_path / ".tlddr").mkdir()
    assert Paths(tmp_path).work == tmp_path / ".tlddr"
