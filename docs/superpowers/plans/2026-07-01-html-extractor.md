# HTML Extractor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a faithful `.htm`/`.html` (incl. Workiva inline-XBRL) extractor wired into the extraction router, so SEC filings extract to the same `ExtractedDoc` the pipeline reads.

**Architecture:** Parse with BeautifulSoup on an lxml backend. Strip script/style + the hidden iXBRL header, unwrap inline `ix:*` tags, walk the body in document order yielding a token stream (text / markdown-table / page-break), then assemble numbered pages from `page-break-after` boundaries. Table rendering is a shared helper reused from the DOCX extractor. A documented skip predicate in the source walk drops SEC machine-generated boilerplate (the 133 duplicate XBRL `R*.htm` fragments + index/linkbase files).

**Tech Stack:** Python 3.11+, BeautifulSoup4 (lxml backend), pydantic, pytest.

**Spec:** `docs/superpowers/specs/2026-07-01-html-extractor-design.md`

## Global Constraints

- Python `>=3.11`. Run tests with `.venv/bin/pytest`.
- Dependencies after this slice: `pydantic>=2.6`, `pymupdf>=1.24`, `python-docx>=1.1`, `openpyxl>=3.1`, `pyyaml>=6.0`, **`beautifulsoup4>=4.12`**, **`lxml>=5.0`**.
- No emojis anywhere (code, comments, commits) — hard rule.
- Conventional commits (`type(scope): description`).
- Faithful extraction: no model calls; capture content + page provenance, never fabricate.
- Invariant (from the proving run): emit `--- page N ---` markers **iff** `pages[]` is populated.
- Branch `html-extractor` off `main` before Task 1; do not commit to `main`.

---

### Task 1: Shared table-markdown helper

Lift the DOCX extractor's private table helpers into a shared module so HTML can reuse them. Behaviour must be byte-identical so existing DOCX tests stay green.

**Files:**
- Create: `tlddr/extract/tables.py`
- Modify: `tlddr/extract/docx.py` (replace `_clean_cell`/`_table_markdown` with imports)
- Test: `tests/test_extract_tables.py` (new), `tests/test_docx.py` (regression, unchanged)

**Interfaces:**
- Produces: `clean_cell(text: str) -> str`; `table_markdown(rows: list[list[str]]) -> str` (rows are raw cell strings; the helper cleans them internally).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_extract_tables.py
from tlddr.extract.tables import clean_cell, table_markdown


def test_clean_cell_escapes_pipes_and_collapses_newlines():
    assert clean_cell("a|b\nc") == "a\\|b c"


def test_table_markdown_renders_header_separator_and_rows():
    md = table_markdown([["Risk", "Mitigation"], ["Flood", "Levee upgrade"]])
    assert md == (
        "| Risk | Mitigation |\n"
        "| --- | --- |\n"
        "| Flood | Levee upgrade |"
    )


def test_table_markdown_empty_is_blank():
    assert table_markdown([]) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_extract_tables.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tlddr.extract.tables'`

- [ ] **Step 3: Write minimal implementation**

```python
# tlddr/extract/tables.py
def clean_cell(text: str) -> str:
    # Keep each table row on one line and avoid breaking the markdown table.
    return text.replace("|", "\\|").replace("\n", " ").strip()


def table_markdown(rows: list[list[str]]) -> str:
    cleaned = [[clean_cell(cell) for cell in row] for row in rows]
    if not cleaned:
        return ""
    width = len(cleaned[0])
    lines = ["| " + " | ".join(cleaned[0]) + " |"]
    lines.append("| " + " | ".join(["---"] * width) + " |")
    for row in cleaned[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)
```

- [ ] **Step 4: Refactor docx.py to use the shared helper**

In `tlddr/extract/docx.py`, delete the `_clean_cell` function and replace `_table_markdown` so it delegates to the shared helper (the DOCX `Table` -> rows extraction stays in docx.py):

```python
from tlddr.extract.tables import table_markdown as _render_table
```

Add this import near the other `tlddr` imports, delete `_clean_cell` (lines defining it) and `_table_markdown`, and replace the table-rendering call site:

```python
def _table_markdown(table: Table) -> str:
    rows = [[cell.text for cell in row.cells] for row in table.rows]
    return _render_table(rows)
```

(The cleaning now happens inside `_render_table`; `_table_markdown` only extracts raw cell text.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_extract_tables.py tests/test_docx.py -v`
Expected: PASS (new helper tests + unchanged DOCX regression tests, including `test_docx_extracts_table_cells_in_document_order`)

- [ ] **Step 6: Commit**

```bash
git add tlddr/extract/tables.py tlddr/extract/docx.py tests/test_extract_tables.py
git commit -m "refactor(extract): extract shared table-markdown helper from docx"
```

---

### Task 2: Declare dependencies and install

Add the parser dependencies so `html.py` can import BeautifulSoup, and declare `lxml` (now a direct dependency).

**Files:**
- Modify: `pyproject.toml:6-12` (the `dependencies` array)

- [ ] **Step 1: Add the dependencies**

In `pyproject.toml`, change the `dependencies` array to:

```toml
dependencies = [
    "pydantic>=2.6",
    "pymupdf>=1.24",
    "python-docx>=1.1",
    "openpyxl>=3.1",
    "pyyaml>=6.0",
    "beautifulsoup4>=4.12",
    "lxml>=5.0",
]
```

- [ ] **Step 2: Install into the venv**

Run: `.venv/bin/pip install -e ".[dev]"`
Expected: installs `beautifulsoup4` (and confirms `lxml` already present), no errors.

- [ ] **Step 3: Verify the import works**

Run: `.venv/bin/python -c "from bs4 import BeautifulSoup; print(BeautifulSoup('<p>hi</p>', 'lxml').get_text())"`
Expected: prints `hi`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore(deps): add beautifulsoup4 and declare lxml for HTML extractor"
```

---

### Task 3: HTML extractor core (single page, no pagination yet)

Build `tlddr/extract/html.py` to parse HTML/iXBRL into faithful text + markdown tables as a **single** page. Page-break splitting comes in Task 4.

**Files:**
- Create: `tlddr/extract/html.py`
- Test: `tests/test_html.py` (new)

**Interfaces:**
- Consumes: `clean_cell`/`table_markdown` from Task 1; `ExtractContext`; `doc_id`/`sha256_file`; `ExtractedDoc`/`PageProvenance`/`SignalType`/`ExtractMethod`.
- Produces: `extract(path: Path, ctx: ExtractContext) -> ExtractedDoc`; module-level helpers `_tokens(node)`, `_table_rows(table)`, `_has_block_child(tag)`, `BLOCK_TAGS`.
- Requires: `ExtractMethod.HTML_TEXT` (added in this task's Step 3).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_html.py
from pathlib import Path

from tlddr.extract.base import ExtractContext
from tlddr.extract.html import extract
from tlddr.models import SignalType, ExtractMethod


def _write(tmp_path: Path, name: str, html: str) -> Path:
    p = tmp_path / name
    p.write_bytes(html.encode("utf-8"))
    return p


def test_ixbrl_header_dropped_and_inline_facts_kept(tmp_path):
    html = (
        "<html><head><title>cvx-20251231</title></head><body>"
        '<div style="display:none"><ix:header><ix:hidden>'
        '<ix:nonNumeric name="dei:EntityRegistrantName">SECRET METADATA</ix:nonNumeric>'
        "</ix:hidden></ix:header></div>"
        "<div>Total revenues "
        '<ix:nonFraction name="us-gaap:Revenues">193,414</ix:nonFraction>'
        " million</div>"
        "</body></html>"
    )
    doc = extract(_write(tmp_path, "f.htm", html), ExtractContext(asset_dir=tmp_path / "a"))
    assert "SECRET METADATA" not in doc.content
    assert "Total revenues 193,414 million" in doc.content
    assert doc.signal_type is SignalType.BORN_DIGITAL_REPORT
    assert doc.extractor == "html"


def test_title_from_tag_then_falls_back_to_stem(tmp_path):
    with_title = extract(_write(tmp_path, "a.htm", "<html><head><title>My 10-K</title></head><body><p>x</p></body></html>"),
                         ExtractContext(asset_dir=tmp_path / "a"))
    assert with_title.raw_title == "My 10-K"
    no_title = extract(_write(tmp_path, "stemname.htm", "<html><body><p>x</p></body></html>"),
                       ExtractContext(asset_dir=tmp_path / "a"))
    assert no_title.raw_title == "stemname"


def test_blocks_are_separated_not_run_together(tmp_path):
    doc = extract(_write(tmp_path, "b.htm", "<html><body><div>First block</div><div>Second block</div></body></html>"),
                  ExtractContext(asset_dir=tmp_path / "a"))
    assert "First block\n\nSecond block" in doc.content


def test_table_rendered_as_markdown_inline(tmp_path):
    html = (
        "<html><body><p>Before</p>"
        "<table><tr><td>Risk</td><td>Mitigation</td></tr>"
        "<tr><td>Flood</td><td>Levee</td></tr></table>"
        "<p>After</p></body></html>"
    )
    doc = extract(_write(tmp_path, "t.htm", html), ExtractContext(asset_dir=tmp_path / "a"))
    assert "| Risk | Mitigation |" in doc.content
    assert doc.content.index("Before") < doc.content.index("Flood") < doc.content.index("After")


def test_single_page_when_no_breaks(tmp_path):
    doc = extract(_write(tmp_path, "s.htm", "<html><body><p>Only content here</p></body></html>"),
                  ExtractContext(asset_dir=tmp_path / "a"))
    assert len(doc.pages) == 1
    assert doc.pages[0].page == 1
    assert doc.pages[0].method is ExtractMethod.HTML_TEXT
    assert doc.pages[0].has_text_layer is True
    assert doc.content.startswith("--- page 1 ---")
    assert doc.pages[0].char_count == len("Only content here")


def test_empty_body_is_unknown_with_warning(tmp_path):
    doc = extract(_write(tmp_path, "e.htm", "<html><body></body></html>"),
                  ExtractContext(asset_dir=tmp_path / "a"))
    assert doc.signal_type is SignalType.UNKNOWN
    assert doc.content == ""
    assert doc.pages == []
    assert any("no extractable text" in w.lower() for w in doc.warnings)


def test_embedded_images_counted_as_warning(tmp_path):
    doc = extract(_write(tmp_path, "i.htm", "<html><body><p>text</p><img src='x.jpg'><img src='y.jpg'></body></html>"),
                  ExtractContext(asset_dir=tmp_path / "a"))
    image_warnings = [w for w in doc.warnings if "embedded image" in w]
    assert image_warnings and "2" in image_warnings[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_html.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tlddr.extract.html'`

- [ ] **Step 3: Add the `HTML_TEXT` extract method**

In `tlddr/models.py`, add to the `ExtractMethod` enum (after `KMZ_IDENTITY`):

```python
    HTML_TEXT = "html_text"
```

- [ ] **Step 4: Write the extractor (single-page)**

```python
# tlddr/extract/html.py
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

from tlddr.extract.base import ExtractContext
from tlddr.extract.tables import table_markdown
from tlddr.ids import doc_id, sha256_file
from tlddr.models import ExtractedDoc, ExtractMethod, PageProvenance, SignalType

# Block-level tags whose boundaries become paragraph breaks in the output.
BLOCK_TAGS = {
    "p", "div", "li", "ul", "ol", "table", "tr", "section", "article",
    "header", "footer", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6",
}


def _has_block_child(tag: Tag) -> bool:
    # Direct-children check only: O(n) overall, fast on a multi-MB filing.
    return any(
        isinstance(child, Tag) and (child.name or "").lower() in BLOCK_TAGS
        for child in tag.children
    )


def _table_rows(table: Tag) -> list[list[str]]:
    rows = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        rows.append([cell.get_text(" ", strip=True) for cell in cells])
    return rows


def _tokens(node):
    """Yield ('text', s) and ('table', markdown) in document order."""
    for child in node.children:
        if isinstance(child, NavigableString):
            text = str(child).strip()
            if text:
                yield ("text", text)
            continue
        if not isinstance(child, Tag):
            continue
        name = (child.name or "").lower()
        if name == "table":
            markdown = table_markdown(_table_rows(child))
            if markdown:
                yield ("table", markdown)
            continue
        if name in BLOCK_TAGS and _has_block_child(child):
            yield from _tokens(child)
            continue
        text = child.get_text(" ", strip=True)
        if text:
            yield ("text", text)


def _strip_ixbrl(soup: BeautifulSoup) -> None:
    for tag in soup(["script", "style"]):
        tag.decompose()
    for tag in soup.find_all(["ix:header", "ix:hidden"]):
        tag.decompose()
    for tag in soup.find_all(lambda t: t.name and t.name.lower().startswith("ix:")):
        tag.unwrap()


def _title(soup: BeautifulSoup, path: Path) -> str:
    title_tag = soup.find("title")
    if title_tag:
        text = title_tag.get_text(strip=True)
        if text:
            return text
    return path.stem


def extract(path: Path, ctx: ExtractContext) -> ExtractedDoc:
    soup = BeautifulSoup(path.read_bytes(), "lxml")
    _strip_ixbrl(soup)
    raw_title = _title(soup, path)
    body = soup.body or soup

    parts = [value for _, value in _tokens(body)]
    page_texts = ["\n\n".join(parts).strip()] if any(parts) else []

    warnings: list[str] = []
    image_count = len(body.find_all("img"))
    if image_count:
        warnings.append(
            f"{image_count} embedded image(s) present, not extracted (identity only)"
        )

    if not page_texts:
        warnings.append("no extractable text found")
        return ExtractedDoc(
            id=doc_id(path), source_path=str(path), source_sha256=sha256_file(path),
            signal_type=SignalType.UNKNOWN, raw_title=raw_title, content="",
            pages=[], warnings=warnings, extractor="html",
        )

    content = "\n\n".join(f"--- page {i} ---\n{t}" for i, t in enumerate(page_texts, 1))
    pages = [
        PageProvenance(
            page=i, method=ExtractMethod.HTML_TEXT,
            has_text_layer=True, char_count=len(t),
        )
        for i, t in enumerate(page_texts, 1)
    ]
    return ExtractedDoc(
        id=doc_id(path), source_path=str(path), source_sha256=sha256_file(path),
        signal_type=SignalType.BORN_DIGITAL_REPORT, raw_title=raw_title,
        content=content, pages=pages, warnings=warnings, extractor="html",
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_html.py -v`
Expected: PASS (all 7 tests)

- [ ] **Step 6: Commit**

```bash
git add tlddr/extract/html.py tlddr/models.py tests/test_html.py
git commit -m "feat(extract): HTML/iXBRL extractor core (faithful text + tables)"
```

---

### Task 4: Page synthesis from `page-break-after`

Split the token stream into numbered pages on `page-break-after`/`break-after` boundaries (value other than `avoid`/`auto`). One page when there are no boundaries (already true from Task 3).

**Files:**
- Modify: `tlddr/extract/html.py` (add `_is_page_break`, emit `("break", "")` tokens, assemble multiple pages)
- Test: `tests/test_html.py` (add page-split tests)

**Interfaces:**
- Produces: `_is_page_break(tag: Tag) -> bool`; `_tokens` now also yields `("break", "")`.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_html.py
def test_page_break_after_splits_into_pages(tmp_path):
    html = (
        "<html><body>"
        '<div style="page-break-after:always">Page one body</div>'
        '<div style="page-break-after:always">Page two body</div>'
        "<div>Page three body</div>"
        "</body></html>"
    )
    doc = extract(_write(tmp_path, "p.htm", html), ExtractContext(asset_dir=tmp_path / "a"))
    assert len(doc.pages) == 3
    assert [p.page for p in doc.pages] == [1, 2, 3]
    assert "--- page 1 ---\nPage one body" in doc.content
    assert "--- page 2 ---\nPage two body" in doc.content
    assert "--- page 3 ---\nPage three body" in doc.content
    assert doc.pages[0].char_count == len("Page one body")


def test_page_break_avoid_does_not_split(tmp_path):
    html = (
        "<html><body>"
        '<div style="page-break-after:avoid">Stays together one</div>'
        "<div>Stays together two</div>"
        "</body></html>"
    )
    doc = extract(_write(tmp_path, "av.htm", html), ExtractContext(asset_dir=tmp_path / "a"))
    assert len(doc.pages) == 1


def test_trailing_content_after_last_break_is_its_own_page(tmp_path):
    html = (
        "<html><body>"
        '<div style="page-break-after:always">First</div>'
        "<p>Trailing</p>"
        "</body></html>"
    )
    doc = extract(_write(tmp_path, "tr.htm", html), ExtractContext(asset_dir=tmp_path / "a"))
    assert len(doc.pages) == 2
    assert "--- page 2 ---\nTrailing" in doc.content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_html.py -k "page_break or trailing" -v`
Expected: FAIL (`test_page_break_after_splits_into_pages` finds 1 page, not 3)

- [ ] **Step 3: Add `_is_page_break` and emit break tokens**

In `tlddr/extract/html.py`, add the helper (after `_has_block_child`):

```python
def _is_page_break(tag: Tag) -> bool:
    style = (tag.get("style") or "").replace(" ", "").lower()
    for prop in ("page-break-after:", "break-after:"):
        if prop in style:
            value = style.split(prop, 1)[1].split(";", 1)[0]
            if value not in ("avoid", "auto", ""):
                return True
    return False
```

Then in `_tokens`, emit a break token after a table and after a block element that carries a page break. Update the `table` branch and the block-recursion branch:

```python
        if name == "table":
            markdown = table_markdown(_table_rows(child))
            if markdown:
                yield ("table", markdown)
            if _is_page_break(child):
                yield ("break", "")
            continue
        if name in BLOCK_TAGS and _has_block_child(child):
            yield from _tokens(child)
            if _is_page_break(child):
                yield ("break", "")
            continue
        text = child.get_text(" ", strip=True)
        if text:
            yield ("text", text)
        if _is_page_break(child):
            yield ("break", "")
```

- [ ] **Step 4: Assemble multiple pages in `extract`**

Replace the single-page assembly line in `extract`:

```python
    parts = [value for _, value in _tokens(body)]
    page_texts = ["\n\n".join(parts).strip()] if any(parts) else []
```

with break-aware assembly:

```python
    page_texts: list[str] = []
    current: list[str] = []
    for kind, value in _tokens(body):
        if kind == "break":
            text = "\n\n".join(current).strip()
            if text:
                page_texts.append(text)
            current = []
        else:
            current.append(value)
    text = "\n\n".join(current).strip()
    if text:
        page_texts.append(text)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_html.py -v`
Expected: PASS (all Task 3 + Task 4 tests)

- [ ] **Step 6: Commit**

```bash
git add tlddr/extract/html.py tests/test_html.py
git commit -m "feat(extract): synthesize page provenance from page-break-after"
```

---

### Task 5: Wire the extractor into the router

Register `.htm` and `.html` so `route()` dispatches them to the HTML extractor.

**Files:**
- Modify: `tlddr/extract/router.py:37-39` (after the kmz registration)
- Test: `tests/test_router.py` (add dispatch test)

**Interfaces:**
- Consumes: `tlddr.extract.html.extract` from Task 3.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_router.py
def test_route_dispatches_htm_and_html_to_html_extractor(tmp_path):
    ctx = ExtractContext(asset_dir=tmp_path)
    for name in ("doc.htm", "doc.HTML"):
        f = tmp_path / name
        f.write_bytes(b"<html><body><p>hello world content</p></body></html>")
        result = router.route(f, ctx)
        assert result.extractor == "html"
        assert "hello world content" in result.content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_router.py::test_route_dispatches_htm_and_html_to_html_extractor -v`
Expected: FAIL (routes to UNKNOWN; `result.extractor == "none"`)

- [ ] **Step 3: Register the extractor**

In `tlddr/extract/router.py`, append after the kmz block:

```python
from tlddr.extract import html as _html

EXTRACTORS[".htm"] = _html.extract
EXTRACTORS[".html"] = _html.extract
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_router.py -v`
Expected: PASS (new dispatch test + existing router tests)

- [ ] **Step 5: Commit**

```bash
git add tlddr/extract/router.py tests/test_router.py
git commit -m "feat(extract): route .htm/.html to the HTML extractor"
```

---

### Task 6: Skip SEC machine-generated boilerplate in the source walk

Add a documented predicate so `run_extract` skips the 133 duplicate XBRL `R*.htm` fragments and the filing-manifest/linkbase files.

**Files:**
- Modify: `tlddr/cli.py` (add `_is_sec_boilerplate`; apply it in `run_extract`'s walk near line 30)
- Test: `tests/test_cli.py` (add predicate + walk-skip tests)

**Interfaces:**
- Produces: `_is_sec_boilerplate(path: Path) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_cli.py
import re
from pathlib import Path
from tlddr.cli import _is_sec_boilerplate


def test_is_sec_boilerplate_matches_machine_generated_artifacts():
    for name in (
        "R12.htm", "R1.htm", "R133.htm",
        "0000093410-26-000078-index.html",
        "0000093410-26-000078-index-headers.html",
        "FilingSummary.xml",
        "cvx-20251231_cal.xml", "cvx-20251231_def.xml",
        "cvx-20251231_lab.xml", "cvx-20251231_pre.xml",
        "cvx-20251231.xsd",
        "0000093410-26-000078-xbrl.zip",
    ):
        assert _is_sec_boilerplate(Path("/x") / name), name


def test_is_sec_boilerplate_keeps_real_content():
    for name in ("cvx-20251231.htm", "a12312025ex19.htm", "report.pdf", "notes.docx"):
        assert not _is_sec_boilerplate(Path("/x") / name), name


def test_run_extract_skips_boilerplate(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "cvx-20251231.htm").write_bytes(b"<html><body><p>Real filing content</p></body></html>")
    (source / "R12.htm").write_bytes(b"<html><body><p>Duplicate XBRL fragment</p></body></html>")
    (source / "FilingSummary.xml").write_bytes(b"<xml/>")
    out = tmp_path / "out"
    from tlddr.cli import run_extract
    docs = run_extract(source, out)
    titles = {d.source_path for d in docs}
    assert any("cvx-20251231.htm" in t for t in titles)
    assert not any("R12.htm" in t for t in titles)
    assert not any("FilingSummary.xml" in t for t in titles)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_cli.py -k "boilerplate" -v`
Expected: FAIL with `ImportError: cannot import name '_is_sec_boilerplate'`

- [ ] **Step 3: Implement the predicate and apply it in the walk**

In `tlddr/cli.py`, add the predicate above `run_extract`:

```python
import re

# SEC EDGAR ships each filing with machine-generated companions that duplicate
# the primary document's content or describe the filing package itself. We skip
# them so the corpus holds one faithful copy of each fact, not many:
#   - R\d+.htm        : the XBRL viewer's re-render of facts already inline in
#                       the primary document (133 of them in the Chevron 10-K).
#   - *-index*.html   : the filing index / manifest pages.
#   - FilingSummary.xml, *_cal/_def/_lab/_pre.xml, *.xsd, *-xbrl.zip : the XBRL
#                       linkbases and schema, not human-readable content.
_BOILERPLATE_PATTERNS = (
    re.compile(r"^R\d+\.htm$", re.IGNORECASE),
    re.compile(r"-index(-headers)?\.html$", re.IGNORECASE),
    re.compile(r"^FilingSummary\.xml$", re.IGNORECASE),
    re.compile(r"_(cal|def|lab|pre)\.xml$", re.IGNORECASE),
    re.compile(r"\.xsd$", re.IGNORECASE),
    re.compile(r"\.zip$", re.IGNORECASE),
)


def _is_sec_boilerplate(path: Path) -> bool:
    name = path.name
    return any(pattern.search(name) for pattern in _BOILERPLATE_PATTERNS)
```

Then in `run_extract`, change the file walk (line 30) to filter:

```python
    files = sorted(
        p for p in source.rglob("*")
        if p.is_file() and not _is_sec_boilerplate(p)
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: PASS (boilerplate tests + existing CLI tests)

- [ ] **Step 5: Commit**

```bash
git add tlddr/cli.py tests/test_cli.py
git commit -m "feat(extract): skip SEC machine-generated boilerplate in source walk"
```

---

### Task 7: Update the module index and run the full suite

Document the new modules and confirm the whole suite is green.

**Files:**
- Modify: `tlddr/extract/CLAUDE.md` (add `tables.py` and `html.py` entries; note `.htm`/`.html` routing)

- [ ] **Step 1: Update the extract module index**

In `tlddr/extract/CLAUDE.md`, add entries (keep the existing house style — no emojis):

```markdown
### html.py
**Purpose:** HTML/iXBRL extractor (BeautifulSoup + lxml). Strips script/style + hidden ix:header, unwraps inline ix:* tags, renders block text + markdown tables in document order, synthesizes page provenance from page-break-after boundaries.
**Key Functions:** `extract(path, ctx) -> ExtractedDoc`; helpers `_tokens`, `_is_page_break`, `_has_block_child`, `_table_rows`, `_strip_ixbrl`, `_title`
**Constants:** `BLOCK_TAGS`
**Dependencies:** bs4 (BeautifulSoup, lxml backend), tlddr.extract.tables

### tables.py
**Purpose:** Shared markdown-table rendering for the docx and html extractors.
**Key Functions:** `clean_cell(text) -> str`, `table_markdown(rows) -> str`
```

Also update the `router.py` entry's `EXTRACTORS` note to mention `.htm`/`.html`, and the `docx.py` entry to note it now reuses `tables.py`.

- [ ] **Step 2: Run the full test suite**

Run: `.venv/bin/pytest -q`
Expected: PASS — all prior tests (96) plus the new tables/html/router/cli tests, no failures.

- [ ] **Step 3: Commit**

```bash
git add tlddr/extract/CLAUDE.md
git commit -m "docs(extract): index html.py and shared tables.py modules"
```

---

## Self-review

**Spec coverage:**
- D1 parser (BeautifulSoup+lxml) -> Task 2 (deps) + Task 3 (parse). Covered.
- D2 page provenance (synthesize from page-break-after, fallback page 1, `HTML_TEXT`) -> Task 3 (single page + enum) + Task 4 (splitting). Covered.
- D3 structure (strip ix:header, unwrap ix:, blocks + markdown tables, no heading inference) -> Task 1 (tables) + Task 3 (`_strip_ixbrl`, `_tokens`). Covered.
- D4 file scope (skip predicate in walk) -> Task 6. Covered.
- Signal-type consequence (BORN_DIGITAL_REPORT / UNKNOWN) -> Task 3 tests. Covered.
- Router wiring `.htm`/`.html` -> Task 5. Covered.
- Embedded-image warning -> Task 3 test. Covered.
- Defensive empty body -> Task 3 `test_empty_body_is_unknown_with_warning`. Covered.
- Deps declared (bs4 + lxml) -> Task 2. Covered.
- Module index doc -> Task 7. Covered.

**Placeholder scan:** No TBD/TODO; every code step shows complete code; every test step shows the test body.

**Type consistency:** `extract(path, ctx) -> ExtractedDoc`, `_tokens(node)` yields `(kind, value)` tuples consumed identically in Task 3/4, `clean_cell`/`table_markdown` signatures match Task 1 definitions and Task 3 usage, `_is_sec_boilerplate(path) -> bool` matches Task 6 import. `ExtractMethod.HTML_TEXT` defined in Task 3 Step 3, used in Task 3 Step 4 + Task 4 tests. Consistent.
