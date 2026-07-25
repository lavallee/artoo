"""The conservative Markdown converter used by the notebook-report generator."""

from artoo.generators.notebook_report import markdown as md


def test_headings_and_paragraphs():
    out = md.to_html("# Title\n\nA paragraph of text.\n\nAnother one.")
    assert "<h1>Title</h1>" in out
    assert "<p>A paragraph of text.</p>" in out
    assert "<p>Another one.</p>" in out


def test_soft_wrapped_paragraph_is_joined():
    out = md.to_html("one line\nsecond line")
    assert "<p>one line second line</p>" in out


def test_unordered_and_ordered_lists():
    out = md.to_html("- a\n- b\n\n1. first\n2. second")
    assert "<ul>\n<li>a</li>\n<li>b</li>\n</ul>" in out
    assert "<ol>\n<li>first</li>\n<li>second</li>\n</ol>" in out


def test_inline_markup():
    out = md.to_html("**bold** and *italic* and `code` and [link](https://x.test).")
    assert "<strong>bold</strong>" in out
    assert "<em>italic</em>" in out
    assert "<code>code</code>" in out
    assert '<a href="https://x.test">link</a>' in out


def test_fenced_code_is_escaped_verbatim():
    out = md.to_html("```python\nprint('<x>')\n```")
    assert "<pre><code" in out
    assert "&lt;x&gt;" in out
    # Markup inside a code fence is not interpreted.
    assert "<strong>" not in md.to_html("```\n**not bold**\n```")


def test_html_is_escaped():
    out = md.to_html("a < b & c > d")
    assert "&lt;" in out and "&amp;" in out and "&gt;" in out


def test_bracket_claim_refs_are_left_untouched():
    # [C7] carries no (url): the link rule must skip it so the kit can anchor it.
    out = md.to_html("The result [C7] holds.")
    assert "[C7]" in out
    assert "<a" not in out


def test_blockquote_and_hr():
    out = md.to_html("> quoted\n\n---")
    assert "<blockquote><p>quoted</p></blockquote>" in out
    assert "<hr>" in out


def test_code_span_protects_special_chars():
    out = md.to_html("use `a && b` here")
    assert "<code>a &amp;&amp; b</code>" in out
