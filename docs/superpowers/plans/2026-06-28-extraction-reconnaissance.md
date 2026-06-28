# Extraction Reconnaissance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the extraction seam — a signal-type router plus per-format extractors that all emit the same `ExtractedDoc` shape — and run it over the 20-file test corpus to produce an inspectable extraction report, with no model calls.

**Architecture:** A `tlddr` Python package exposes one CLI subcommand, `tlddr extract`, which walks a source directory, routes each file by extension to a format extractor, and writes one JSON record per document plus a human-readable `extraction-report.md`. Every extractor implements the same contract (`extract(path, ctx) -> ExtractedDoc`), so nothing downstream knows which tool read a file. This is proving step 1 from the design spec: confirm the signal is legible before spending anything on reasoning.

**Tech Stack:** Python 3.11+, pydantic v2 (contracts), pymupdf (PDF text + rasterisation), mammoth (DOCX to markdown), openpyxl (XLSX), stdlib `zipfile`/`xml` (KMZ), argparse (CLI), pytest + python-docx (tests/fixtures).

## Global Constraints

- **No emojis** anywhere — code, comments, commit messages, or output. (User hard rule.)
- **Conventional commits**: `type(scope): description` (`feat`, `fix`, `docs`, `test`, `chore`, `refactor`).
- **No model calls in this plan.** Image-only pages are flagged `method=VISION` with a thumbnail and a warning; the actual vision call is a later plan.
- **Swappable extraction seam:** every extractor emits the *same* `ExtractedDoc`; the router never special-cases a downstream consumer.
- **Identity only for drawings and KMZ:** title/name + thumbnail or summary. No geometry interpretation, no CAD, no GIS comprehension.
- **Document = unit of identity, page = unit of provenance.** One `ExtractedDoc` per source file; per-page facts live in `pages[]`.
- **Honesty over coverage:** extraction problems (image-only pages, messy sheets, mammoth warnings, unknown extensions) are surfaced as `warnings`, never swallowed.
- **Composition over inheritance:** the eventual Understand-stage `Node` will *compose* an `ExtractedDoc` (hold it as a field), not subclass it. This plan builds only `ExtractedDoc`.
- **Prefer minimal dependencies:** only the four extraction libs + pydantic at runtime. Add nothing heavier (`pdfplumber`, `camelot`, `pytesseract`, `pandas`) until a real document demands it.

---

## File structure

```
tl-ddr/
  pyproject.toml              # package metadata, deps, console script, pytest config
  .gitignore                  # .venv, __pycache__, egg-info, .tlddr output dir
  tlddr/
    __init__.py
    ids.py                    # doc_id(path), sha256_file(path)
    models.py                 # SignalType, ExtractMethod, PageProvenance, ExtractedDoc
    extract/
      __init__.py
      base.py                 # ExtractContext, Extractor type alias
      router.py               # EXTRACTORS registry, route(path, ctx)
      pdf.py                  # extract(path, ctx) via pymupdf
      docx.py                 # extract(path, ctx) via mammoth
      xlsx.py                 # extract(path, ctx) via openpyxl
      kmz.py                  # extract(path, ctx) via zipfile + xml
      report.py               # render_report(docs) -> markdown
    cli.py                    # main(), run_extract(source, out)
  tests/
    conftest.py               # fixture factories (tiny generated pdf/docx/xlsx/kmz)
    test_ids.py
    test_models.py
    test_router.py
    test_pdf.py
    test_docx.py
    test_xlsx.py
    test_kmz.py
    test_report.py
    test_cli.py
```

Each extractor is one focused file behind a shared contract. `models.py` and `ids.py` are the fixed points every extractor depends on.

---

### Task 1: Project scaffold, contracts, and id helpers

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `tlddr/__init__.py`
- Create: `tlddr/ids.py`
- Create: `tlddr/models.py`
- Test: `tests/test_ids.py`, `tests/test_models.py`

**Interfaces:**
- Produces:
  - `tlddr.ids.doc_id(path: pathlib.Path) -> str` — deterministic slug from the filename stem
  - `tlddr.ids.sha256_file(path: pathlib.Path) -> str` — hex digest of file bytes
  - `tlddr.models.SignalType(str, Enum)` — members below
  - `tlddr.models.ExtractMethod(str, Enum)` — members below
  - `tlddr.models.PageProvenance(BaseModel)` — `page:int, method:ExtractMethod, has_text_layer:bool, char_count:int=0, thumbnail:str|None=None`
  - `tlddr.models.ExtractedDoc(BaseModel)` — `id:str, source_path:str, source_sha256:str, signal_type:SignalType, raw_title:str, content:str, pages:list[PageProvenance], warnings:list[str], extractor:str`

- [ ] **Step 1: Create the package scaffold**

Create `pyproject.toml`:

```toml
[project]
name = "tlddr"
version = "0.1.0"
description = "TDD + tl;dr: drafts technical due-diligence reports from source documents"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.6",
    "pymupdf>=1.24",
    "mammoth>=1.7",
    "openpyxl>=3.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "python-docx>=1.1",
]

[project.scripts]
tlddr = "tlddr.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["tlddr*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Create `.gitignore`:

```gitignore
.venv/
__pycache__/
*.egg-info/
.pytest_cache/
.tlddr/
```

Create empty `tlddr/__init__.py`.

- [ ] **Step 2: Create the virtual environment and install**

Run:
```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```
Expected: installs pydantic, pymupdf, mammoth, openpyxl, pytest, python-docx without error.

- [ ] **Step 3: Write the failing tests for ids and models**

Create `tests/test_ids.py`:

```python
from pathlib import Path
from tlddr.ids import doc_id, sha256_file


def test_doc_id_is_deterministic_slug():
    assert doc_id(Path("/x/A6 Cost-Benefit Analysis.pdf")) == "a6-cost-benefit-analysis"


def test_doc_id_collapses_punctuation_and_spaces():
    assert doc_id(Path("/x/aemo---gis (2025).kmz")) == "aemo-gis-2025"


def test_sha256_file_matches_known_value(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"hello")
    # sha256 of b"hello"
    assert sha256_file(f) == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
```

Create `tests/test_models.py`:

```python
from tlddr.models import SignalType, ExtractMethod, PageProvenance, ExtractedDoc


def test_signal_type_serialises_to_string():
    assert SignalType.BORN_DIGITAL_REPORT.value == "born_digital_report"


def test_extracted_doc_round_trips_json():
    doc = ExtractedDoc(
        id="d1",
        source_path="/x/d1.pdf",
        source_sha256="abc",
        signal_type=SignalType.MIXED,
        raw_title="D1",
        content="body",
        pages=[PageProvenance(page=1, method=ExtractMethod.PYMUPDF_TEXT,
                              has_text_layer=True, char_count=4)],
        warnings=["page 2 image-only"],
        extractor="pdf",
    )
    restored = ExtractedDoc.model_validate_json(doc.model_dump_json())
    assert restored.signal_type is SignalType.MIXED
    assert restored.pages[0].method is ExtractMethod.PYMUPDF_TEXT
    assert restored.warnings == ["page 2 image-only"]
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_ids.py tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tlddr.ids'` / `tlddr.models`.

- [ ] **Step 5: Implement `tlddr/ids.py`**

```python
import hashlib
import re
from pathlib import Path


def doc_id(path: Path) -> str:
    stem = path.stem.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", stem)
    return slug.strip("-")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
```

- [ ] **Step 6: Implement `tlddr/models.py`**

```python
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
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_ids.py tests/test_models.py -v`
Expected: PASS (5 passed).

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .gitignore tlddr/__init__.py tlddr/ids.py tlddr/models.py tests/test_ids.py tests/test_models.py
git commit -m "feat(extract): add package scaffold, ExtractedDoc contract, and id helpers"
```

---

### Task 2: Extractor contract and router

**Files:**
- Create: `tlddr/extract/__init__.py`
- Create: `tlddr/extract/base.py`
- Create: `tlddr/extract/router.py`
- Test: `tests/test_router.py`

**Interfaces:**
- Consumes: `tlddr.models.ExtractedDoc`
- Produces:
  - `tlddr.extract.base.ExtractContext` — frozen dataclass with `asset_dir: pathlib.Path`
  - `tlddr.extract.base.Extractor` — `Callable[[Path, ExtractContext], ExtractedDoc]`
  - `tlddr.extract.router.route(path: Path, ctx: ExtractContext) -> ExtractedDoc` — dispatches by lowercased suffix; unknown suffix returns an `ExtractedDoc` with `signal_type=UNKNOWN` and a warning
  - `tlddr.extract.router.EXTRACTORS: dict[str, Extractor]` — populated by later tasks

- [ ] **Step 1: Write the failing test**

Create `tests/test_router.py`:

```python
from pathlib import Path
from tlddr.extract.base import ExtractContext
from tlddr.extract import router
from tlddr.models import SignalType, ExtractedDoc


def fake_extractor(path: Path, ctx: ExtractContext) -> ExtractedDoc:
    return ExtractedDoc(
        id="fake", source_path=str(path), source_sha256="x",
        signal_type=SignalType.BORN_DIGITAL_REPORT, raw_title="fake",
        content="", extractor="fake",
    )


def test_route_dispatches_by_suffix(tmp_path, monkeypatch):
    monkeypatch.setitem(router.EXTRACTORS, ".pdf", fake_extractor)
    ctx = ExtractContext(asset_dir=tmp_path)
    result = router.route(tmp_path / "doc.PDF", ctx)
    assert result.extractor == "fake"


def test_route_unknown_extension_returns_unknown_with_warning(tmp_path):
    ctx = ExtractContext(asset_dir=tmp_path)
    f = tmp_path / "thing.zip"
    f.write_bytes(b"x")
    result = router.route(f, ctx)
    assert result.signal_type is SignalType.UNKNOWN
    assert any("no extractor" in w.lower() for w in result.warnings)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tlddr.extract'`.

- [ ] **Step 3: Implement `tlddr/extract/__init__.py` (empty) and `tlddr/extract/base.py`**

`tlddr/extract/__init__.py`: empty file.

`tlddr/extract/base.py`:

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from tlddr.models import ExtractedDoc


@dataclass(frozen=True)
class ExtractContext:
    asset_dir: Path


Extractor = Callable[[Path, ExtractContext], ExtractedDoc]
```

- [ ] **Step 4: Implement `tlddr/extract/router.py`**

```python
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
            source_sha256=sha256_file(path),
            signal_type=SignalType.UNKNOWN,
            raw_title=path.stem,
            content="",
            warnings=[f"no extractor for extension '{path.suffix}'"],
            extractor="none",
        )
    return extractor(path, ctx)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_router.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add tlddr/extract/__init__.py tlddr/extract/base.py tlddr/extract/router.py tests/test_router.py
git commit -m "feat(extract): add extractor contract and suffix router"
```

---

### Task 3: PDF extractor (pymupdf)

**Files:**
- Create: `tlddr/extract/pdf.py`
- Modify: `tlddr/extract/router.py` (register `.pdf`)
- Test: `tests/conftest.py`, `tests/test_pdf.py`

**Interfaces:**
- Consumes: `ExtractContext`, `ExtractedDoc`, `PageProvenance`, `SignalType`, `ExtractMethod`, `doc_id`, `sha256_file`
- Produces: `tlddr.extract.pdf.extract(path: Path, ctx: ExtractContext) -> ExtractedDoc`. Per page: text-layer probe sets `has_text_layer` and `method` (`PYMUPDF_TEXT` for text pages, `VISION` for image-only). Image-only pages get a rasterised thumbnail under `ctx.asset_dir` and a warning. Doc `signal_type`: all-text -> `BORN_DIGITAL_REPORT`, all-image -> `DRAWING`, mixed -> `MIXED`.

- [ ] **Step 1: Add fixture factories to `tests/conftest.py`**

Create `tests/conftest.py`:

```python
import zipfile
from pathlib import Path
import pytest
import fitz  # pymupdf
from openpyxl import Workbook
from docx import Document


@pytest.fixture
def born_digital_pdf(tmp_path) -> Path:
    p = tmp_path / "born.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Renewable energy zone cost benefit analysis")
    doc.save(p)
    doc.close()
    return p


@pytest.fixture
def image_only_pdf(tmp_path) -> Path:
    p = tmp_path / "drawing.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.draw_rect(fitz.Rect(100, 100, 300, 300), fill=(0, 0, 0))
    doc.save(p)
    doc.close()
    return p


@pytest.fixture
def mixed_pdf(tmp_path) -> Path:
    p = tmp_path / "mixed.pdf"
    doc = fitz.open()
    t = doc.new_page()
    t.insert_text((72, 72), "Page one has real text content here")
    g = doc.new_page()
    g.draw_rect(fitz.Rect(100, 100, 300, 300), fill=(0, 0, 0))
    doc.save(p)
    doc.close()
    return p


@pytest.fixture
def simple_docx(tmp_path) -> Path:
    p = tmp_path / "report.docx"
    d = Document()
    d.add_heading("Business Case", level=0)
    d.add_paragraph("This project delivers value.")
    d.save(p)
    return p


@pytest.fixture
def simple_xlsx(tmp_path) -> Path:
    p = tmp_path / "data.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Inputs"
    ws["A1"] = "Region"
    ws["B1"] = "Capacity"
    ws["A2"] = "NSW"
    ws["B2"] = 1200
    wb.save(p)
    return p


@pytest.fixture
def messy_xlsx(tmp_path) -> Path:
    p = tmp_path / "messy.xlsx"
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "Title spanning header"
    ws.merge_cells("A1:C1")
    ws["A2"] = "Region"
    ws["B2"] = "Capacity"
    wb.save(p)
    return p


@pytest.fixture
def simple_kmz(tmp_path) -> Path:
    p = tmp_path / "zones.kmz"
    kml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        '<name>Indicative REZ Boundaries 2025</name>'
        '<Placemark><name>Zone A</name></Placemark>'
        '<Placemark><name>Zone B</name></Placemark>'
        '</Document></kml>'
    )
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("doc.kml", kml)
    return p
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_pdf.py`:

```python
from tlddr.extract.base import ExtractContext
from tlddr.extract.pdf import extract
from tlddr.models import SignalType, ExtractMethod


def test_born_digital_pdf_has_text(tmp_path, born_digital_pdf):
    ctx = ExtractContext(asset_dir=tmp_path / "assets")
    doc = extract(born_digital_pdf, ctx)
    assert doc.signal_type is SignalType.BORN_DIGITAL_REPORT
    assert doc.pages[0].has_text_layer is True
    assert doc.pages[0].method is ExtractMethod.PYMUPDF_TEXT
    assert "cost benefit" in doc.content.lower()


def test_image_only_pdf_routes_to_vision_with_thumbnail(tmp_path, image_only_pdf):
    ctx = ExtractContext(asset_dir=tmp_path / "assets")
    doc = extract(image_only_pdf, ctx)
    assert doc.signal_type is SignalType.DRAWING
    assert doc.pages[0].has_text_layer is False
    assert doc.pages[0].method is ExtractMethod.VISION
    assert doc.pages[0].thumbnail is not None
    assert (tmp_path / "assets").exists()
    assert any("image-only" in w.lower() for w in doc.warnings)


def test_mixed_pdf_is_mixed(tmp_path, mixed_pdf):
    ctx = ExtractContext(asset_dir=tmp_path / "assets")
    doc = extract(mixed_pdf, ctx)
    assert doc.signal_type is SignalType.MIXED
    assert len(doc.pages) == 2
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_pdf.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tlddr.extract.pdf'`.

- [ ] **Step 4: Implement `tlddr/extract/pdf.py`**

```python
from pathlib import Path
import fitz  # pymupdf
from tlddr.extract.base import ExtractContext
from tlddr.ids import doc_id, sha256_file
from tlddr.models import ExtractedDoc, PageProvenance, SignalType, ExtractMethod

TEXT_THRESHOLD = 10  # chars of stripped text to count a page as text-bearing
THUMBNAIL_SCALE = 0.3


def extract(path: Path, ctx: ExtractContext) -> ExtractedDoc:
    pdf = fitz.open(path)
    pages: list[PageProvenance] = []
    warnings: list[str] = []
    content_parts: list[str] = []
    did = doc_id(path)

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
    pdf.close()

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
```

- [ ] **Step 5: Register the extractor — append to `tlddr/extract/router.py`**

Add at the bottom of `tlddr/extract/router.py`:

```python
from tlddr.extract import pdf as _pdf

EXTRACTORS[".pdf"] = _pdf.extract
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_pdf.py -v`
Expected: PASS (3 passed).

- [ ] **Step 7: Commit**

```bash
git add tlddr/extract/pdf.py tlddr/extract/router.py tests/conftest.py tests/test_pdf.py
git commit -m "feat(extract): add pymupdf PDF extractor with text-layer routing"
```

---

### Task 4: DOCX extractor (mammoth)

**Files:**
- Create: `tlddr/extract/docx.py`
- Modify: `tlddr/extract/router.py` (register `.docx`)
- Test: `tests/test_docx.py`

**Interfaces:**
- Consumes: `ExtractContext`, `ExtractedDoc`, `doc_id`, `sha256_file`, `SignalType`, `ExtractMethod`
- Produces: `tlddr.extract.docx.extract(path: Path, ctx: ExtractContext) -> ExtractedDoc`. Converts to markdown via mammoth, sets `signal_type=BORN_DIGITAL_REPORT`, copies mammoth conversion messages into `warnings`. `pages=[]` (DOCX has no fixed pagination).

- [ ] **Step 1: Write the failing test**

Create `tests/test_docx.py`:

```python
from tlddr.extract.base import ExtractContext
from tlddr.extract.docx import extract
from tlddr.models import SignalType


def test_docx_extracts_markdown(tmp_path, simple_docx):
    ctx = ExtractContext(asset_dir=tmp_path / "assets")
    doc = extract(simple_docx, ctx)
    assert doc.signal_type is SignalType.BORN_DIGITAL_REPORT
    assert doc.extractor == "docx"
    assert "Business Case" in doc.content
    assert "value" in doc.content
    assert doc.pages == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_docx.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tlddr.extract.docx'`.

- [ ] **Step 3: Implement `tlddr/extract/docx.py`**

```python
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
```

- [ ] **Step 4: Register the extractor — append to `tlddr/extract/router.py`**

Add at the bottom of `tlddr/extract/router.py`:

```python
from tlddr.extract import docx as _docx

EXTRACTORS[".docx"] = _docx.extract
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_docx.py -v`
Expected: PASS (1 passed).

- [ ] **Step 6: Commit**

```bash
git add tlddr/extract/docx.py tlddr/extract/router.py tests/test_docx.py
git commit -m "feat(extract): add mammoth DOCX extractor"
```

---

### Task 5: XLSX extractor (openpyxl)

**Files:**
- Create: `tlddr/extract/xlsx.py`
- Modify: `tlddr/extract/router.py` (register `.xlsx`)
- Test: `tests/test_xlsx.py`

**Interfaces:**
- Consumes: `ExtractContext`, `ExtractedDoc`, `doc_id`, `sha256_file`, `SignalType`, `ExtractMethod`
- Produces: `tlddr.extract.xlsx.extract(path: Path, ctx: ExtractContext) -> ExtractedDoc`. Dumps each sheet's used range as a markdown-ish table into `content`; sets `signal_type=SPREADSHEET`; emits warnings for merged cells (`messy: sheet '<name>' has merged cells`). One `PageProvenance` per sheet with `method=OPENPYXL_XLSX`, `has_text_layer=True`, `page` = sheet index.

- [ ] **Step 1: Write the failing test**

Create `tests/test_xlsx.py`:

```python
from tlddr.extract.base import ExtractContext
from tlddr.extract.xlsx import extract
from tlddr.models import SignalType, ExtractMethod


def test_xlsx_dumps_sheet_content(tmp_path, simple_xlsx):
    ctx = ExtractContext(asset_dir=tmp_path / "assets")
    doc = extract(simple_xlsx, ctx)
    assert doc.signal_type is SignalType.SPREADSHEET
    assert "Region" in doc.content and "Capacity" in doc.content
    assert "NSW" in doc.content
    assert doc.pages[0].method is ExtractMethod.OPENPYXL_XLSX


def test_xlsx_warns_on_merged_cells(tmp_path, messy_xlsx):
    ctx = ExtractContext(asset_dir=tmp_path / "assets")
    doc = extract(messy_xlsx, ctx)
    assert any("merged" in w.lower() for w in doc.warnings)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_xlsx.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tlddr.extract.xlsx'`.

- [ ] **Step 3: Implement `tlddr/extract/xlsx.py`**

```python
from pathlib import Path
from openpyxl import load_workbook
from tlddr.extract.base import ExtractContext
from tlddr.ids import doc_id, sha256_file
from tlddr.models import ExtractedDoc, PageProvenance, SignalType, ExtractMethod

MAX_ROWS = 200  # cap dump per sheet for the reconnaissance report


def _cell(value: object) -> str:
    return "" if value is None else str(value)


def extract(path: Path, ctx: ExtractContext) -> ExtractedDoc:
    wb = load_workbook(path, data_only=True, read_only=False)
    parts: list[str] = []
    pages: list[PageProvenance] = []
    warnings: list[str] = []

    for index, ws in enumerate(wb.worksheets, start=1):
        parts.append(f"--- sheet: {ws.title} ---")
        rows = 0
        for row in ws.iter_rows(values_only=True):
            if rows >= MAX_ROWS:
                warnings.append(f"sheet '{ws.title}' truncated at {MAX_ROWS} rows")
                break
            line = " | ".join(_cell(v) for v in row)
            if line.strip(" |"):
                parts.append(line)
                rows += 1
        if ws.merged_cells.ranges:
            warnings.append(f"messy: sheet '{ws.title}' has merged cells")
        pages.append(PageProvenance(
            page=index, method=ExtractMethod.OPENPYXL_XLSX,
            has_text_layer=True, char_count=0,
        ))
    wb.close()

    return ExtractedDoc(
        id=doc_id(path),
        source_path=str(path),
        source_sha256=sha256_file(path),
        signal_type=SignalType.SPREADSHEET,
        raw_title=path.stem,
        content="\n".join(parts),
        pages=pages,
        warnings=warnings,
        extractor="xlsx",
    )
```

- [ ] **Step 4: Register the extractor — append to `tlddr/extract/router.py`**

Add at the bottom of `tlddr/extract/router.py`:

```python
from tlddr.extract import xlsx as _xlsx

EXTRACTORS[".xlsx"] = _xlsx.extract
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_xlsx.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add tlddr/extract/xlsx.py tlddr/extract/router.py tests/test_xlsx.py
git commit -m "feat(extract): add openpyxl XLSX extractor with messy-sheet warnings"
```

---

### Task 6: KMZ extractor (identity only)

**Files:**
- Create: `tlddr/extract/kmz.py`
- Modify: `tlddr/extract/router.py` (register `.kmz`)
- Test: `tests/test_kmz.py`

**Interfaces:**
- Consumes: `ExtractContext`, `ExtractedDoc`, `doc_id`, `sha256_file`, `SignalType`, `ExtractMethod`
- Produces: `tlddr.extract.kmz.extract(path: Path, ctx: ExtractContext) -> ExtractedDoc`. Unzips, reads the first `.kml`, pulls the Document `<name>` and counts `<Placemark>` elements (namespace-agnostic via local tag name). `content` is a one-line identity summary; `signal_type=GEOSPATIAL`; one `PageProvenance` with `method=KMZ_IDENTITY`, `has_text_layer=False`. No geometry parsed.

- [ ] **Step 1: Write the failing test**

Create `tests/test_kmz.py`:

```python
from tlddr.extract.base import ExtractContext
from tlddr.extract.kmz import extract
from tlddr.models import SignalType, ExtractMethod


def test_kmz_extracts_identity(tmp_path, simple_kmz):
    ctx = ExtractContext(asset_dir=tmp_path / "assets")
    doc = extract(simple_kmz, ctx)
    assert doc.signal_type is SignalType.GEOSPATIAL
    assert "Indicative REZ Boundaries 2025" in doc.content
    assert "2" in doc.content  # two placemarks counted
    assert doc.pages[0].method is ExtractMethod.KMZ_IDENTITY
    assert doc.pages[0].has_text_layer is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_kmz.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tlddr.extract.kmz'`.

- [ ] **Step 3: Implement `tlddr/extract/kmz.py`**

```python
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
```

- [ ] **Step 4: Register the extractor — append to `tlddr/extract/router.py`**

Add at the bottom of `tlddr/extract/router.py`:

```python
from tlddr.extract import kmz as _kmz

EXTRACTORS[".kmz"] = _kmz.extract
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_kmz.py -v`
Expected: PASS (1 passed).

- [ ] **Step 6: Commit**

```bash
git add tlddr/extract/kmz.py tlddr/extract/router.py tests/test_kmz.py
git commit -m "feat(extract): add identity-only KMZ extractor"
```

---

### Task 7: Extraction report renderer

**Files:**
- Create: `tlddr/extract/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `ExtractedDoc`
- Produces: `tlddr.extract.report.render_report(docs: list[ExtractedDoc]) -> str` — a markdown report with a summary table (id, signal_type, page count, warning count) followed by a per-document section (title, source, short sha, signal_type, per-page method summary, warnings, and an excerpt of `content`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_report.py`:

```python
from tlddr.extract.report import render_report
from tlddr.models import ExtractedDoc, PageProvenance, SignalType, ExtractMethod


def _doc():
    return ExtractedDoc(
        id="a6-cost-benefit-analysis",
        source_path="/x/a6.pdf",
        source_sha256="deadbeefcafe",
        signal_type=SignalType.MIXED,
        raw_title="A6 Cost Benefit Analysis",
        content="Executive summary of the cost benefit analysis.",
        pages=[
            PageProvenance(page=1, method=ExtractMethod.PYMUPDF_TEXT, has_text_layer=True, char_count=40),
            PageProvenance(page=2, method=ExtractMethod.VISION, has_text_layer=False, thumbnail="/x/t.png"),
        ],
        warnings=["page 2 image-only; would route to vision (not run in reconnaissance)"],
        extractor="pdf",
    )


def test_report_has_summary_and_detail():
    md = render_report([_doc()])
    assert "a6-cost-benefit-analysis" in md
    assert "mixed" in md
    assert "Executive summary" in md
    assert "image-only" in md
    assert "deadbeef" in md  # short sha shown


def test_report_handles_empty_list():
    md = render_report([])
    assert "0 documents" in md
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tlddr.extract.report'`.

- [ ] **Step 3: Implement `tlddr/extract/report.py`**

```python
from collections import Counter
from tlddr.models import ExtractedDoc

EXCERPT_CHARS = 800


def render_report(docs: list[ExtractedDoc]) -> str:
    lines: list[str] = []
    lines.append("# Extraction reconnaissance report")
    lines.append("")
    lines.append(f"{len(docs)} documents extracted.")
    lines.append("")

    if docs:
        lines.append("| id | signal_type | pages | warnings |")
        lines.append("|----|-------------|-------|----------|")
        for d in docs:
            lines.append(f"| {d.id} | {d.signal_type.value} | {len(d.pages)} | {len(d.warnings)} |")
        lines.append("")

    for d in docs:
        lines.append(f"## {d.id}")
        lines.append("")
        lines.append(f"- title: {d.raw_title}")
        lines.append(f"- source: {d.source_path}")
        lines.append(f"- sha256: {d.source_sha256[:12]}")
        lines.append(f"- signal_type: {d.signal_type.value}")
        lines.append(f"- extractor: {d.extractor}")
        method_counts = Counter(p.method.value for p in d.pages)
        if method_counts:
            summary = ", ".join(f"{m}: {n}" for m, n in sorted(method_counts.items()))
            lines.append(f"- page methods: {summary}")
        if d.warnings:
            lines.append("- warnings:")
            for w in d.warnings:
                lines.append(f"  - {w}")
        lines.append("")
        excerpt = d.content[:EXCERPT_CHARS]
        if excerpt:
            lines.append("```")
            lines.append(excerpt)
            lines.append("```")
        lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_report.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add tlddr/extract/report.py tests/test_report.py
git commit -m "feat(extract): add markdown extraction-report renderer"
```

---

### Task 8: CLI `extract` subcommand

**Files:**
- Create: `tlddr/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `route`, `ExtractContext`, `render_report`, `ExtractedDoc`
- Produces:
  - `tlddr.cli.run_extract(source: Path, out: Path) -> list[ExtractedDoc]` — walks `source` recursively for files, routes each, writes `out/extracted/<id>.json` per doc and `out/extraction-report.md`, returns the docs
  - `tlddr.cli.main(argv: list[str] | None = None) -> int` — argparse entry point with an `extract` subcommand (`--source`, `--out`, default out `.tlddr`)

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli.py`:

```python
from pathlib import Path
from tlddr.cli import run_extract, main


def test_run_extract_writes_json_and_report(tmp_path, born_digital_pdf, simple_docx, simple_kmz):
    source = tmp_path / "src"
    source.mkdir()
    for f in (born_digital_pdf, simple_docx, simple_kmz):
        (source / f.name).write_bytes(f.read_bytes())
    out = tmp_path / "out"

    docs = run_extract(source, out)

    assert len(docs) == 3
    assert (out / "extraction-report.md").exists()
    json_files = list((out / "extracted").glob("*.json"))
    assert len(json_files) == 3
    report = (out / "extraction-report.md").read_text()
    assert "born" in report


def test_main_extract_returns_zero(tmp_path, simple_docx):
    source = tmp_path / "src"
    source.mkdir()
    (source / simple_docx.name).write_bytes(simple_docx.read_bytes())
    out = tmp_path / "out"
    code = main(["extract", "--source", str(source), "--out", str(out)])
    assert code == 0
    assert (out / "extraction-report.md").exists()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tlddr.cli'`.

- [ ] **Step 3: Implement `tlddr/cli.py`**

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: PASS (all tests green, ~17 tests).

- [ ] **Step 6: Commit**

```bash
git add tlddr/cli.py tests/test_cli.py
git commit -m "feat(cli): add tlddr extract subcommand"
```

---

### Task 9: Reconnaissance run on the real corpus (manual verification)

This task runs no new code — it is the proving step the whole plan exists for. The deliverable is judgment, not a passing test.

**Files:**
- Create: `.tlddr/extraction-report.md` (generated; gitignored)

- [ ] **Step 1: Run extraction over the real corpus**

Run:
```bash
.venv/bin/tlddr extract --source "docs/test-reports/Engineering reports test" --out .tlddr
```
Expected: 20 lines of `extracted <id> [...]` output (13 pdf, 4 docx, 2 kmz, 1 xlsx) and a final summary line. No exceptions.

- [ ] **Step 2: Read the report and judge the signal**

Open `.tlddr/extraction-report.md` and check, against the source pile:

- Can you tell *what each document is and what it is about* from the extracted form alone? (the core make-or-break question)
- **Born-digital PDFs:** is the text clean and complete, or is it garbled/missing? Note any PDF that came back `DRAWING`/`MIXED` unexpectedly (could be a scanned or slide-deck export — a real signal-type finding).
- **The XLSX workbook** (`Draft 2026 ISP Inputs and Assumptions workbook.xlsx`): are the sheets legible? Did the messy-sheet warnings fire where they should?
- **The two KMZ files:** did identity (name + placemark count) come through?
- **`R972.pdf`:** what is it? Did it extract as text, or flag as image-only?
- **Any image-only pages:** confirm thumbnails were written under `.tlddr/thumbnails/` and warnings name the pages that "would route to vision".

- [ ] **Step 3: Record findings**

Write a short findings note (2-10 bullet points) summarising where the signal is strong, where it is weak, and which documents will need the vision path or a heavier table extractor later. This note feeds the next plan (Understand). No commit needed unless you choose to save the note under `docs/`.

---

## Self-review

**Spec coverage (extraction-relevant requirements only — this plan is scoped to proving step 1):**
- Route by signal type, not extension, with a uniform node shape -> Tasks 2-6 (router dispatches by extension to format extractors; each extractor sets the fine `signal_type` and all emit `ExtractedDoc`). Covered.
- Extraction seam contract `extract -> Node[stub]` -> `ExtractedDoc` + `Extractor` type alias (Tasks 1-2). Covered. (The eventual `Node` composes `ExtractedDoc`; deferred to the Understand plan per Global Constraints.)
- Per-page text-layer probe; text pages to text path, image-only to visual path -> Task 3. Covered.
- Drawings/KMZ as identity only, no geometry -> Tasks 3 (DRAWING + thumbnail) and 6 (KMZ identity). Covered.
- Spreadsheets tolerant of messy sheets, surfacing problems -> Task 5 (merged-cell + truncation warnings). Covered.
- Page = provenance unit, document = identity unit -> `ExtractedDoc.pages[]` vs one doc per file. Covered.
- Honesty: surface what could not be read -> `warnings` populated by every extractor; image-only pages flagged not silently dropped. Covered.
- No model calls in proving step 1 -> vision is flagged (`ExtractMethod.VISION`) but never invoked. Covered.
- Minimal dependency set -> only pymupdf/mammoth/openpyxl/pydantic at runtime. Covered.
- Staged, inspectable execution -> `tlddr extract` is a standalone subcommand writing JSON + a readable report (Task 8), then a manual reconnaissance run (Task 9). Covered.

**Deferred to later plans (intentionally not in this plan):** vault/TurboVault writes, the model seam (`LLMClient`), Understand-stage fields (`description`, `doc_type`, `report_sections`, `related`, confidences, `triage`), section profiles, drafting, assembly, quarantine. These depend on the model seam and/or on what the reconnaissance run reveals, per the spec's deferred-questions section.

**Placeholder scan:** No `TBD`/`TODO`/"add error handling"/"similar to Task N" present. Task 6 contains a deliberate simplification note (drop the no-op helper) with the exact replacement code shown, not a placeholder. Task 9 is intentionally a manual verification task with a concrete checklist, not code.

**Type consistency:** `ExtractedDoc`, `PageProvenance`, `ExtractContext`, `SignalType`, `ExtractMethod` member names, and the `extract(path, ctx) -> ExtractedDoc` signature are identical across Tasks 1-8. `route`, `run_extract`, `render_report` signatures match their consumers. Enum string values (`born_digital_report`, `pymupdf_text`, etc.) are used consistently in assertions and the report renderer.

---

## Notes for the next plan (Understand)

- Settle the `Confidence`, `Triage`, and `Depth` enums and the triage-derivation function against the real reconnaissance output.
- Introduce the model seam (`LLMClient`) — first real use is the vision description of the image-only pages flagged here.
- Compose `Node` from `ExtractedDoc` (hold it as a field) and add the Understand-stage fields; wire the validated edge write path and the TurboVault vault seam (live after session reload).
