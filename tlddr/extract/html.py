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


def _is_page_break(tag: Tag) -> bool:
    style = (tag.get("style") or "").replace(" ", "").lower()
    for prop in ("page-break-after:", "break-after:"):
        if prop in style:
            value = style.split(prop, 1)[1].split(";", 1)[0]
            if value not in ("avoid", "auto", ""):
                return True
    return False


def _table_rows(table: Tag) -> list[list[str]]:
    rows = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        rows.append([cell.get_text(" ", strip=True) for cell in cells])
    return rows


def _tokens(node):
    """Yield ('text', s), ('table', markdown), and ('break', '') in document order."""
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
