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


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Triage(str, Enum):
    GREEN = "green"
    AMBER = "amber"
    RED = "red"


class RelationType(str, Enum):
    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"
    CORROBORATES = "corroborates"
    REFERENCES = "references"
    SAME_SUBJECT = "same_subject"
    INPUT_TO = "input_to"


class Edge(BaseModel):
    target: str
    relation: RelationType
    rationale: str


class Section(BaseModel):
    id: str
    title: str
    parent: str | None = None


class Question(BaseModel):
    id: str
    raised_by: str
    node_id: str | None = None
    section_id: str | None = None
    question: str
    blocks: list[str] = Field(default_factory=list)
    blocking: bool = False
    answer: str | None = None


class Node(BaseModel):
    id: str
    extracted_id: str
    title: str
    doc_type: str
    description: str
    report_sections: list[str] = Field(default_factory=list)
    confidence_extraction: Confidence
    confidence_interpretation: Confidence
    triage: Triage
    open_questions: list[str] = Field(default_factory=list)
    related: list[Edge] = Field(default_factory=list)
