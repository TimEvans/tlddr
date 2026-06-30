from tlddr.draft.pages import citable_pages, page_text
from tlddr.models import ExtractedDoc, PageProvenance, SignalType, ExtractMethod


def _pdf():
    return ExtractedDoc(
        id="p1", source_path="/x/p1.pdf", source_sha256="a",
        signal_type=SignalType.MIXED, raw_title="P1",
        content="--- page 1 ---\nalpha text\n\n--- page 3 ---\ngamma text",
        pages=[
            PageProvenance(page=1, method=ExtractMethod.PYMUPDF_TEXT, has_text_layer=True),
            PageProvenance(page=2, method=ExtractMethod.VISION, has_text_layer=False),
            PageProvenance(page=3, method=ExtractMethod.PYMUPDF_TEXT, has_text_layer=True),
        ],
        extractor="pdf",
    )


def _xlsx():
    return ExtractedDoc(
        id="x1", source_path="/x/x1.xlsx", source_sha256="a",
        signal_type=SignalType.SPREADSHEET, raw_title="X1",
        content="--- sheet: Costs ---\na | b\n\n--- sheet: Yield ---\nc | d",
        pages=[
            PageProvenance(page=1, method=ExtractMethod.OPENPYXL_XLSX, has_text_layer=True),
            PageProvenance(page=2, method=ExtractMethod.OPENPYXL_XLSX, has_text_layer=True),
        ],
        extractor="xlsx",
    )


def _docx():
    return ExtractedDoc(
        id="d1", source_path="/x/d1.docx", source_sha256="a",
        signal_type=SignalType.BORN_DIGITAL_REPORT, raw_title="D1",
        content="whole docx body, no page markers", pages=[], extractor="docx",
    )


def test_pdf_citable_pages_are_text_bearing_only():
    assert citable_pages(_pdf()) == {1, 3}            # page 2 is image-only, not citable
    assert page_text(_pdf(), 1) == "alpha text"
    assert page_text(_pdf(), 3) == "gamma text"
    assert page_text(_pdf(), 2) is None               # image-only
    assert page_text(_pdf(), 9) is None               # out of range


def test_xlsx_pages_are_sheet_ordinals():
    assert citable_pages(_xlsx()) == {1, 2}
    assert page_text(_xlsx(), 1) == "a | b"
    assert page_text(_xlsx(), 2) == "c | d"


def test_docx_has_single_synthetic_page():
    assert citable_pages(_docx()) == {1}
    assert page_text(_docx(), 1) == "whole docx body, no page markers"
    assert page_text(_docx(), 2) is None
