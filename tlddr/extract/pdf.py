from pathlib import Path
import fitz  # pymupdf
from tlddr.extract.base import ExtractContext
from tlddr.ids import doc_id, sha256_file
from tlddr.models import ExtractedDoc, PageProvenance, SignalType, ExtractMethod

TEXT_THRESHOLD = 10  # chars of stripped text to count a page as text-bearing
THUMBNAIL_SCALE = 0.3


def extract(path: Path, ctx: ExtractContext) -> ExtractedDoc:
    pages: list[PageProvenance] = []
    warnings: list[str] = []
    content_parts: list[str] = []
    did = doc_id(path)

    with fitz.open(path) as pdf:
        for index, page in enumerate(pdf):
            number = index + 1
            text = page.get_text("text").strip()
            has_text = len(text) >= TEXT_THRESHOLD
            if has_text:
                content_parts.append(f"--- page {number} ---\n{text}")
                pages.append(PageProvenance(
                    page=number, method=ExtractMethod.PYMUPDF_TEXT,
                    has_text_layer=True, char_count=len(text),
                ))
            else:
                ctx.asset_dir.mkdir(parents=True, exist_ok=True)
                thumb = ctx.asset_dir / f"{did}-p{number}.png"
                pixmap = page.get_pixmap(matrix=fitz.Matrix(THUMBNAIL_SCALE, THUMBNAIL_SCALE))
                pixmap.save(thumb)
                warnings.append(
                    f"page {number} image-only; would route to vision (not run in reconnaissance)"
                )
                pages.append(PageProvenance(
                    page=number, method=ExtractMethod.VISION,
                    has_text_layer=False, char_count=0, thumbnail=str(thumb),
                ))

        pdf_title = (pdf.metadata or {}).get("title") or path.stem

    text_pages = sum(1 for p in pages if p.has_text_layer)
    if not pages:
        signal = SignalType.UNKNOWN
    elif text_pages == len(pages):
        signal = SignalType.BORN_DIGITAL_REPORT
    elif text_pages == 0:
        signal = SignalType.DRAWING
    else:
        signal = SignalType.MIXED

    return ExtractedDoc(
        id=did,
        source_path=str(path),
        source_sha256=sha256_file(path),
        signal_type=signal,
        raw_title=pdf_title,
        content="\n\n".join(content_parts),
        pages=pages,
        warnings=warnings,
        extractor="pdf",
    )
