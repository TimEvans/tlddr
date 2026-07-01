from pathlib import Path
from tlddr.extract.base import ExtractContext
from tlddr.extract import router
from tlddr.models import SignalType, ExtractedDoc


def fake_extractor(path: Path, ctx: ExtractContext) -> ExtractedDoc:
    return ExtractedDoc(
        id="fake", source_path=str(path), source_sha256="x",
        signal_type=SignalType.BORN_DIGITAL_REPORT, raw_title="fake",
        content="", extractor="fake",
    )


def test_route_dispatches_by_suffix(tmp_path, monkeypatch):
    monkeypatch.setitem(router.EXTRACTORS, ".pdf", fake_extractor)
    ctx = ExtractContext(asset_dir=tmp_path)
    result = router.route(tmp_path / "doc.PDF", ctx)
    assert result.extractor == "fake"


def test_route_unknown_extension_returns_unknown_with_warning(tmp_path):
    ctx = ExtractContext(asset_dir=tmp_path)
    f = tmp_path / "thing.zip"
    f.write_bytes(b"x")
    result = router.route(f, ctx)
    assert result.signal_type is SignalType.UNKNOWN
    assert any("no extractor" in w.lower() for w in result.warnings)


def test_route_dispatches_htm_and_html_to_html_extractor(tmp_path):
    ctx = ExtractContext(asset_dir=tmp_path)
    for name in ("doc.htm", "doc.HTML"):
        f = tmp_path / name
        f.write_bytes(b"<html><body><p>hello world content</p></body></html>")
        result = router.route(f, ctx)
        assert result.extractor == "html"
        assert "hello world content" in result.content
