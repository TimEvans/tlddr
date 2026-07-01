from pathlib import Path
from tlddr.extract.base import ExtractContext, Extractor
from tlddr.ids import doc_id, sha256_file
from tlddr.models import ExtractedDoc, SignalType

EXTRACTORS: dict[str, Extractor] = {}


def route(path: Path, ctx: ExtractContext) -> ExtractedDoc:
    extractor = EXTRACTORS.get(path.suffix.lower())
    if extractor is None:
        return ExtractedDoc(
            id=doc_id(path),
            source_path=str(path),
            source_sha256=sha256_file(path) if path.exists() else "",
            signal_type=SignalType.UNKNOWN,
            raw_title=path.stem,
            content="",
            warnings=[f"no extractor for extension '{path.suffix.lower()}'"],
            extractor="none",
        )
    return extractor(path, ctx)


from tlddr.extract import pdf as _pdf

EXTRACTORS[".pdf"] = _pdf.extract

from tlddr.extract import docx as _docx

EXTRACTORS[".docx"] = _docx.extract

from tlddr.extract import xlsx as _xlsx

EXTRACTORS[".xlsx"] = _xlsx.extract

from tlddr.extract import kmz as _kmz

EXTRACTORS[".kmz"] = _kmz.extract

from tlddr.extract import html as _html

EXTRACTORS[".htm"] = _html.extract
EXTRACTORS[".html"] = _html.extract
