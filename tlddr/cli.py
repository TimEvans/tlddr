import argparse
import json
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tlddr import runstate
from tlddr import config as tlddr_config
from tlddr.status import render_status
from tlddr.extract.base import ExtractContext
from tlddr.extract.router import route
from tlddr.extract.report import render_report
from tlddr.ids import doc_id, sha256_file
from tlddr.models import ExtractedDoc, Node, Question, QuestionStatus, SignalType, Section, DraftClaim
from tlddr.understand.slice import build_slice
from tlddr.understand.commit import build_node
from tlddr.understand.sections import load_sections, section_ids
from tlddr.understand.node_render import render_node_markdown
from tlddr.understand.render import render_index, render_triage
from tlddr.draft.read import build_read
from tlddr.draft.claims import validate_claims, _claim_id
from tlddr.draft.amend import apply_amendments
from tlddr.draft.eval import groundedness_readout
from tlddr.draft.verify import ingest_verdicts
from tlddr.draft.assemble import render_published, render_sidecar
from tlddr.answer import ingest_answers, parse_triage_answers
from tlddr import bench


def resolve_base(cli_output: Path | None) -> Path:
    """Resolve the output base: --output flag > TLDDR_OUTPUT env > current directory."""
    if cli_output is not None:
        return cli_output
    env = os.environ.get("TLDDR_OUTPUT")
    return Path(env) if env else Path(".")


@dataclass(frozen=True)
class Paths:
    """Derive every output root from a single base directory."""

    base: Path

    @property
    def work(self) -> Path:
        """The hidden machine bin. Falls back to a legacy work/ dir if one exists
        and .tlddr/ does not, so pre-existing runs keep working until re-run."""
        hidden = self.base / ".tlddr"
        legacy = self.base / "work"
        if legacy.exists() and not hidden.exists():
            return legacy
        return hidden

    @property
    def state_lock(self) -> Path:
        return self.work / "state_lock.json"

    @property
    def config(self) -> Path:
        return self.base / "tlddr.toml"

    @property
    def extracted(self) -> Path:
        return self.work / "extracted"

    @property
    def thumbnails(self) -> Path:
        return self.work / "thumbnails"

    @property
    def nodes(self) -> Path:
        return self.work / "nodes"

    @property
    def enrichment(self) -> Path:
        return self.work / "enrichment"

    @property
    def sections(self) -> Path:
        return self.work / "sections.json"

    @property
    def questions(self) -> Path:
        return self.work / "questions.json"

    @property
    def claims(self) -> Path:
        return self.work / "claims.json"

    @property
    def vault(self) -> Path:
        return self.base / "vault"

    @property
    def report(self) -> Path:
        return self.base / "report"


# SEC EDGAR ships each filing with machine-generated companions that duplicate
# the primary document's content or describe the filing package itself. We skip
# them so the corpus holds one faithful copy of each fact, not many:
#   - R\d+.htm        : the XBRL viewer's re-render of facts already inline in
#                       the primary document (133 of them in the Chevron 10-K).
#   - *-index*.html   : the filing index / manifest pages.
#   - FilingSummary.xml, *_cal/_def/_lab/_pre.xml, *.xsd, *-xbrl.zip : the XBRL
#                       linkbases and schema, not human-readable content.
_BOILERPLATE_PATTERNS = (
    re.compile(r"^R\d+\.htm$", re.IGNORECASE),
    re.compile(r"-index(-headers)?\.html$", re.IGNORECASE),
    re.compile(r"^FilingSummary\.xml$", re.IGNORECASE),
    re.compile(r"_(cal|def|lab|pre)\.xml$", re.IGNORECASE),
    re.compile(r"\.xsd$", re.IGNORECASE),
    re.compile(r"-xbrl\.zip$", re.IGNORECASE),
)


def _is_sec_boilerplate(path: Path) -> bool:
    name = path.name
    return any(pattern.search(name) for pattern in _BOILERPLATE_PATTERNS)


def run_extract(source: Path, out: Path, benchmark: Path | None = None) -> list[ExtractedDoc]:
    with bench.timed_stage(benchmark, "extract"):
        extracted_dir = out / "extracted"
        asset_dir = out / "thumbnails"
        extracted_dir.mkdir(parents=True, exist_ok=True)
        asset_dir.mkdir(parents=True, exist_ok=True)
        ctx = ExtractContext(asset_dir=asset_dir)

        files = sorted(
            p for p in source.rglob("*")
            if p.is_file() and not _is_sec_boilerplate(p)
        )
        docs: list[ExtractedDoc] = []
        for path in files:
            try:
                doc = route(path, ctx)
            except Exception as exc:
                doc = ExtractedDoc(
                    id=doc_id(path),
                    source_path=str(path),
                    source_sha256=sha256_file(path) if path.exists() else "",
                    signal_type=SignalType.UNKNOWN,
                    raw_title=path.stem,
                    content="",
                    warnings=[f"extraction failed: {type(exc).__name__}: {exc}"],
                    extractor="error",
                )
            json_path = extracted_dir / f"{doc.id}.json"
            if json_path.exists():
                print(f"warning: id collision on '{doc.id}', overwriting {json_path}")
            json_path.write_text(doc.model_dump_json(indent=2))
            docs.append(doc)
            print(f"extracted {doc.id} [{doc.signal_type.value}] ({len(doc.warnings)} warnings)")

        (out / "extraction-report.md").write_text(render_report(docs))
        print(f"\nwrote {len(docs)} records and extraction-report.md to {out}")
    return docs


def _load_doc(extracted_dir: Path, node_id: str) -> ExtractedDoc:
    return ExtractedDoc.model_validate_json((extracted_dir / f"{node_id}.json").read_text())


def understand_slice(extracted_dir: Path, node_id: str) -> str:
    return build_slice(_load_doc(extracted_dir, node_id))


def understand_sections(sections_path: Path) -> list[Section]:
    sections = load_sections(sections_path)
    for s in sections:
        prefix = "  " if s.parent else ""
        print(f"{prefix}{s.id} — {s.title}")
    return sections


def understand_commit(enrichment_path: Path, extracted_dir: Path, out_dir: Path,
                      sections_path: Path | None = None) -> Node:
    enrichment = json.loads(enrichment_path.read_text())
    doc = _load_doc(extracted_dir, enrichment["extracted_id"])
    known_ids = {p.stem for p in extracted_dir.glob("*.json")}
    known_section_ids = (section_ids(load_sections(sections_path))
                         if sections_path else frozenset())

    node, dropped_edges, dropped_sections, questions = build_node(
        enrichment, doc, known_ids, known_section_ids)

    nodes_dir = out_dir / "nodes"
    nodes_dir.mkdir(parents=True, exist_ok=True)
    (nodes_dir / f"{node.id}.json").write_text(node.model_dump_json(indent=2))

    questions_path = out_dir / "questions.json"
    existing = json.loads(questions_path.read_text()) if questions_path.exists() else []
    # drop only this node's OPEN questions (regenerated fresh below); preserve answered ones
    # so the _apply_revises call below can flip REVISE_PENDING -> REVISE_APPLIED
    existing = [q for q in existing
                if q.get("node_id") != node.id or q.get("status", "open") != "open"]
    existing.extend(q.model_dump(mode="json") for q in questions)
    questions_path.write_text(json.dumps(existing, indent=2))
    _apply_revises(out_dir, lambda q, nid=node.id: q.node_id == nid)

    for d in dropped_edges:
        print(f"dropped edge {node.id} -> {d.target} ({d.relation.value}): target not in node set")
    for t in dropped_sections:
        print(f"dropped section tag {node.id} -> {t}: not a known section id")
    print(f"committed {node.id} [{node.triage.value}] "
          f"({len(node.related)} edges, {len(node.report_sections)} sections, "
          f"{len(questions)} questions)")
    return node


def understand_render(work_dir: Path, vault_dir: Path,
                      sections_path: Path | None = None) -> None:
    nodes = [Node.model_validate_json(p.read_text())
             for p in sorted((work_dir / "nodes").glob("*.json"))]
    questions_path = work_dir / "questions.json"
    questions = ([Question.model_validate(q) for q in json.loads(questions_path.read_text())]
                 if questions_path.exists() else [])
    sections = load_sections(sections_path) if sections_path else None

    vault_dir.mkdir(parents=True, exist_ok=True)
    for node in nodes:
        (vault_dir / f"{node.id}.md").write_text(render_node_markdown(node))
    (vault_dir / "_index.md").write_text(render_index(nodes))
    (vault_dir / "_triage.md").write_text(render_triage(nodes, questions, sections))
    print(f"rendered {len(nodes)} nodes to {vault_dir}")


def _load_claims(work_dir: Path) -> list[DraftClaim]:
    path = work_dir / "claims.json"
    return [DraftClaim.model_validate(c) for c in json.loads(path.read_text())] if path.exists() else []


def _append_questions(work_dir: Path, new: list,
                      drop: Callable[[dict], bool] | None = None) -> None:
    path = work_dir / "questions.json"
    existing = json.loads(path.read_text()) if path.exists() else []
    if drop is not None:
        existing = [q for q in existing if not drop(q)]
    existing.extend(q.model_dump(mode="json") for q in new)
    path.write_text(json.dumps(existing, indent=2))


def _apply_revises(work_dir: Path, match) -> None:
    """Flip REVISE_PENDING -> REVISE_APPLIED for questions the given predicate selects."""
    path = work_dir / "questions.json"
    if not path.exists():
        return
    questions = [Question.model_validate(q) for q in json.loads(path.read_text())]
    for q in questions:
        if q.status is QuestionStatus.REVISE_PENDING and match(q):
            q.status = QuestionStatus.REVISE_APPLIED
    path.write_text(json.dumps([q.model_dump(mode="json") for q in questions], indent=2))


def draft_read(extracted_dir: Path, node_id: str, pages: list[int] | None) -> str:
    return build_read(_load_doc(extracted_dir, node_id), pages=pages)


def draft_commit(claims_path: Path, extracted_dir: Path, work_dir: Path,
                 sections_path: Path | None = None) -> list[DraftClaim]:
    raw = json.loads(claims_path.read_text())
    docs = {p.stem: _load_doc(extracted_dir, p.stem) for p in extracted_dir.glob("*.json")}
    nodes = {n.id: n for n in (Node.model_validate_json(p.read_text())
                               for p in (work_dir / "nodes").glob("*.json"))}
    known_section_ids = section_ids(load_sections(sections_path)) if sections_path else None
    valid, findings = validate_claims(raw, docs, nodes, known_section_ids)

    submitted_sections = {r["section_id"] for r in raw}
    committed = [c for c in _load_claims(work_dir) if c.section_id not in submitted_sections]
    committed.extend(valid)
    for c in committed:
        if not c.id:
            c.id = _claim_id(c.section_id, c.text)
    seen: dict[str, int] = {}
    for c in committed:
        if c.id in seen:
            seen[c.id] += 1
            c.id = f"{c.id}-{seen[c.id]}"
        else:
            seen[c.id] = 1
    (work_dir / "claims.json").write_text(
        json.dumps([c.model_dump(mode="json") for c in committed], indent=2))
    for section in submitted_sections:
        _append_questions(work_dir, [],
                          drop=lambda q, s=section: q.get("raised_by") == "draft" and q.get("section_id") == s)
    _append_questions(work_dir, findings)
    for section in submitted_sections:
        _apply_revises(work_dir, lambda q, s=section: q.section_id == s)
    print(f"committed {len(valid)} claims, {len(findings)} findings")
    return valid


def draft_amend(amendments_path: Path, extracted_dir: Path, work_dir: Path,
                sections_path: Path | None = None) -> None:
    records = json.loads(amendments_path.read_text())
    docs = {p.stem: _load_doc(extracted_dir, p.stem) for p in extracted_dir.glob("*.json")}
    nodes = {n.id: n for n in (Node.model_validate_json(p.read_text())
                               for p in (work_dir / "nodes").glob("*.json"))}
    known_section_ids = section_ids(load_sections(sections_path)) if sections_path else None
    claims = _load_claims(work_dir)
    updated, amended, dropped = apply_amendments(records, claims, docs, nodes, known_section_ids)
    (work_dir / "claims.json").write_text(
        json.dumps([c.model_dump(mode="json") for c in updated], indent=2))

    questions_path = work_dir / "questions.json"
    questions = ([Question.model_validate(q) for q in json.loads(questions_path.read_text())]
                 if questions_path.exists() else [])
    flipped = 0
    for q in questions:
        if (q.claim_id in amended and q.status is QuestionStatus.REVISE_PENDING):
            q.status = QuestionStatus.REVISE_APPLIED
            flipped += 1
    questions_path.write_text(json.dumps([q.model_dump(mode="json") for q in questions], indent=2))
    for message in dropped:
        print(f"dropped amendment: {message}")
    print(f"amended {len(amended)} claims, applied {flipped} revise question(s)")


def draft_verify_commit(verdicts_path: Path, work_dir: Path) -> None:
    verdicts = json.loads(verdicts_path.read_text())
    questions_path = work_dir / "questions.json"
    existing = ([Question.model_validate(q) for q in json.loads(questions_path.read_text())]
                if questions_path.exists() else [])
    suppress_ids = {q.id for q in existing if q.status is not QuestionStatus.OPEN}
    new_qs = ingest_verdicts(verdicts, _load_claims(work_dir), suppress_ids)
    _append_questions(
        work_dir, new_qs,
        drop=lambda q: q.get("raised_by") == "verify" and q.get("status", "open") == "open")
    print(f"raised {len(new_qs)} verify questions")


def _format_worklist(worklist: dict) -> str:
    lines = ["RE-PASS WORKLIST"]
    if worklist["sections"]:
        lines.append("Section re-passes (re-draft -> re-verify):")
        for s in worklist["sections"]:
            lines.append(f"  - {s['section_id']}   from: {', '.join(s['from'])}")
            lines.append(f"    guidance: {s['guidance']}")
    if worklist["nodes"]:
        lines.append("Node re-passes (re-understand):")
        for n in worklist["nodes"]:
            lines.append(f"  - {n['node_id']}   from: {', '.join(n['from'])}")
            lines.append(f"    guidance: {n['guidance']}")
    if not worklist["sections"] and not worklist["nodes"]:
        lines.append("(nothing to re-pass)")
    return "\n".join(lines)


def _bump_repass_log(work_dir: Path, worklist: dict) -> None:
    path = work_dir / "repass_log.json"
    log = json.loads(path.read_text()) if path.exists() else {}
    for item in worklist["sections"]:
        log[item["section_id"]] = log.get(item["section_id"], 0) + 1
    for item in worklist["nodes"]:
        log[item["node_id"]] = log.get(item["node_id"], 0) + 1
    path.write_text(json.dumps(log, indent=2))


def answer_commit(answers_path: Path | None, triage_path: Path | None, work_dir: Path,
                  sections_path: Path | None = None, vault_dir: Path | None = None) -> None:
    questions_path = work_dir / "questions.json"
    questions = ([Question.model_validate(q) for q in json.loads(questions_path.read_text())]
                 if questions_path.exists() else [])
    if triage_path is not None:
        records, skipped = parse_triage_answers(triage_path.read_text())
        for qid in skipped:
            print(f"skipped slot for '{qid}': filled but no [revise]/[accept] tag")
    else:
        records = json.loads(answers_path.read_text())

    updated, worklist, dropped = ingest_answers(records, questions)
    for message in dropped:
        print(f"dropped answer: {message}")
    questions_path.write_text(
        json.dumps([q.model_dump(mode="json") for q in updated], indent=2))
    (work_dir / "worklist.json").write_text(json.dumps(worklist, indent=2))
    _bump_repass_log(work_dir, worklist)
    print(_format_worklist(worklist))

    if vault_dir is not None:
        understand_render(work_dir, vault_dir, sections_path)


def draft_eval(work_dir: Path, sections_path: Path, benchmark: Path | None = None) -> None:
    with bench.timed_stage(benchmark, "draft-eval"):
        print(groundedness_readout(_load_claims(work_dir), load_sections(sections_path)))


def assemble(work_dir: Path, out_dir: Path, sections_path: Path,
             vault_dir: Path = Path("vault"), benchmark: Path | None = None) -> None:
    with bench.timed_stage(benchmark, "assemble"):
        claims = _load_claims(work_dir)
        sections = load_sections(sections_path)
        questions_path = work_dir / "questions.json"
        questions = ([Question.model_validate(q) for q in json.loads(questions_path.read_text())]
                     if questions_path.exists() else [])
        pending = [q for q in questions if q.status is QuestionStatus.REVISE_PENDING]
        for q in pending:
            target = q.section_id or q.node_id or q.claim_id
            print(f"warning: {q.id} is revise_pending with no re-pass applied "
                  f"(target {target})")
        repass_log_path = work_dir / "repass_log.json"
        if repass_log_path.exists():
            log = json.loads(repass_log_path.read_text())
            for target, count in sorted(log.items()):
                if count >= 3:
                    print(f"warning: '{target}' has cycled {count} times "
                          f"through the answer loop")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "report.md").write_text(render_published(sections, claims))
        (out_dir / "report_comments.md").write_text(render_sidecar(sections, claims, questions))
        nodes = [Node.model_validate_json(p.read_text())
                 for p in sorted((work_dir / "nodes").glob("*.json"))]
        vault_dir.mkdir(parents=True, exist_ok=True)
        (vault_dir / "_triage.md").write_text(render_triage(nodes, questions, sections))
        print(f"assembled {len(claims)} claims into report.md + report_comments.md")


def bench_record(benchmark_dir: Path, extracted_dir: Path | None, stage: str,
                 unit: str, kind: str, model: str, tokens: int, tools: int,
                 ms: int, notes: str) -> dict:
    source_chars, source_pages = (
        bench.source_size(extracted_dir, unit) if kind == "doc" else (None, None))
    row = bench.record_row(benchmark_dir, stage=stage, unit=unit, unit_kind=kind,
                           model=model, tokens=tokens, tool_uses=tools, duration_ms=ms,
                           source_chars=source_chars, source_pages=source_pages, notes=notes)
    print(f"recorded {stage}/{unit}: {tokens} tok, {tools} tools, {ms} ms"
          + (f", {source_chars} src chars / {source_pages} pages"
             if source_chars is not None else ""))
    return row


def bench_report(benchmark_dir: Path) -> str:
    return bench.render_report(bench.load_rows(benchmark_dir))


def status(base: Path) -> None:
    paths = Paths(base)
    state = runstate.load_state(paths.state_lock)
    rows = bench.load_rows(paths.work / "benchmark") if (paths.work / "benchmark").exists() else []
    qpath = paths.questions
    questions = ([Question.model_validate(q) for q in json.loads(qpath.read_text())]
                 if qpath.exists() else [])
    print(render_status(state, rows, questions))


def mark_stage_cmd(base: Path, stage: str) -> None:
    paths = Paths(base)
    now = datetime.now(timezone.utc).isoformat()
    runstate.mark_stage(paths.state_lock, stage, now=now)
    print(f"marked {stage} done")


def config_cmd(base: Path, preset: str | None, corpus: str | None, model: str | None,
               effort: str | None, interaction: str | None, benchmark: bool | None) -> None:
    paths = Paths(base)
    toml_cfg = tlddr_config.read_toml(paths.config)
    overrides = {"corpus": corpus, "output": str(base), "model": model,
                 "effort": effort, "interaction": interaction, "benchmark": benchmark}
    cfg = tlddr_config.resolve_config(preset, overrides, toml_cfg)
    # persist human config (top-level + overrides table for any non-preset axis values)
    persist = {"corpus": cfg.get("corpus"), "output": cfg.get("output"),
               "preset": cfg.get("preset"), "overrides": {a: cfg[a] for a in
               ("model", "effort", "interaction", "benchmark") if a in cfg}}
    tlddr_config.write_toml(paths.config, {k: v for k, v in persist.items() if v is not None})
    fp = runstate.corpus_fingerprint(Path(cfg["corpus"])) if cfg.get("corpus") else ""
    runstate.init_state(paths.state_lock, cfg, fp)
    print("resolved config:")
    for k in ("corpus", "output", "preset", "model", "effort", "interaction", "benchmark"):
        if k in cfg:
            print(f"  {k}: {cfg[k]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tlddr")
    sub = parser.add_subparsers(dest="command", required=True)

    extract_cmd = sub.add_parser("extract", help="extract source documents into node records")
    extract_cmd.add_argument("--source", required=True, type=Path)
    extract_cmd.add_argument("--output", type=Path, default=None)
    extract_cmd.add_argument("--benchmark", type=Path, default=None)

    slice_cmd = sub.add_parser("understand-slice", help="print the bounded slice for one document")
    slice_cmd.add_argument("--output", type=Path, default=None)
    slice_cmd.add_argument("--id", required=True)

    sections_cmd = sub.add_parser("sections", help="load, validate, and print the section structure")
    sections_cmd.add_argument("--sections", required=True, type=Path)

    commit_cmd = sub.add_parser("understand-commit", help="assemble a validated node from agent enrichment")
    commit_cmd.add_argument("--enrichment", required=True, type=Path)
    commit_cmd.add_argument("--output", type=Path, default=None)

    render_cmd = sub.add_parser("understand-render", help="render the vault, index, and triage")
    render_cmd.add_argument("--output", type=Path, default=None)

    dread = sub.add_parser("draft-read", help="serve a node's content/pages for drafting")
    dread.add_argument("--output", type=Path, default=None)
    dread.add_argument("--id", required=True)
    dread.add_argument("--pages", type=str, default=None, help="comma-separated page numbers")

    dcommit = sub.add_parser("draft-commit", help="validate agent draft claims for a section")
    dcommit.add_argument("--claims", required=True, type=Path)
    dcommit.add_argument("--output", type=Path, default=None)

    damend = sub.add_parser("draft-amend", help="apply validated claim-level edits (the re-pass)")
    damend.add_argument("--amendments", required=True, type=Path)
    damend.add_argument("--output", type=Path, default=None)

    dverify = sub.add_parser("draft-verify-commit", help="ingest C-lite judge verdicts")
    dverify.add_argument("--verdicts", required=True, type=Path)
    dverify.add_argument("--output", type=Path, default=None)

    acommit = sub.add_parser("answer-commit",
                             help="ingest reviewer answers and build the re-pass worklist")
    asrc = acommit.add_mutually_exclusive_group(required=True)
    asrc.add_argument("--answers", type=Path, default=None)
    asrc.add_argument("--triage", type=Path, default=None)
    acommit.add_argument("--output", type=Path, default=None)

    deval = sub.add_parser("draft-eval", help="print the tier-B groundedness readout")
    deval.add_argument("--output", type=Path, default=None)
    deval.add_argument("--benchmark", type=Path, default=None)

    asm = sub.add_parser("assemble", help="assemble report.md + report_comments.md")
    asm.add_argument("--output", type=Path, default=None)
    asm.add_argument("--benchmark", type=Path, default=None)

    st = sub.add_parser("status", help="print deterministic run state + progress")
    st.add_argument("--output", type=Path, default=None)

    ms = sub.add_parser("mark-stage", help="record a stage as done in the run state")
    ms.add_argument("stage", choices=runstate.STAGES)
    ms.add_argument("--output", type=Path, default=None)

    cfg_cmd = sub.add_parser("config", help="resolve + persist run configuration (presets + overrides)")
    cfg_cmd.add_argument("--preset", choices=list(tlddr_config.PRESETS), default=None)
    cfg_cmd.add_argument("--corpus", default=None)
    cfg_cmd.add_argument("--model", choices=["sonnet", "opus"], default=None)
    cfg_cmd.add_argument("--effort", choices=["low", "medium", "high"], default=None)
    cfg_cmd.add_argument("--interaction", choices=["autonomous", "guided"], default=None)
    cfg_cmd.add_argument("--benchmark", dest="benchmark", action="store_true", default=None)
    cfg_cmd.add_argument("--output", type=Path, default=None)

    bench_cmd = sub.add_parser("bench", help="record and report run benchmarks")
    bench_sub = bench_cmd.add_subparsers(dest="bench_command", required=True)

    brec = bench_sub.add_parser("record", help="append one benchmark row")
    brec.add_argument("--benchmark", required=True, type=Path)
    brec.add_argument("--stage", required=True)
    brec.add_argument("--unit", required=True)
    brec.add_argument("--kind", default="doc", choices=["doc", "section", "corpus", "stage"])
    brec.add_argument("--model", default="")
    brec.add_argument("--tokens", required=True, type=int)
    brec.add_argument("--tools", default=0, type=int)
    brec.add_argument("--ms", required=True, type=int)
    brec.add_argument("--extracted", type=Path, default=None)
    brec.add_argument("--notes", default="")

    brep = bench_sub.add_parser("report", help="print benchmark tables")
    brep.add_argument("--benchmark", required=True, type=Path)

    args = parser.parse_args(argv)
    if args.command == "extract":
        paths = Paths(resolve_base(args.output))
        run_extract(args.source, paths.work, args.benchmark)
        return 0
    if args.command == "understand-slice":
        paths = Paths(resolve_base(args.output))
        print(understand_slice(paths.extracted, args.id))
        return 0
    if args.command == "sections":
        understand_sections(args.sections)
        return 0
    if args.command == "understand-commit":
        paths = Paths(resolve_base(args.output))
        sections = paths.sections if paths.sections.exists() else None
        understand_commit(args.enrichment, paths.extracted, paths.work, sections)
        return 0
    if args.command == "understand-render":
        paths = Paths(resolve_base(args.output))
        sections = paths.sections if paths.sections.exists() else None
        understand_render(paths.work, paths.vault, sections)
        return 0
    if args.command == "draft-read":
        paths = Paths(resolve_base(args.output))
        pages = [int(p) for p in args.pages.split(",")] if args.pages else None
        print(draft_read(paths.extracted, args.id, pages))
        return 0
    if args.command == "draft-commit":
        paths = Paths(resolve_base(args.output))
        sections = paths.sections if paths.sections.exists() else None
        draft_commit(args.claims, paths.extracted, paths.work, sections)
        return 0
    if args.command == "draft-amend":
        paths = Paths(resolve_base(args.output))
        sections = paths.sections if paths.sections.exists() else None
        draft_amend(args.amendments, paths.extracted, paths.work, sections)
        return 0
    if args.command == "draft-verify-commit":
        paths = Paths(resolve_base(args.output))
        draft_verify_commit(args.verdicts, paths.work)
        return 0
    if args.command == "answer-commit":
        paths = Paths(resolve_base(args.output))
        sections = paths.sections if paths.sections.exists() else None
        answer_commit(args.answers, args.triage, paths.work, sections, paths.vault)
        return 0
    if args.command == "draft-eval":
        paths = Paths(resolve_base(args.output))
        draft_eval(paths.work, paths.sections, args.benchmark)
        return 0
    if args.command == "assemble":
        paths = Paths(resolve_base(args.output))
        assemble(paths.work, paths.report, paths.sections, paths.vault, args.benchmark)
        return 0
    if args.command == "status":
        status(resolve_base(args.output))
        return 0
    if args.command == "mark-stage":
        mark_stage_cmd(resolve_base(args.output), args.stage)
        return 0
    if args.command == "config":
        config_cmd(resolve_base(args.output), args.preset, args.corpus, args.model,
                   args.effort, args.interaction, args.benchmark)
        return 0
    if args.command == "bench":
        if args.bench_command == "record":
            bench_record(args.benchmark, args.extracted, args.stage, args.unit,
                         args.kind, args.model, args.tokens, args.tools, args.ms, args.notes)
        elif args.bench_command == "report":
            print(bench_report(args.benchmark))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
