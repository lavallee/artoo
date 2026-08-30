"""The CSS vocabulary parser and the invented-class check."""

import pytest

from artoo import libraries, markup
from artoo import manifest as manifest_mod

CSS = """
/* a comment with a } brace and .not-a-class inside */
.article { display: grid; }
.article-full, .article-breakout { grid-column: full; }
.article-masthead__name { font-weight: 700; }
.callout--warn .callout-title { color: red; }
.card h3 { margin: 0; }
@media print {
  .no-print { display: none; }
}
"""


def test_base_classes_fold_elements_and_modifiers_onto_their_parent():
    assert markup.base_classes(CSS) == {
        "article",
        "article-full",
        "article-breakout",
        "article-masthead",
        "callout",
        "card",
        "no-print",
    }


def test_declared_classes_keep_every_usable_name():
    declared = markup.declared_classes(CSS)
    # Markup writes all of these; only the folded parent is *public* vocabulary.
    assert {"callout--warn", "callout-title", "article-masthead__name"} <= declared


def test_comments_and_declarations_are_not_mistaken_for_selectors():
    assert "not-a-class" not in markup.declared_classes(CSS)


def test_classes_used_reads_both_quote_styles():
    html = """<div class="a b"><span class='c'></span><p class=d></p></div>"""
    assert markup.classes_used(html) == {"a", "b", "c"}


def test_closest_suggests_a_real_typo_fix():
    known = {"article-full", "article-figure", "article-lede"}
    assert markup.closest("article-ful", known, "article-") == "article-full"


def test_closest_stays_silent_on_an_invention():
    """A shared prefix makes everything look similar; the suffix is the signal.

    Whole-name matching calls `article-wide` a near miss on `article-dek`,
    which sends the reader to a class that has nothing to do with what they
    wanted. No suggestion is the honest answer.
    """
    known = {"article-full", "article-dek", "article-lede", "article-title"}
    assert markup.closest("article-wide", known, "article-") == ""


# -- the artifact-level check ----------------------------------------------


def _use(artifact, *classes):
    index = artifact.site_dir / "index.html"
    markup_line = "".join(f'<div class="{c}"></div>' for c in classes)
    index.write_text(index.read_text().replace("</main>", f"{markup_line}</main>"))
    return manifest_mod.load(artifact.dir)


def test_invented_class_in_a_library_namespace_is_reported(artifact):
    findings = libraries.markup_check(_use(artifact, "article-wide"))
    assert [f.cls for f in findings] == ["article-wide"]
    assert findings[0].library == "artoo-kit"
    assert findings[0].namespace == "article-"


def test_an_authors_own_class_is_never_second_guessed(artifact):
    """The check has to stay quiet outside the namespaces it owns.

    An artifact's own `.chart-bar` is a legitimate authorial choice. Flagging
    it would make the check noise, and a noisy check gets ignored — including
    on the day it is right.
    """
    assert libraries.markup_check(_use(artifact, "chart-bar", "spend-table")) == []


def test_a_typo_carries_the_class_that_was_meant(artifact):
    findings = libraries.markup_check(_use(artifact, "article-ful"))
    assert findings[0].suggestion == "article-full"
    assert "article-full" in findings[0].message()


def test_the_scaffolded_starter_page_uses_only_real_classes(artifact):
    """The page artoo itself writes must pass the check it imposes."""
    assert libraries.markup_check(artifact) == []


@pytest.mark.parametrize("kind", ["report", "presentation"])
def test_every_scaffolded_kind_passes_its_own_check(tmp_path, kind):
    from artoo import scaffold

    m = scaffold.init_artifact(tmp_path / kind, title="T", kind=kind)
    assert libraries.markup_check(m) == []


def test_a_vendored_library_that_is_not_installed_is_skipped(artifact):
    """Without the library's declared namespaces there is no way to tell an
    invention from an authorial class, and guessing would fail a page that
    renders perfectly."""
    m = _use(artifact, "article-wide")
    m.libraries = [{"name": "some-external-kit", "version": "1.0", "sha256": "x"}]
    m.save()
    assert libraries.markup_check(manifest_mod.load(artifact.dir)) == []


# -- artoo's own output has to pass the check artoo imposes ------------------


def test_generated_notebook_report_uses_only_real_classes(tmp_path, flip_stub):
    """A generator that emits classes the kit does not define would fail the
    user's next `artoo build` with a problem they did not create."""
    from click.testing import CliRunner

    from artoo import manifest as manifest_mod
    from artoo.generators.notebook_report import generate
    from conftest import SAMPLE_PROJECTION

    flip_stub.set_export(SAMPLE_PROJECTION)
    nb = tmp_path / "nb"
    nb.mkdir()
    (nb / "index.md").write_text(
        "---\nokf_version: '0.1'\nflip: '0.6'\nslug: demo-nb\nuid: nb-abc123\n"
        "title: Demo notebook\nkind: scout\nstatus: active\ncreated: '2026-07-20'\n"
        "updated: '2026-07-24'\nvisibility: public\n---\n\n# Demo notebook\n",
        encoding="utf-8",
    )
    out = tmp_path / "report"
    result = CliRunner().invoke(generate, ["--notebook", str(nb), "--out", str(out)])
    assert result.exit_code == 0, result.output

    assert libraries.markup_check(manifest_mod.load(out)) == []


def test_the_explainer_templates_use_only_real_classes():
    """Scanned rather than run: a full explainer run needs agent CLIs."""
    from pathlib import Path

    kit = libraries.available()["artoo-kit"]
    declared = markup.declared_classes_in_dir(kit.root)
    offenders = []
    for path in sorted(Path(__file__).resolve().parent.parent.glob("src/artoo/**/*.py")):
        for cls in sorted(markup.classes_used(path.read_text(encoding="utf-8"))):
            namespace = kit.owns(cls)
            if namespace and cls not in declared:
                offenders.append(f"{path.name}: {cls}")
    assert offenders == []
