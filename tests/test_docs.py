"""`artoo docs`, and the guard that keeps the class tables honest."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from artoo import docs, libraries, markup
from artoo.cli import main


@pytest.mark.parametrize("name", sorted(libraries.available()))
def test_documented_classes_match_the_stylesheets_exactly(name):
    """The anti-drift guard, and the reason the generated tables can be trusted.

    A class in the CSS that nobody documented is a class the next author has
    to reverse-engineer — which is the failure this whole surface exists to
    remove. A documented class the CSS no longer defines is worse: it sends
    them to write markup that renders as nothing.
    """
    lib = libraries.available()[name]
    if not lib.classes:
        pytest.skip(f"{name} declares no vocabulary")
    defined = markup.base_classes_in_dir(lib.root, lib.vendored)
    assert defined - set(lib.classes) == set(), "undocumented classes in the stylesheet"
    assert set(lib.classes) - defined == set(), "documented classes the stylesheet dropped"


@pytest.mark.parametrize("name", sorted(libraries.available()))
def test_every_declared_namespace_is_actually_used(name):
    """A namespace nothing lives in would fail builds without teaching anything."""
    lib = libraries.available()[name]
    for namespace in lib.namespaces:
        assert any(cls.startswith(namespace) for cls in lib.classes), namespace


def test_index_lists_guides_and_libraries():
    index = docs.index()
    for name in list(docs.AUTHORED) + list(libraries.available()):
        assert name in index


@pytest.mark.parametrize("topic", [t.name for t in docs.topics()])
def test_every_listed_topic_renders(topic):
    text = docs.render(topic)
    assert text.startswith("# ")
    assert len(text) > 200


def test_library_topic_carries_the_class_table():
    text = docs.render("artoo-kit")
    assert "## Class vocabulary" in text
    assert "`article-full`" in text
    assert "`article-`" in text  # the namespace it owns


def test_unknown_topic_names_the_ones_that_exist():
    with pytest.raises(KeyError) as exc:
        docs.render("layouts")
    assert "quickstart" in str(exc.value)


def test_render_all_covers_every_topic():
    everything = docs.render_all()
    for topic in docs.topics():
        assert topic.name in everything


def test_cli_docs_lists_then_renders():
    runner = CliRunner()
    listed = runner.invoke(main, ["docs"])
    assert listed.exit_code == 0
    assert "quickstart" in listed.output

    one = runner.invoke(main, ["docs", "firewall"])
    assert one.exit_code == 0
    assert "deny-by-default" in one.output

    every = runner.invoke(main, ["docs", "--all"])
    assert every.exit_code == 0
    assert len(every.output) > len(one.output)


def test_cli_docs_unknown_topic_is_a_clean_error():
    result = CliRunner().invoke(main, ["docs", "nope"])
    assert result.exit_code != 0
    assert "artoo-kit" in result.output


def test_the_published_reference_is_in_sync_with_the_package(tmp_path):
    """docs/ is generated, and a stale copy is worse than none — it is what
    anything reading over HTTP gets, long after the CLI moved on."""
    repo_docs = Path(__file__).resolve().parent.parent / "docs"
    if not (repo_docs / "llms.txt").is_file():
        pytest.skip("not running in the repo")

    docs.write_site(tmp_path)
    stale = [
        str(fresh.relative_to(tmp_path))
        for fresh in tmp_path.rglob("*")
        if fresh.is_file()
        and (
            not (repo_docs / fresh.relative_to(tmp_path)).is_file()
            or (repo_docs / fresh.relative_to(tmp_path)).read_text() != fresh.read_text()
        )
    ]
    assert not stale, (
        f"docs/ is stale: {', '.join(stale)}. "
        "Run `uv run python scripts/sync-docs-site.py`."
    )
