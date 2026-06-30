import json
from pathlib import Path
from tlddr.cli import understand_slice, understand_commit, understand_render, understand_sections
from tlddr.models import ExtractedDoc, SignalType


def _write_doc(d: Path, id: str):
    doc = ExtractedDoc(
        id=id, source_path=f"/x/{id}.pdf", source_sha256="a",
        signal_type=SignalType.BORN_DIGITAL_REPORT, raw_title=f"{id} title",
        content="--- page 1 ---\nbody", pages=[], warnings=[], extractor="docx",
    )
    (d / f"{id}.json").write_text(doc.model_dump_json())


def test_slice_then_commit_then_render(tmp_path):
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    _write_doc(extracted, "a6")
    _write_doc(extracted, "a3")

    # slice
    s = understand_slice(extracted, "a6")
    assert "a6 title" in s and "body" in s

    # commit (enrichment references a real node a3 and a ghost)
    enrichment = {
        "extracted_id": "a6", "doc_type": "cba", "description": "A CBA.",
        "confidence_interpretation": "high",
        "related": [{"target": "a3", "relation": "corroborates", "rationale": "x"},
                    {"target": "ghost", "relation": "references", "rationale": "y"}],
        "questions": [],
    }
    ep = tmp_path / "a6.enrichment.json"
    ep.write_text(json.dumps(enrichment))
    work = tmp_path / "work"
    node = understand_commit(ep, extracted, work)
    assert node.id == "a6"
    assert [e.target for e in node.related] == ["a3"]          # ghost dropped
    assert (work / "nodes" / "a6.json").exists()

    # render
    vault = tmp_path / "vault"
    understand_render(work, vault)
    assert (vault / "a6.md").exists()
    assert (vault / "_index.md").exists()
    assert (vault / "_triage.md").exists()
    assert "[[a3]]" in (vault / "a6.md").read_text()
    assert "a6" in (vault / "_index.md").read_text()


def test_commit_is_idempotent_on_questions(tmp_path):
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    _write_doc(extracted, "a6")
    enrichment = {
        "extracted_id": "a6", "doc_type": "cba", "description": "d",
        "confidence_interpretation": "high", "related": [],
        "questions": [{"id": "q-1", "question": "Which scenario?"}],
    }
    ep = tmp_path / "a6.enrichment.json"
    ep.write_text(json.dumps(enrichment))
    work = tmp_path / "work"
    understand_commit(ep, extracted, work)
    understand_commit(ep, extracted, work)  # re-commit the same node
    questions = json.loads((work / "questions.json").read_text())
    assert len(questions) == 1  # not duplicated on re-run


def test_commit_validates_section_tags_against_spec(tmp_path):
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    _write_doc(extracted, "a6")

    sections = tmp_path / "sections.json"
    sections.write_text(json.dumps([
        {"id": "financial-model", "title": "Financial Model"},
    ]))

    enrichment = {
        "extracted_id": "a6", "doc_type": "cba", "description": "d",
        "confidence_interpretation": "high", "related": [],
        "report_sections": ["financial-model", "ghost-section"],
        "questions": [],
    }
    ep = tmp_path / "a6.enrichment.json"
    ep.write_text(json.dumps(enrichment))
    work = tmp_path / "work"

    node = understand_commit(ep, extracted, work, sections)
    assert node.report_sections == ["financial-model"]   # ghost-section dropped


def test_sections_command_prints_and_validates(tmp_path, capsys):
    p = tmp_path / "sections.json"
    p.write_text(json.dumps([
        {"id": "key-technology", "title": "Key Technology"},
        {"id": "key-technology-type-1", "title": "Technology type 1",
         "parent": "key-technology"},
    ]))
    sections = understand_sections(p)
    assert [s.id for s in sections] == ["key-technology", "key-technology-type-1"]
    out = capsys.readouterr().out
    assert "key-technology — Key Technology" in out
    assert "  key-technology-type-1 — Technology type 1" in out  # indented child
