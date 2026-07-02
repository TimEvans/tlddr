from pathlib import Path
from tlddr.cli import resolve_base, Paths


def test_resolve_base_prefers_flag_over_env(monkeypatch):
    monkeypatch.setenv("TLDDR_OUTPUT", "env-dir")
    assert resolve_base(Path("flag-dir")) == Path("flag-dir")


def test_resolve_base_uses_env_when_no_flag(monkeypatch):
    monkeypatch.setenv("TLDDR_OUTPUT", "env-dir")
    assert resolve_base(None) == Path("env-dir")


def test_resolve_base_defaults_to_dot_tlddr(monkeypatch):
    monkeypatch.delenv("TLDDR_OUTPUT", raising=False)
    assert resolve_base(None) == Path(".tlddr")


def test_paths_derives_layout_from_base():
    p = Paths(Path("/out/run1"))
    assert p.work == Path("/out/run1/work")
    assert p.extracted == Path("/out/run1/work/extracted")
    assert p.thumbnails == Path("/out/run1/work/thumbnails")
    assert p.nodes == Path("/out/run1/work/nodes")
    assert p.enrichment == Path("/out/run1/work/enrichment")
    assert p.sections == Path("/out/run1/work/sections.json")
    assert p.questions == Path("/out/run1/work/questions.json")
    assert p.claims == Path("/out/run1/work/claims.json")
    assert p.vault == Path("/out/run1/vault")
    assert p.report == Path("/out/run1/report")
