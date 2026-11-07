"""Markdown blocks: parsing, validation with file:line, rendering, and vocabulary."""

from __future__ import annotations

import json

import pytest

from artoo import blocks, build, content, libraries, manifest
from artoo.generators.notebook_report import markdown


def _ctx(**kw) -> blocks.Context:
    return blocks.Context(registry=blocks.registry(), **kw)


def _render(md: str, **kw) -> tuple[str, list[str]]:
    ctx = _ctx(**kw)
    return markdown.to_html(md, blocks=ctx), ctx.diagnostics


def test_callout_with_positional_variant_title_and_id():
    out, problems = _render('::: callout warn #caveat title="Read *this*"\nBody **text**.\n:::')
    assert problems == []
    assert out.startswith('<aside class="callout callout--warn" id="caveat" data-block="callout"')
    assert 'data-src="content.md:1"' in out
    assert '<strong class="callout-title">Read <em>this</em></strong>' in out
    assert "<p>Body <strong>text</strong>.</p>" in out


def test_unknown_block_names_the_line_and_suggests():
    _, problems = _render("Intro.\n\n::: calout\nx\n:::")
    assert problems == [
        'content.md:3: unknown block "calout" (did you mean "callout"?) — '
        "`artoo docs blocks` lists the blocks this artifact can use"
    ]


def test_unknown_attribute_and_bad_choice_and_missing_required():
    _, problems = _render('::: callout tone=warn\nx\n:::\n\n::: callout loud\nx\n:::\n\n'
                          "::: pullnumber\nlabel\n:::")
    assert "content.md:1: `callout` block has no attribute 'tone'" in problems[0]
    assert "content.md:5: `callout` block: variant 'loud' is not one of" in problems[1]
    assert "content.md:9: `pullnumber` block needs value=" in problems[2]


def test_unclosed_and_stray_fences_are_errors():
    _, problems = _render("::: callout\nnever closed")
    assert problems == ["content.md:1: `callout` block is never closed; end it with a line of :::"]
    _, problems = _render("Text.\n\n:::\n")
    assert problems[0].startswith("content.md:3: ::: closes a block that was never opened")


def test_nesting_by_colon_count_and_inner_line_numbers():
    md = ":::: wide\n::: callout\nok\n:::\n\n::: nope\n:::\n::::"
    out, problems = _render(md)
    assert '<div class="article-breakout" data-block="wide"' in out
    assert '<aside class="callout" data-block="callout" data-src="content.md:2"' in out
    assert problems == [
        'content.md:6: unknown block "nope" — `artoo docs blocks` lists the blocks this '
        "artifact can use"
    ]


def test_line_errors_inside_line_bodies_point_at_the_line():
    _, problems = _render("::: stats\n1 | one\nno pipe here\n:::")
    assert problems == ["content.md:3: `stats` block: line 'no pipe here' needs `value | label`"]


def test_html_island_is_verbatim_and_marked():
    out, problems = _render('::: html #fig\n<figure class="article-figure"><b>x</b></figure>\n:::')
    assert problems == []
    assert out == ('<figure class="article-figure" id="fig" data-block="html" '
                   'data-src="content.md:1"><b>x</b></figure>')


def test_without_a_context_directives_stay_text():
    assert markdown.to_html("::: callout\nx\n:::") == "<p>::: callout x :::</p>"


def test_figure_unwraps_an_image_figure_and_adds_caption_and_source():
    out, _ = _render('::: figure caption="Cap" source="Ledger"\n![Alt](a.png)\n:::')
    assert out.count("<figure") == 1
    assert "<figcaption>Cap Source: Ledger</figcaption>" in out


def test_cards_headings_stay_out_of_the_toc():
    body, toc = content._body_and_toc(
        "# T\n\n## Real\n\n::: cards\n[A](a.html) — one\n:::\n", _ctx()
    )
    assert [label for _, label, _ in toc] == ["Real"]
    assert '<a class="nav-card" href="a.html"><h3 data-toc="skip">A</h3><p>one</p></a>' in body


def _artifact(tmp_path, md: str, rows=None):
    m = manifest.new("demo", "Demo")
    m.content_source = "content.md"
    m.save(tmp_path)
    libraries.add(m, "artoo-kit")
    (tmp_path / "content.md").write_text(md, encoding="utf-8")
    if rows is not None:
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "d.json").write_text(json.dumps(rows))
        m.data_packs = [{"source": "data/d.json", "path": "data/d.json", "global": "D"}]
        m.save()
    return manifest.load(tmp_path)


def test_grid_binds_a_pack_vendors_the_library_and_loads_assets(tmp_path):
    m = _artifact(
        tmp_path,
        "# Demo\n\n::: grid data=D index=id search\nname | Name | name\nv | Value | number bar\n:::\n",
        rows=[{"id": 1, "name": "a", "v": 2}],
    )
    result = build.build(m)
    assert result.ok, result.problems
    page = (tmp_path / "site" / "index.html").read_text()
    assert '<link rel="stylesheet" href="lib/artoo-grid/grid.css">' in page
    assert page.index('src="lib/artoo-grid/grid.js"') < page.index('src="data/d.js"')
    assert '{"field": "name", "title": "Name", "format": "name", "minWidth": 96}' in page
    assert (tmp_path / "site" / "lib" / "artoo-grid" / "grid.js").is_file()
    assert any(e["name"] == "artoo-grid" for e in manifest.load(tmp_path).libraries)


def test_grid_rejects_fields_the_data_does_not_have(tmp_path):
    m = _artifact(tmp_path, "# Demo\n\n::: grid data=D\nnmae | Name | name\n:::\n",
                  rows=[{"name": "a"}])
    result = build.build(m)
    assert not result.ok
    assert result.problems == [
        "content.md:4: `grid` block: column field 'nmae' is not in the data (it has name)"
    ]


def test_grid_names_declared_packs_when_data_is_wrong(tmp_path):
    m = _artifact(tmp_path, "# Demo\n\n::: grid data=X\na | A\n:::\n", rows=[{"a": 1}])
    problems = build.build(m).problems
    assert "data='X' names no [[data]] pack (declared globals: D)" in problems[0]


def test_front_matter_keeps_line_numbers_true(tmp_path):
    m = _artifact(tmp_path, "---\nkicker: K\n---\n# Demo\n\n::: nope\n:::\n")
    assert build.build(m).problems[0].startswith("content.md:6: unknown block")


def test_collection_pages_report_their_own_file(tmp_path):
    m = manifest.new("demo", "Demo", kind="reference-guide")
    m.content_pages = "pages"
    m.save(tmp_path)
    libraries.add(m, "artoo-kit")
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "index.md").write_text("# Home\n")
    (tmp_path / "pages" / "two.md").write_text("# Two\n\n::: nope\n:::\n")
    assert build.build(manifest.load(tmp_path)).problems == [
        'pages/two.md:3: unknown block "nope" — `artoo docs blocks` lists the blocks this '
        "artifact can use"
    ]


@pytest.mark.parametrize("name", sorted(blocks.registry()))
def test_every_example_renders_cleanly_with_only_vendored_vocabulary(tmp_path, name):
    block = blocks.registry()[name]
    rows = [{"id": 1, "name": "a", "county": "c", "hhi": 1, "prof": 0.5}]
    m = _artifact(tmp_path, f"# Demo\n\n{block.example}\n", rows=rows)
    m.data_packs[0]["global"] = "DISTRICTS"
    m.save()
    m = manifest.load(tmp_path)
    rendered = content.render(m)
    assert rendered.problems == [], rendered.problems
    assert libraries.markup_check(m) == []
    page = (tmp_path / "site" / "index.html").read_text()
    assert f'data-block="{name}"' in page


def test_every_block_is_documented_with_summary_and_example():
    for block in blocks.registry().values():
        assert block.summary and block.example.startswith(f"::: {block.name}")
        assert block.body in {"markdown", "lines", "raw", "none"}


def test_grid_infers_formats_booleans_height_and_layout_from_the_pack(tmp_path):
    rows = [{"name": "Long district name", "n": 12411, "share": 8.25, "ok": True},
            {"name": "B", "n": 9, "share": 1.5, "ok": None}]
    m = _artifact(tmp_path, "# Demo\n\n::: grid data=D\nname | Name\nn | N\nshare | Share\nok | OK\n:::\n",
                  rows=rows)
    assert build.build(m).ok
    page = (tmp_path / "site" / "index.html").read_text()
    assert '{"field": "n", "title": "N", "format": "number", "decimals": 0}' in page
    assert '{"field": "share", "title": "Share", "format": "number", "decimals": 2}' in page
    assert '{"field": "ok", "title": "OK", "format": "chip"}' in page
    assert 'var b=["ok"]' in page
    assert '"tabulator": {"height": false}' in page and '"layout": "fitColumns"' in page
    assert '{"field": "name", "title": "Name", "minWidth": 168}' in page  # 18 characters


def test_grid_keeps_an_explicit_format(tmp_path):
    m = _artifact(tmp_path, "# Demo\n\n::: grid data=D\nn | N | currency\n:::\n", rows=[{"n": 5}])
    assert build.build(m).ok
    assert '{"field": "n", "title": "N", "format": "currency"}' in (
        tmp_path / "site" / "index.html").read_text()
