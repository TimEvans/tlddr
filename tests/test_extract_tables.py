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
