from enum import Enum
from pydantic import BaseModel, Field


class SignalType(str, Enum):
    BORN_DIGITAL_REPORT = "born_digital_report"
    SLIDE_DECK = "slide_deck"
    TABLE_PAGE = "table_page"
    DRAWING = "drawing"
    SPREADSHEET = "spreadsheet"
    IMAGE = "image"
    GEOSPATIAL = "geospatial"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class ExtractMethod(str, Enum):
    PYMUPDF_TEXT = "pymupdf_text"
    MAMMOTH_DOCX = "mammoth_docx"
    OPENPYXL_XLSX = "openpyxl_xlsx"
    KMZ_IDENTITY = "kmz_identity"
    VISION = "vision"
    OCR = "ocr"


class PageProvenance(BaseModel):
    page: int
    method: ExtractMethod
    has_text_layer: bool
    char_count: int = 0
    thumbnail: str | None = None


class ExtractedDoc(BaseModel):
    id: str
    source_path: str
    source_sha256: str
    signal_type: SignalType
    raw_title: str
    content: str
    pages: list[PageProvenance] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    extractor: str
