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


# ---------------------------------------------------------------------------
# Fix 1: nested-table garbling in _table_rows
# ---------------------------------------------------------------------------

def test_nested_table_does_not_create_phantom_rows_or_ragged_columns(tmp_path):
    """Outer 1-row 2-col table whose 2nd cell contains a nested table.

    Expected: outer table renders as exactly header+separator+1 data row (3 pipe
    lines), separator has exactly 2 columns, and the inner table's text simply
    flattens into the parent cell via get_text.
    """
    html = (
        "<html><body>"
        "<table>"
        "<tr>"
        "<td>Col1</td>"
        "<td><table><tr><td>Inner1</td><td>Inner2</td></tr></table></td>"
        "</tr>"
        "</table>"
        "</body></html>"
    )
    doc = extract(_write(tmp_path, "nested.htm", html), ExtractContext(asset_dir=tmp_path / "a"))
    table_lines = [line for line in doc.content.split("\n") if line.startswith("|")]
    # 1 outer row renders as header + separator = 2 pipe lines.
    # The buggy code produces 3 (phantom inner row leaks as an extra data row).
    assert len(table_lines) == 2, (
        f"expected header+separator only (2 pipe lines, no phantom row), got {len(table_lines)}: "
        + repr(table_lines)
    )
    assert "| --- | --- |" in doc.content, "separator should show exactly 2 columns"
    assert "| --- | --- | --- |" not in doc.content, (
        "separator must not have 3+ columns (ragged column count)"
    )


def test_simple_non_nested_table_still_renders_correctly(tmp_path):
    """Regression: the existing simple-table test must stay green after the fix."""
    html = (
        "<html><body>"
        "<table>"
        "<tr><td>Risk</td><td>Mitigation</td></tr>"
        "<tr><td>Flood</td><td>Levee</td></tr>"
        "</table>"
        "</body></html>"
    )
    doc = extract(_write(tmp_path, "simple.htm", html), ExtractContext(asset_dir=tmp_path / "a"))
    assert "| Risk | Mitigation |" in doc.content
    assert "| Flood | Levee |" in doc.content


# ---------------------------------------------------------------------------
# Fix 2: _is_page_break false positives on `none` and `column-break-after`
# ---------------------------------------------------------------------------

def test_break_after_always_splits_pages(tmp_path):
    """CSS3 break-after:always must split into two pages (coverage regression)."""
    html = (
        "<html><body>"
        '<div style="break-after:always">CSS3 page one</div>'
        "<div>CSS3 page two</div>"
        "</body></html>"
    )
    doc = extract(_write(tmp_path, "ba.htm", html), ExtractContext(asset_dir=tmp_path / "a"))
    assert len(doc.pages) == 2, f"expected 2 pages, got {len(doc.pages)}"


def test_break_after_auto_does_not_split(tmp_path):
    """break-after:auto must not produce a page split."""
    html = (
        "<html><body>"
        '<div style="break-after:auto">Part one</div>'
        "<div>Part two</div>"
        "</body></html>"
    )
    doc = extract(_write(tmp_path, "baauto.htm", html), ExtractContext(asset_dir=tmp_path / "a"))
    assert len(doc.pages) == 1, f"expected 1 page, got {len(doc.pages)}"


def test_page_break_after_none_does_not_split(tmp_path):
    """page-break-after:none must not produce a page split (false-positive bug)."""
    html = (
        "<html><body>"
        '<div style="page-break-after:none">No break here</div>'
        "<div>Still on same page</div>"
        "</body></html>"
    )
    doc = extract(_write(tmp_path, "pbnone.htm", html), ExtractContext(asset_dir=tmp_path / "a"))
    assert len(doc.pages) == 1, f"expected 1 page, got {len(doc.pages)}"


def test_column_break_after_always_does_not_split_pages(tmp_path):
    """column-break-after:always must not trigger a page split (substring-match bug)."""
    html = (
        "<html><body>"
        '<div style="column-break-after:always">Column break only</div>'
        "<div>Next column content</div>"
        "</body></html>"
    )
    doc = extract(_write(tmp_path, "colba.htm", html), ExtractContext(asset_dir=tmp_path / "a"))
    assert len(doc.pages) == 1, f"expected 1 page, got {len(doc.pages)}"


def test_webkit_column_break_after_always_does_not_split_pages(tmp_path):
    """-webkit-column-break-after:always must not trigger a page split."""
    html = (
        "<html><body>"
        '<div style="-webkit-column-break-after:always">Webkit col break</div>'
        "<div>Next section</div>"
        "</body></html>"
    )
    doc = extract(_write(tmp_path, "wkcolba.htm", html), ExtractContext(asset_dir=tmp_path / "a"))
    assert len(doc.pages) == 1, f"expected 1 page, got {len(doc.pages)}"
