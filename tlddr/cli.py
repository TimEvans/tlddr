import argparse
import sys
from pathlib import Path
from tlddr.extract.base import ExtractContext
from tlddr.extract.router import route
from tlddr.extract.report import render_report
from tlddr.models import ExtractedDoc


def run_extract(source: Path, out: Path) -> list[ExtractedDoc]:
    extracted_dir = out / "extracted"
    asset_dir = out / "thumbnails"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    ctx = ExtractContext(asset_dir=asset_dir)

    files = sorted(p for p in source.rglob("*") if p.is_file())
    docs: list[ExtractedDoc] = []
    for path in files:
        doc = route(path, ctx)
        (extracted_dir / f"{doc.id}.json").write_text(doc.model_dump_json(indent=2))
        docs.append(doc)
        print(f"extracted {doc.id} [{doc.signal_type.value}] ({len(doc.warnings)} warnings)")

    (out / "extraction-report.md").write_text(render_report(docs))
    print(f"\nwrote {len(docs)} records and extraction-report.md to {out}")
    return docs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tlddr")
    sub = parser.add_subparsers(dest="command", required=True)

    extract_cmd = sub.add_parser("extract", help="extract source documents into node records")
    extract_cmd.add_argument("--source", required=True, type=Path)
    extract_cmd.add_argument("--out", default=Path(".tlddr"), type=Path)

    args = parser.parse_args(argv)
    if args.command == "extract":
        run_extract(args.source, args.out)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
