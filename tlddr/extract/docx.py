from pathlib import Path
import mammoth
from tlddr.extract.base import ExtractContext
from tlddr.ids import doc_id, sha256_file
from tlddr.models import ExtractedDoc, SignalType


def extract(path: Path, ctx: ExtractContext) -> ExtractedDoc:
    with path.open("rb") as fh:
        result = mammoth.convert_to_markdown(fh)
    warnings = [f"{m.type}: {m.message}" for m in result.messages]
    return ExtractedDoc(
        id=doc_id(path),
        source_path=str(path),
        source_sha256=sha256_file(path),
        signal_type=SignalType.BORN_DIGITAL_REPORT,
        raw_title=path.stem,
        content=result.value,
        pages=[],
        warnings=warnings,
        extractor="docx",
    )
