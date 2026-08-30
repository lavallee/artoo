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
