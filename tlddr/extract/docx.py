from pathlib import Path
import mammoth
from tlddr.extract.base import ExtractContext
from tlddr.ids import doc_id, sha256_file
from tlddr.models import ExtractedDoc, SignalType


def extract(path: Path, ctx: ExtractContext) -> ExtractedDoc:
    # By default mammoth inlines embedded images as base64 data-URIs, which can
    # dwarf the real text (90%+ of content on image-heavy documents). We drop the
    # image data and instead record how many images were present, consistent with
    # the identity-not-pixels approach: the existence of a figure matters, its
    # bytes do not belong in the text layer.
    image_count = {"n": 0}

    @mammoth.images.img_element
    def _drop_image(image):
        image_count["n"] += 1
        return {}

    with path.open("rb") as fh:
        result = mammoth.convert_to_markdown(fh, convert_image=_drop_image)
    warnings = [f"{m.type}: {m.message}" for m in result.messages]
    if image_count["n"]:
        warnings.append(
            f"{image_count['n']} embedded image(s) present, not extracted (identity only)"
        )
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
