from tlddr.extract.base import ExtractContext
from tlddr.extract.kmz import extract
from tlddr.models import SignalType, ExtractMethod


def test_kmz_extracts_identity(tmp_path, simple_kmz):
    ctx = ExtractContext(asset_dir=tmp_path / "assets")
    doc = extract(simple_kmz, ctx)
    assert doc.signal_type is SignalType.GEOSPATIAL
    assert "Indicative REZ Boundaries 2025" in doc.content
    assert "2 placemarks" in doc.content  # two placemarks counted, not satisfiable by the year in the name
    assert doc.pages[0].method is ExtractMethod.KMZ_IDENTITY
    assert doc.pages[0].has_text_layer is False
