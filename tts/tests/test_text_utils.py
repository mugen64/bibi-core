from utils.text import strip_markdown


def test_empty_string_passes_through():
    assert strip_markdown("") == ""


def test_strips_bold_and_italic():
    assert strip_markdown("**bold** and *italic*") == "bold and italic"


def test_strips_headers_and_list_markers():
    assert strip_markdown("# Title\n- one\n- two") == "Title\none\ntwo"


def test_strips_links_keeping_the_label():
    assert strip_markdown("see [the docs](https://example.com)") == "see the docs"


def test_strips_inline_code_and_strikethrough():
    assert strip_markdown("run `ls -la` not ~~rm -rf~~") == "run ls -la not rm -rf"


def test_collapses_repeated_spaces_left_by_stripped_symbols():
    assert strip_markdown("a **  ** b") == "a b"
