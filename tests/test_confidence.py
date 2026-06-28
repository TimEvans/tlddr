from tlddr.understand.confidence import extraction_confidence
from tlddr.models import ExtractedDoc, PageProvenance, SignalType, ExtractMethod, Confidence


def _doc(**kw):
    base = dict(
        id="d", source_path="/x", source_sha256="a",
        signal_type=SignalType.BORN_DIGITAL_REPORT, raw_title="t",
        content="", pages=[], warnings=[], extractor="pdf",
    )
    base.update(kw)
    return ExtractedDoc(**base)


def _pages(n_text, n_image):
    pages = [PageProvenance(page=i + 1, method=ExtractMethod.PYMUPDF_TEXT, has_text_layer=True)
             for i in range(n_text)]
    pages += [PageProvenance(page=n_text + i + 1, method=ExtractMethod.VISION, has_text_layer=False)
              for i in range(n_image)]
    return pages


def test_all_text_pdf_is_high():
    assert extraction_confidence(_doc(pages=_pages(10, 0))) is Confidence.HIGH


def test_one_image_cover_in_long_doc_stays_high():
    assert extraction_confidence(_doc(signal_type=SignalType.MIXED, pages=_pages(114, 1))) is Confidence.HIGH


def test_mostly_image_doc_is_low():
    assert extraction_confidence(_doc(signal_type=SignalType.DRAWING, pages=_pages(0, 5))) is Confidence.LOW


def test_half_image_is_medium():
    assert extraction_confidence(_doc(signal_type=SignalType.MIXED, pages=_pages(5, 5))) is Confidence.MEDIUM


def test_geospatial_identity_is_high():
    assert extraction_confidence(_doc(signal_type=SignalType.GEOSPATIAL, pages=[])) is Confidence.HIGH


def test_truncated_spreadsheet_is_medium():
    doc = _doc(signal_type=SignalType.SPREADSHEET, warnings=["sheet 'X' truncated at 200 rows"])
    assert extraction_confidence(doc) is Confidence.MEDIUM


def test_clean_docx_is_high():
    # docx has no pages; faithful text+tables -> high
    assert extraction_confidence(_doc(signal_type=SignalType.BORN_DIGITAL_REPORT, extractor="docx", pages=[])) is Confidence.HIGH
