"""Explainer page assembly: favicon, notebook-aware colophon, provenance panel."""

from artoo.generators.explainer import templates

PAGE = {"slug": "index", "title": "Overview", "purpose": "What this is."}
BASE_META = {
    "date": "2026-07-24",
    "artoo_version": "0.1.0",
    "repo_name": "demo",
    "commit": "abc1234",
    "workers": "analysis: codex, synthesis: claude",
}


def test_shell_always_ships_favicon():
    html_text = templates.render_page(
        page=PAGE, pages=[PAGE], site_title="Demo", body="<p>x</p>", meta=BASE_META
    )
    assert 'rel="icon"' in html_text and "favicon.svg" in html_text


def test_panel_and_colophon_when_provenance():
    meta = {**BASE_META, "notebook_uid": "nb-abc123", "notebook_updated": "2026-07-24"}
    html_text = templates.render_page(
        page=PAGE, pages=[PAGE], site_title="Demo",
        body="<p>Backed by [C1] and [C2].</p>", meta=meta, provenance=True,
    )
    assert "data-artoo-provenance" in html_text
    assert "data/provenance.js" in html_text
    assert "lib/artoo-kit/provenance.js" in html_text
    assert "data-claim-anchors" in html_text
    assert "Rendered from" in html_text and "nb-abc123" in html_text


def test_no_panel_without_provenance():
    html_text = templates.render_page(
        page=PAGE, pages=[PAGE], site_title="Demo", body="<p>x</p>", meta=BASE_META
    )
    assert "data-artoo-provenance" not in html_text
    assert "provenance.js" not in html_text
    assert "Rendered from" not in html_text
