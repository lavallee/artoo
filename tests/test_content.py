from artoo import content


def test_article_render_has_toc_and_stable_section_ids(artifact):
    source = artifact.dir / artifact.content_source
    source.write_text("# Decision\n\n## Evidence here\n\nSupported text.\n")
    result = content.render(artifact)
    assert result.status == "written"
    page = (artifact.site_dir / "index.html").read_text()
    assert '<a href="#evidence-here">Evidence here</a>' in page
    assert '<h2 id="evidence-here">Evidence here</h2>' in page
    assert page.count("<h1") == 1


def test_no_content_declaration_preserves_raw_html(artifact):
    artifact.content_source = ""
    index = artifact.site_dir / "index.html"
    index.write_text("custom")
    assert content.render(artifact).status == "skipped"
    assert index.read_text() == "custom"


def test_collection_page_manifest_refuses_unlisted_pages(tmp_path):
    from artoo import scaffold

    artifact = scaffold.init_artifact(
        tmp_path / "guide", title="Guide", kind="reference-guide"
    )
    (artifact.dir / "content" / "extra.md").write_text("# Extra")
    result = content.render(artifact)
    assert result.status == "error"
    assert "not in content.order: extra.md" in result.problems[0]


def test_collection_prunes_only_previously_generated_pages(tmp_path):
    from artoo import scaffold

    artifact = scaffold.init_artifact(
        tmp_path / "guide", title="Guide", kind="reference-guide"
    )
    custom = artifact.site_dir / "custom.html"
    custom.write_text("kept")
    (artifact.dir / "content" / "evidence.md").rename(
        artifact.dir / "content" / "limits.md"
    )
    artifact.content_order = ["index.md", "limits.md"]
    result = content.render(artifact)
    assert result.status == "written"
    assert not (artifact.site_dir / "evidence.html").exists()
    assert (artifact.site_dir / "limits.html").exists()
    assert custom.read_text() == "kept"


def test_mermaid_fence_renders_as_a_diagram_and_vendors_the_renderer(artifact):
    from artoo import libraries, manifest

    source = artifact.dir / artifact.content_source
    source.write_text("# Flow\n\n```mermaid\nflowchart LR\n  A --> B\n```\n")
    assert content.render(artifact).status == "written"
    page = (artifact.site_dir / "index.html").read_text()
    assert '<pre class="mermaid">flowchart LR\n  A --&gt; B</pre>' in page
    assert 'href="lib/artoo-diagrams/diagrams.css"' in page
    assert page.index('src="lib/artoo-diagrams/pele.global.js"') < page.index(
        'src="lib/artoo-diagrams/diagrams.js"'
    )
    reloaded = manifest.load(artifact.dir)
    assert any(lib["name"] == "artoo-diagrams" for lib in reloaded.libraries)
    assert (libraries.vendored_dir(reloaded, "artoo-diagrams") / "pele.global.js").is_file()


def test_content_never_re_vendors_a_pinned_diagram_library(artifact):
    from artoo import manifest

    artifact.libraries.append({"name": "artoo-diagrams", "version": "0.0.1", "sha256": "x"})
    artifact.save()
    source = artifact.dir / artifact.content_source
    source.write_text("# Flow\n\n```mermaid\nflowchart LR\n  A --> B\n```\n")
    content.render(artifact)
    pinned = [
        lib for lib in manifest.load(artifact.dir).libraries if lib["name"] == "artoo-diagrams"
    ]
    assert pinned == [{"name": "artoo-diagrams", "version": "0.0.1", "sha256": "x"}]


def test_pages_without_diagrams_load_no_renderer(artifact):
    source = artifact.dir / artifact.content_source
    source.write_text("# Plain\n\n```python\nprint('mermaid')\n```\n")
    content.render(artifact)
    page = (artifact.site_dir / "index.html").read_text()
    assert "artoo-diagrams" not in page
    assert 'class="language-python"' in page


def test_markdown_figure_renders_and_verify_checks_the_file(artifact):
    from artoo import verify

    source = artifact.dir / artifact.content_source
    source.write_text('# Shot\n\n![The canvas beside the chat](assets/shot.png "It works")\n')
    assert content.render(artifact).status == "written"
    page = (artifact.site_dir / "index.html").read_text()
    assert '<figure class="article-figure"><img src="assets/shot.png" alt="The canvas beside the chat"' in page
    assert "<figcaption>It works</figcaption>" in page
    missing = verify.static(artifact)
    assert any("assets/shot.png" in problem for problem in missing.problems)
    (artifact.site_dir / "assets").mkdir()
    (artifact.site_dir / "assets" / "shot.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    assert not [p for p in verify.static(artifact).problems if "shot.png" in p]
