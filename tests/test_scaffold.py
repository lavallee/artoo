"""Kind-aware scaffolding: a presentation is a deck, not a styled article."""

import re

from artoo import manifest as manifest_mod
from artoo import scaffold


def _deck(tmp_path, **kw):
    return scaffold.init_artifact(
        tmp_path / "talk", title="Q3 review", kind="presentation",
        description="Where the quarter landed.", **kw
    )


def test_presentation_is_a_valid_kind():
    assert "presentation" in manifest_mod.KINDS
    assert set(manifest_mod.FORMS) == {"article", "explorer", "collection", "deck"}


def test_presentation_scaffolds_a_deck_not_an_article(tmp_path):
    m = _deck(tmp_path)
    index = (m.dir / m.site / "index.html").read_text()
    assert 'class="deck-root"' in index
    assert 'data-deck' in index
    assert index.count("<section class=\"deck-slide\"") >= 3
    # the article skeleton must not leak into a deck
    assert "article-masthead" not in index
    assert "article-lede" not in index


def test_presentation_vendors_the_deck_library_only(tmp_path):
    m = _deck(tmp_path)
    names = [lib["name"] for lib in m.libraries]
    assert names == ["artoo-deck"]
    lib_dir = m.dir / m.site / "lib" / "artoo-deck"
    assert (lib_dir / "deck.css").exists()
    assert (lib_dir / "deck.js").exists()
    assert not (m.dir / m.site / "lib" / "artoo-kit").exists()


def test_report_still_scaffolds_an_article(tmp_path):
    m = scaffold.init_artifact(tmp_path / "r", title="R", kind="report")
    index = (m.dir / m.site / "index.html").read_text()
    assert "article-masthead" in index
    assert "deck-slide" not in index
    assert [lib["name"] for lib in m.libraries] == ["artoo-kit"]
    assert m.form == "article"
    assert m.content_source == "content.md"


def test_form_can_override_kind_and_scaffold_an_explorer(tmp_path):
    m = scaffold.init_artifact(tmp_path / "x", title="Compare", kind="report", form="explorer")
    index = (m.site_dir / "index.html").read_text()
    assert m.effective_form == "explorer"
    assert [lib["name"] for lib in m.libraries] == ["artoo-kit", "artoo-controls"]
    assert "ArtooControls.create" in index
    assert 'href="lib/artoo-kit/article.css"' in index
    assert (m.site_dir / "data" / "items.json").is_file()
    assert (m.site_dir / "data" / "items.js").is_file()


def test_reference_guide_infers_collection_with_navigation(tmp_path):
    m = scaffold.init_artifact(tmp_path / "guide", title="Guide", kind="reference-guide")
    assert m.effective_form == "collection"
    assert m.content_pages == "content"
    assert m.content_order == ["index.md", "evidence.md"]
    assert (m.site_dir / "evidence.html").is_file()
    page = (m.site_dir / "evidence.html").read_text()
    assert 'aria-current="page"' in page
    assert 'rel="prev"' in page
    assert 'class="nav-toggle"' in page
    assert 'class="nav-links"' in page


def test_deck_starter_declares_acts_and_notes(tmp_path):
    """The overview and the notes toggle read structure from the markup, so the
    starter has to demonstrate both or the affordances look broken."""
    index = (_deck(tmp_path).dir / "site" / "index.html").read_text()
    acts = set(re.findall(r'data-act="([^"]+)"', index))
    assert len(acts) >= 2
    assert re.search(r'data-short="[^"]+"', index)
    assert 'class="deck-notes"' in index


def test_deck_starter_wires_every_control_the_library_expects(tmp_path):
    """Each hook deck.js binds must exist in the starter, or a scaffolded deck
    ships with a dead button."""
    index = (_deck(tmp_path).dir / "site" / "index.html").read_text()
    for hook in (
        "data-deck",
        "data-deck-overview",
        "data-deck-progress",
        "data-deck-counter",
        "data-deck-prev",
        "data-deck-next",
        'data-deck-toggle="overview"',
        'data-deck-toggle="notes"',
        'data-deck-toggle="help"',
        "data-deck-help",
    ):
        assert hook in index, f"starter is missing {hook}"


def test_deck_starter_escapes_its_inputs(tmp_path):
    m = scaffold.init_artifact(
        tmp_path / "x", title='Q3 "review" & <you>', kind="presentation",
        description="a & b <c>",
    )
    index = (m.dir / m.site / "index.html").read_text()
    assert "<you>" not in index
    assert "&lt;you&gt;" in index
    assert "&amp;" in index
