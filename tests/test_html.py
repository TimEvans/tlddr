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
