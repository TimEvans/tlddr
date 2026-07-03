import json
from pathlib import Path
from tlddr.cli import main
from tlddr.models import Question


def _work_with_questions(tmp: Path, questions: list[dict]) -> Path:
    base = tmp / "out"
    work = base / "work"
    nodes = work / "nodes"
    nodes.mkdir(parents=True)
    (work / "questions.json").write_text(json.dumps(questions))
    (work / "sections.json").write_text(json.dumps([{"id": "s1", "title": "Overview"}]))
    return base


def _load_qs(base: Path) -> list[dict]:
    return json.loads((base / "work" / "questions.json").read_text())


def test_answer_commit_resolves_and_writes_worklist(tmp_path):
    base = _work_with_questions(tmp_path, [
        {"id": "v-1", "raised_by": "verify", "section_id": "s1", "question": "Fix this?",
         "blocking": True},
        {"id": "v-2", "raised_by": "verify", "section_id": "s1", "question": "Nit?"},
    ])
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps([
        {"id": "v-1", "disposition": "revise", "answer": "Re-draft with p.47."},
        {"id": "v-2", "disposition": "accept", "answer": "Fine as is."},
    ]))

    assert main(["answer-commit", "--answers", str(answers), "--output", str(base)]) == 0

    qs = {q["id"]: q for q in _load_qs(base)}
    assert qs["v-1"]["status"] == "revise_pending"
    assert qs["v-2"]["status"] == "accepted"

    worklist = json.loads((base / "work" / "worklist.json").read_text())
    assert [s["section_id"] for s in worklist["sections"]] == ["s1"]   # revise only
    assert "Re-draft with p.47." in worklist["sections"][0]["guidance"]


def test_answer_commit_triage_mode(tmp_path):
    base = _work_with_questions(tmp_path, [
        {"id": "v-1", "raised_by": "verify", "section_id": "s1", "question": "Fix this?"},
    ])
    triage = tmp_path / "_triage.md"
    triage.write_text("## Open questions\n### v-1\nFix this?\n> answer: [revise] Cite p.47.\n")

    assert main(["answer-commit", "--triage", str(triage), "--output", str(base)]) == 0
    qs = {q["id"]: q for q in _load_qs(base)}
    assert qs["v-1"]["status"] == "revise_pending"
    assert qs["v-1"]["answer"] == "Cite p.47."


def test_answer_commit_rerenders_triage_with_resolved(tmp_path):
    base = _work_with_questions(tmp_path, [
        {"id": "v-1", "raised_by": "verify", "section_id": "s1", "question": "Fix this?"},
    ])
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps([{"id": "v-1", "disposition": "accept", "answer": "ok"}]))
    main(["answer-commit", "--answers", str(answers), "--output", str(base)])
    triage_md = (base / "vault" / "_triage.md").read_text()
    assert "## Resolved questions" in triage_md
    assert "(accepted)" in triage_md


def test_answer_commit_reports_unknown_id(tmp_path, capsys):
    base = _work_with_questions(tmp_path, [
        {"id": "v-1", "raised_by": "verify", "section_id": "s1", "question": "Fix this?"},
    ])
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps([{"id": "ghost", "disposition": "accept", "answer": "x"}]))
    main(["answer-commit", "--answers", str(answers), "--output", str(base)])
    assert "ghost" in capsys.readouterr().out
    assert _load_qs(base)[0]["status"] == "open"


def test_repass_log_warns_after_three_cycles(tmp_path, capsys):
    base = _work_with_questions(tmp_path, [
        {"id": "v-1", "raised_by": "verify", "section_id": "s1", "question": "Fix this?"},
    ])
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps([{"id": "v-1", "disposition": "revise", "answer": "redo"}]))

    # three answer-commit rounds against the same section
    for _ in range(3):
        main(["answer-commit", "--answers", str(answers), "--output", str(base)])

    log = json.loads((base / "work" / "repass_log.json").read_text())
    assert log["s1"] == 3

    capsys.readouterr()                       # clear
    main(["assemble", "--output", str(base)])
    assert "cycled 3 times" in capsys.readouterr().out


def test_assemble_warns_on_unapplied_revise(tmp_path, capsys):
    base = _work_with_questions(tmp_path, [
        {"id": "verify-claim-x-downgrade", "raised_by": "verify", "claim_id": "claim-x",
         "section_id": "s1", "question": "fix me", "status": "revise_pending"}])
    capsys.readouterr()
    main(["assemble", "--output", str(base)])
    assert "revise_pending" in capsys.readouterr().out.lower()


def test_assemble_silent_once_applied(tmp_path, capsys):
    base = _work_with_questions(tmp_path, [
        {"id": "verify-claim-x-downgrade", "raised_by": "verify", "claim_id": "claim-x",
         "section_id": "s1", "question": "fixed", "status": "revise_applied"}])
    capsys.readouterr()
    main(["assemble", "--output", str(base)])
    assert "revise_pending" not in capsys.readouterr().out.lower()


def test_draft_amend_edits_claim_and_flips_revise(tmp_path):
    from tlddr.cli import main
    import json
    base = tmp_path / "out"; work = base / "work"; (work / "nodes").mkdir(parents=True)
    (work / "extracted").mkdir()
    from tlddr.models import ExtractedDoc, PageProvenance, SignalType, ExtractMethod
    doc = ExtractedDoc(id="n", source_path="/x", source_sha256="a", signal_type=SignalType.MIXED,
                       raw_title="N", content="--- page 1 ---\na\n--- page 2 ---\nb",
                       pages=[PageProvenance(page=1, method=ExtractMethod.PYMUPDF_TEXT, has_text_layer=True),
                              PageProvenance(page=2, method=ExtractMethod.PYMUPDF_TEXT, has_text_layer=True)],
                       extractor="pdf")
    (work / "extracted" / "n.json").write_text(doc.model_dump_json())
    (work / "claims.json").write_text(json.dumps([{
        "id": "claim-a", "section_id": "s1", "text": "orig",
        "sources": [{"node_id": "n", "page": 1}],
        "support_level": "fully_supported", "evidence_relation": "quoted"}]))
    (work / "questions.json").write_text(json.dumps([{
        "id": "verify-claim-a-downgrade", "raised_by": "verify", "claim_id": "claim-a",
        "section_id": "s1", "question": "q", "status": "revise_pending"}]))
    amend = tmp_path / "am.json"
    amend.write_text(json.dumps([{"claim_id": "claim-a", "set_text": "fixed",
                                  "add_pages": [{"node_id": "n", "page": 2}]}]))
    assert main(["draft-amend", "--amendments", str(amend), "--output", str(base)]) == 0
    claims = json.loads((work / "claims.json").read_text())
    assert claims[0]["text"] == "fixed" and sorted(s["page"] for s in claims[0]["sources"]) == [1, 2]
    q = json.loads((work / "questions.json").read_text())[0]
    assert q["status"] == "revise_applied"
