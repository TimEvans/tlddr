import argparse
import json
import sys
from pathlib import Path
from tlddr.extract.base import ExtractContext
from tlddr.extract.router import route
from tlddr.extract.report import render_report
from tlddr.ids import doc_id, sha256_file
from tlddr.models import ExtractedDoc, Node, Question, SignalType, Section
from tlddr.understand.slice import build_slice
from tlddr.understand.commit import build_node
from tlddr.understand.sections import load_sections, section_ids
from tlddr.understand.node_render import render_node_markdown
from tlddr.understand.render import render_index, render_triage


def run_extract(source: Path, out: Path) -> list[ExtractedDoc]:
    extracted_dir = out / "extracted"
    asset_dir = out / "thumbnails"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    asset_dir.mkdir(parents=True, exist_ok=True)
    ctx = ExtractContext(asset_dir=asset_dir)

    files = sorted(p for p in source.rglob("*") if p.is_file())
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
    existing = [q for q in existing if q.get("node_id") != node.id]  # replace this node's prior questions
    existing.extend(q.model_dump(mode="json") for q in questions)
    questions_path.write_text(json.dumps(existing, indent=2))

    for d in dropped_edges:
        print(f"dropped edge {node.id} -> {d.target} ({d.relation.value}): target not in node set")
    for t in dropped_sections:
        print(f"dropped section tag {node.id} -> {t}: not in sections.json")
    print(f"committed {node.id} [{node.triage.value}] "
          f"({len(node.related)} edges, {len(node.report_sections)} sections, "
          f"{len(questions)} questions)")
    return node


def understand_render(work_dir: Path, vault_dir: Path) -> None:
    nodes = [Node.model_validate_json(p.read_text())
             for p in sorted((work_dir / "nodes").glob("*.json"))]
    questions_path = work_dir / "questions.json"
    questions = ([Question.model_validate(q) for q in json.loads(questions_path.read_text())]
                 if questions_path.exists() else [])

    vault_dir.mkdir(parents=True, exist_ok=True)
    for node in nodes:
        (vault_dir / f"{node.id}.md").write_text(render_node_markdown(node))
    (vault_dir / "_index.md").write_text(render_index(nodes))
    (vault_dir / "_triage.md").write_text(render_triage(nodes, questions))
    print(f"rendered {len(nodes)} nodes to {vault_dir}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tlddr")
    sub = parser.add_subparsers(dest="command", required=True)

    extract_cmd = sub.add_parser("extract", help="extract source documents into node records")
    extract_cmd.add_argument("--source", required=True, type=Path)
    extract_cmd.add_argument("--out", default=Path(".tlddr"), type=Path)

    slice_cmd = sub.add_parser("understand-slice", help="print the bounded slice for one document")
    slice_cmd.add_argument("--extracted", required=True, type=Path)
    slice_cmd.add_argument("--id", required=True)

    sections_cmd = sub.add_parser("sections", help="load, validate, and print the section structure")
    sections_cmd.add_argument("--sections", required=True, type=Path)

    commit_cmd = sub.add_parser("understand-commit", help="assemble a validated node from agent enrichment")
    commit_cmd.add_argument("--enrichment", required=True, type=Path)
    commit_cmd.add_argument("--extracted", required=True, type=Path)
    commit_cmd.add_argument("--out", default=Path(".tlddr"), type=Path)
    commit_cmd.add_argument("--sections", type=Path, default=None)

    render_cmd = sub.add_parser("understand-render", help="render the vault, index, and triage")
    render_cmd.add_argument("--work", default=Path(".tlddr"), type=Path)
    render_cmd.add_argument("--vault", default=Path("vault"), type=Path)

    args = parser.parse_args(argv)
    if args.command == "extract":
        run_extract(args.source, args.out)
        return 0
    if args.command == "understand-slice":
        print(understand_slice(args.extracted, args.id))
        return 0
    if args.command == "sections":
        understand_sections(args.sections)
        return 0
    if args.command == "understand-commit":
        understand_commit(args.enrichment, args.extracted, args.out, args.sections)
        return 0
    if args.command == "understand-render":
        understand_render(args.work, args.vault)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
