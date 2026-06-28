from tlddr.extract.base import ExtractContext
from tlddr.extract.pdf import extract
from tlddr.models import SignalType, ExtractMethod


def test_born_digital_pdf_has_text(tmp_path, born_digital_pdf):
    ctx = ExtractContext(asset_dir=tmp_path / "assets")
    doc = extract(born_digital_pdf, ctx)
    assert doc.signal_type is SignalType.BORN_DIGITAL_REPORT
    assert doc.pages[0].has_text_layer is True
    assert doc.pages[0].method is ExtractMethod.PYMUPDF_TEXT
    assert "cost benefit" in doc.content.lower()


def test_image_only_pdf_routes_to_vision_with_thumbnail(tmp_path, image_only_pdf):
    ctx = ExtractContext(asset_dir=tmp_path / "assets")
    doc = extract(image_only_pdf, ctx)
    assert doc.signal_type is SignalType.DRAWING
    assert doc.pages[0].has_text_layer is False
    assert doc.pages[0].method is ExtractMethod.VISION
    assert doc.pages[0].thumbnail is not None
    assert (tmp_path / "assets").exists()
    assert any("image-only" in w.lower() for w in doc.warnings)


def test_mixed_pdf_is_mixed(tmp_path, mixed_pdf):
    ctx = ExtractContext(asset_dir=tmp_path / "assets")
    doc = extract(mixed_pdf, ctx)
    assert doc.signal_type is SignalType.MIXED
    assert len(doc.pages) == 2
