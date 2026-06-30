import json
import pytest
from pathlib import Path
from tlddr.understand.sections import load_sections, section_ids, validate_section_tags
from tlddr.models import Section


def _write(tmp_path: Path, data) -> Path:
    p = tmp_path / "sections.json"
    p.write_text(json.dumps(data))
    return p


def test_load_sections_preserves_fields_and_parent(tmp_path):
    p = _write(tmp_path, [
        {"id": "permitting-environmental", "title": "Permitting and Environmental review"},
        {"id": "key-technology", "title": "Key Technology"},
        {"id": "key-technology-type-1", "title": "Technology type 1", "parent": "key-technology"},
    ])
    sections = load_sections(p)
    assert [s.id for s in sections] == [
        "permitting-environmental", "key-technology", "key-technology-type-1"]
    assert sections[2].parent == "key-technology"
    assert sections[0].parent is None


def test_load_sections_rejects_duplicate_ids(tmp_path):
    p = _write(tmp_path, [
        {"id": "a", "title": "A"},
        {"id": "a", "title": "A again"},
    ])
    with pytest.raises(ValueError, match="duplicate"):
        load_sections(p)


def test_load_sections_rejects_unknown_parent(tmp_path):
    p = _write(tmp_path, [{"id": "child", "title": "Child", "parent": "ghost"}])
    with pytest.raises(ValueError, match="parent"):
        load_sections(p)


def test_section_ids_returns_the_id_set():
    sections = [Section(id="a", title="A"), Section(id="b", title="B")]
    assert section_ids(sections) == {"a", "b"}


def test_validate_section_tags_keeps_known_drops_unknown_dedupes():
    known = {"a", "b", "c"}
    valid, dropped = validate_section_tags(["b", "ghost", "a", "b"], known)
    assert valid == ["b", "a"]          # known, unique, in order
    assert dropped == ["ghost"]         # unknown reported once
