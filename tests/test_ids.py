from pathlib import Path
from tlddr.ids import doc_id, sha256_file


def test_doc_id_is_deterministic_slug():
    assert doc_id(Path("/x/A6 Cost-Benefit Analysis.pdf")) == "a6-cost-benefit-analysis"


def test_doc_id_collapses_punctuation_and_spaces():
    assert doc_id(Path("/x/aemo---gis (2025).kmz")) == "aemo-gis-2025"


def test_sha256_file_matches_known_value(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"hello")
    # sha256 of b"hello"
    assert sha256_file(f) == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
