import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from tlddr.extract.base import ExtractContext
from tlddr.ids import doc_id, sha256_file
from tlddr.models import ExtractedDoc, PageProvenance, SignalType, ExtractMethod


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _document_name(root: ET.Element) -> str | None:
    for elem in root.iter():
        if _local(elem.tag) == "Document":
            for child in elem:
                if _local(child.tag) == "name" and child.text:
                    return child.text.strip()
    return None


def extract(path: Path, ctx: ExtractContext) -> ExtractedDoc:
    warnings: list[str] = []
    name = path.stem
    placemarks = 0

    with zipfile.ZipFile(path) as z:
        kml_names = [n for n in z.namelist() if n.lower().endswith(".kml")]
        if not kml_names:
            warnings.append("no .kml found inside .kmz")
        else:
            root = ET.fromstring(z.read(kml_names[0]))
            placemarks = sum(1 for elem in root.iter() if _local(elem.tag) == "Placemark")
            doc_name = _document_name(root)
            if doc_name:
                name = doc_name

    summary = (
        f"Geospatial dataset (identity only): '{name}'. "
        f"{placemarks} placemarks/boundaries. Geometry not interpreted."
    )

    return ExtractedDoc(
        id=doc_id(path),
        source_path=str(path),
        source_sha256=sha256_file(path),
        signal_type=SignalType.GEOSPATIAL,
        raw_title=name,
        content=summary,
        pages=[PageProvenance(
            page=1, method=ExtractMethod.KMZ_IDENTITY,
            has_text_layer=False, char_count=len(summary),
        )],
        warnings=warnings,
        extractor="kmz",
    )
