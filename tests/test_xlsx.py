from tlddr.extract.base import ExtractContext
from tlddr.extract.xlsx import extract
from tlddr.models import SignalType, ExtractMethod


def test_xlsx_dumps_sheet_content(tmp_path, simple_xlsx):
    ctx = ExtractContext(asset_dir=tmp_path / "assets")
    doc = extract(simple_xlsx, ctx)
    assert doc.signal_type is SignalType.SPREADSHEET
    assert "Region" in doc.content and "Capacity" in doc.content
    assert "NSW" in doc.content
    assert doc.pages[0].method is ExtractMethod.OPENPYXL_XLSX


def test_xlsx_warns_on_merged_cells(tmp_path, messy_xlsx):
    ctx = ExtractContext(asset_dir=tmp_path / "assets")
    doc = extract(messy_xlsx, ctx)
    assert any("merged" in w.lower() for w in doc.warnings)
