from tlddr.extract.base import ExtractContext
from tlddr.extract.docx import extract
from tlddr.models import SignalType


def test_docx_extracts_markdown(tmp_path, simple_docx):
    ctx = ExtractContext(asset_dir=tmp_path / "assets")
    doc = extract(simple_docx, ctx)
    assert doc.signal_type is SignalType.BORN_DIGITAL_REPORT
    assert doc.extractor == "docx"
    assert "Business Case" in doc.content
    assert "value" in doc.content
    assert doc.pages == []


def test_docx_drops_embedded_images_and_counts_them(tmp_path, docx_with_image):
    ctx = ExtractContext(asset_dir=tmp_path / "assets")
    doc = extract(docx_with_image, ctx)
    # images are dropped, not inlined as base64 bloat
    assert "data:image" not in doc.content
    # real prose is preserved
    assert "Real text body here" in doc.content
    assert "More text after the image" in doc.content
    # image presence is reported as provenance (identity, not pixels)
    image_warnings = [w for w in doc.warnings if "embedded image" in w]
    assert image_warnings, "expected an embedded-image provenance warning"
    assert "2" in image_warnings[0]


def test_docx_without_images_has_no_image_warning(tmp_path, simple_docx):
    ctx = ExtractContext(asset_dir=tmp_path / "assets")
    doc = extract(simple_docx, ctx)
    assert not [w for w in doc.warnings if "embedded image" in w]
