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
