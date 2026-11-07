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


def test_image_alone_in_a_paragraph_is_a_figure():
    out = md.to_html('Intro.\n\n![The index page](assets/index.png "Every canvas, with a *preview*")\n\nAfter.')
    assert (
        '<figure class="article-figure"><img src="assets/index.png" alt="The index page" loading="lazy">'
        "<figcaption>Every canvas, with a <em>preview</em></figcaption></figure>"
    ) in out
    assert "<p>Intro.</p>" in out and "<p>After.</p>" in out


def test_figure_without_caption_has_no_figcaption():
    out = md.to_html("![A chart](chart.svg)")
    assert out == '<figure class="article-figure"><img src="chart.svg" alt="A chart" loading="lazy"></figure>'


def test_inline_image_stays_in_its_paragraph():
    out = md.to_html("Click ![the gear](gear.svg) then [save](https://x.test).")
    assert out == (
        '<p>Click <img src="gear.svg" alt="the gear" loading="lazy"> then '
        '<a href="https://x.test">save</a>.</p>'
    )


def test_image_attributes_are_escaped():
    out = md.to_html('![Tom & "Jerry" <3](a.png?x=1&y=2)')
    assert 'alt="Tom &amp; &quot;Jerry&quot; &lt;3"' in out
    assert 'src="a.png?x=1&amp;y=2"' in out


def test_image_syntax_in_code_is_literal():
    out = md.to_html("`![not](img.png)`")
    assert "<img" not in out
    assert "<code>![not](img.png)</code>" in out


def test_video_figure_is_a_named_silent_loop():
    out = md.to_html('![The agent adds a waitlist box](assets/presence.mp4 "Real time.")')
    assert '<figure class="article-figure"><video class="article-loop" autoplay loop muted playsinline' in out
    assert 'aria-label="The agent adds a waitlist box"' in out
    assert '<source src="assets/presence.mp4" type="video/mp4">' in out
    assert "<figcaption>Real time.</figcaption>" in out
    assert "<img" not in out


def test_video_poster_only_when_the_renderer_says_it_exists():
    src = "![loop](a/clip.webm)"
    assert "poster=" not in md.to_html(src)
    out = md.to_html(src, poster_exists=lambda rel: rel == "a/clip.poster.png")
    assert 'poster="a/clip.poster.png"' in out and 'type="video/webm"' in out


def test_toggle_fence_switches_between_labelled_images():
    out = md.to_html(
        "```toggle\nProposed: ![dashed box](a.png)\nAccepted: ![solid box](b.png)\ncaption: Flip it.\n```"
    )
    assert out.startswith('<figure class="article-figure article-toggle">')
    assert out.count('type="radio"') == 2 and out.count(" checked") == 1
    assert ">Proposed</label>" in out and ">Accepted</label>" in out
    assert 'alt="dashed box"' in out and 'alt="solid box"' in out
    assert "<figcaption>Flip it.</figcaption>" in out


def test_malformed_toggle_stays_a_code_block():
    out = md.to_html("```toggle\njust text\n```")
    assert '<pre><code class="language-toggle">' in out


def test_pipe_table_with_right_aligned_numbers():
    out = md.to_html("| Version | Words |\n|---|---:|\n| V1 | 508 |\n| V2 | 256 |")
    assert out.startswith('<div class="article-table" role="region" tabindex="0" aria-label="Table"><table><thead>')
    assert '<th scope="col">Version</th>' in out and out.endswith("</table></div>")
    assert '<th scope="col" class="numeric">Words</th>' in out
    assert '<td class="numeric">508</td>' in out
    assert out.count("<tr>") == 3


def test_escaped_pipe_stays_in_its_cell():
    out = md.to_html("| Command | Does |\n|---|---|\n| `proposals accept\\|reject` | decides |")
    assert "<code>proposals accept|reject</code>" in out
    assert out.count("<td") == 2
