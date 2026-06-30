from pathlib import Path

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from tlddr.extract.base import ExtractContext
from tlddr.extract.tables import table_markdown as _render_table
from tlddr.ids import doc_id, sha256_file
from tlddr.models import ExtractedDoc, SignalType


def _iter_block_items(document: DocxDocument):
    """Yield paragraphs and tables in true document order.

    python-docx exposes paragraphs and tables as separate collections, which
    loses their interleaving. Walking the body XML preserves the real order so a
    table stays in context with the prose around it.
    """
    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def _paragraph_markdown(paragraph: Paragraph) -> str:
    text = paragraph.text.strip()
    if not text:
        return ""
    style = paragraph.style.name or ""
    if style == "Title":
        return f"# {text}"
    if style.startswith("Heading"):
        try:
            level = int(style.split()[-1])
        except ValueError:
            level = 1
        return f"{'#' * min(level, 6)} {text}"
    return text


def _table_markdown(table: Table) -> str:
    rows = [[cell.text for cell in row.cells] for row in table.rows]
    return _render_table(rows)


def extract(path: Path, ctx: ExtractContext) -> ExtractedDoc:
    # We use python-docx (not mammoth) so that table content is captured
    # faithfully and in document order. mammoth produced cleaner inline prose but
    # silently dropped table cells, which is unacceptable for a content store
    # where tables carry the data. Embedded images are not part of the text
    # layer; we count them as provenance (identity, not pixels) instead.
    document = Document(str(path))

    parts: list[str] = []
    for block in _iter_block_items(document):
        rendered = (
            _paragraph_markdown(block)
            if isinstance(block, Paragraph)
            else _table_markdown(block)
        )
        if rendered:
            parts.append(rendered)

    warnings: list[str] = []
    image_count = len(document.inline_shapes)
    if image_count:
        warnings.append(
            f"{image_count} embedded image(s) present, not extracted (identity only)"
        )

    return ExtractedDoc(
        id=doc_id(path),
        source_path=str(path),
        source_sha256=sha256_file(path),
        signal_type=SignalType.BORN_DIGITAL_REPORT,
        raw_title=path.stem,
        content="\n\n".join(parts),
        pages=[],
        warnings=warnings,
        extractor="docx",
    )
