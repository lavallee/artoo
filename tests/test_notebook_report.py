"""The notebook-report generator: render a report from a flip notebook."""

from click.testing import CliRunner

from artoo import manifest as manifest_mod
from artoo.generators import available
from artoo.generators.notebook_report import (
    find_draft_dir,
    generate,
    read_draft_markdown,
)

from conftest import SAMPLE_PROJECTION


def _make_notebook(tmp_path, *, updated="2026-07-24", visibility="public"):
    """A minimal flip notebook root whose vintage matches SAMPLE_PROJECTION."""
    nb = tmp_path / "demo-nb"
    nb.mkdir()
    (nb / "index.md").write_text(
        f"---\nuid: nb-abc123\nslug: demo-nb\ntitle: Demo notebook\n"
        f"updated: '{updated}'\nvisibility: {visibility}\n---\n\n# Demo notebook\n",
        encoding="utf-8",
    )
    return nb


def _add_draft(nb, body, *, version="v0", current=True):
    drafts = nb / "drafts"
    vdir = drafts / version
    vdir.mkdir(parents=True)
    (vdir / "index.md").write_text(body, encoding="utf-8")
    (vdir / "changelog.md").write_text("changed nothing", encoding="utf-8")
    if current:
        (drafts / "current").symlink_to(vdir.name)
    return vdir


def _invoke(nb, out, *extra):
    return CliRunner().invoke(
        generate, ["--notebook", str(nb), "--out", str(out), *extra]
    )


def test_registered():
    assert "notebook-report" in available()


def test_skeleton_when_no_draft(tmp_path, flip_stub):
    flip_stub.set_export(SAMPLE_PROJECTION)
    nb = _make_notebook(tmp_path)
    out = tmp_path / "report"
    result = _invoke(nb, out)
    assert result.exit_code == 0, result.output

    page = (out / "site" / "index.html").read_text()
    # Honest skeleton, clearly marked, projected from the notebook.
    assert "Skeleton — no draft" in page
    assert "Claims by status" in page
    assert "Sources by grade" in page
    assert "[C1]" in page  # cited by stable id for the kit's claim anchors
    assert "verified" in page and "asserted" in page
    # Provenance wiring is present.
    assert "data-artoo-provenance" in page
    assert "data-claim-anchors" in page
    assert 'src="data/provenance.js"' in page
    assert (out / "site" / "data" / "provenance.json").is_file()
    # The loud regeneration contract in the colophon.
    assert "This page is a render" in page
    assert "notebook-report generator" in page


def test_draft_rendered_when_present(tmp_path, flip_stub):
    flip_stub.set_export(SAMPLE_PROJECTION)
    nb = _make_notebook(tmp_path)
    _add_draft(nb, "# Findings\n\nThe system is fast. See [C1] for the claim.\n\n- one\n- two")
    out = tmp_path / "report"
    result = _invoke(nb, out)
    assert result.exit_code == 0, result.output

    page = (out / "site" / "index.html").read_text()
    assert "<h1>Findings</h1>" in page
    assert "<li>one</li>" in page
    assert "[C1]" in page  # left intact for the anchor hydrator
    assert "Skeleton — no draft" not in page
    assert "Body rendered from the notebook&#x27;s current draft." in page or \
           "Body rendered from the notebook's current draft." in page


def test_prefers_current_symlink_over_older_version(tmp_path):
    nb = _make_notebook(tmp_path)
    _add_draft(nb, "# v0 body", version="v0", current=False)
    v1 = _add_draft(nb, "# v1 body", version="v1", current=True)
    # current -> v1
    assert find_draft_dir(nb).resolve() == v1.resolve()


def test_newest_version_when_no_current(tmp_path):
    nb = _make_notebook(tmp_path)
    _add_draft(nb, "# v0", version="v0", current=False)
    _add_draft(nb, "# v2", version="v2", current=False)
    _add_draft(nb, "# v1", version="v1", current=False)
    assert find_draft_dir(nb).name == "v2"


def test_read_draft_concatenates_when_no_primary(tmp_path):
    nb = _make_notebook(tmp_path)
    drafts = nb / "drafts" / "v0"
    drafts.mkdir(parents=True)
    (drafts / "01-intro.md").write_text("# Intro", encoding="utf-8")
    (drafts / "02-body.md").write_text("# Body", encoding="utf-8")
    (drafts / "changelog.md").write_text("# Changelog — excluded", encoding="utf-8")
    md = read_draft_markdown(drafts)
    assert "# Intro" in md and "# Body" in md
    assert "excluded" not in md


def test_regen_idempotent_and_restamps_vintage(tmp_path, flip_stub):
    flip_stub.set_export(SAMPLE_PROJECTION)
    nb = _make_notebook(tmp_path, updated="2026-07-24")
    _add_draft(nb, "# Report\n\nBody.")
    out = tmp_path / "report"

    first = _invoke(nb, out)
    assert first.exit_code == 0
    m1 = manifest_mod.load(out)
    assert m1.rendered_updated == "2026-07-24"
    first_html = (out / "site" / "index.html").read_text()

    second = _invoke(nb, out)
    assert second.exit_code == 0
    assert "updating report" in second.output
    # Same notebook in → same page out (deterministic; the date line is the
    # only day-varying bit and both runs share today's date).
    assert (out / "site" / "index.html").read_text() == first_html

    # Notebook moves on: the render vintage restamps on regen.
    (nb / "index.md").write_text(
        (nb / "index.md").read_text().replace("2026-07-24", "2026-08-01"),
        encoding="utf-8",
    )
    bumped = dict(SAMPLE_PROJECTION)
    bumped["notebook"] = dict(SAMPLE_PROJECTION["notebook"], updated="2026-08-01")
    flip_stub.set_export(bumped)
    third = _invoke(nb, out)
    assert third.exit_code == 0
    m3 = manifest_mod.load(out)
    assert m3.rendered_updated == "2026-08-01"
    assert "updated 2026-08-01" in (out / "site" / "index.html").read_text()


def test_draft_renders_without_flip(tmp_path, monkeypatch):
    # No flip: a draft still renders, just without the provenance panel.
    monkeypatch.delenv("ARTOO_FLIP_BIN", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    (tmp_path / "empty").mkdir()
    nb = _make_notebook(tmp_path)
    _add_draft(nb, "# Offline\n\nRendered without flip.")
    out = tmp_path / "report"
    result = _invoke(nb, out)
    assert result.exit_code == 0, result.output
    page = (out / "site" / "index.html").read_text()
    assert "<h1>Offline</h1>" in page
    assert "data-artoo-provenance" not in page  # no panel without a projection
    # Colophon still names the vintage read from the live frontmatter.
    assert "nb-abc123" in page


def test_no_draft_and_no_flip_refuses(tmp_path, monkeypatch):
    monkeypatch.delenv("ARTOO_FLIP_BIN", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    (tmp_path / "empty").mkdir()
    nb = _make_notebook(tmp_path)
    out = tmp_path / "report"
    result = _invoke(nb, out)
    assert result.exit_code != 0
    assert "nothing" in result.output.lower()


def test_include_private_reaches_flip(tmp_path, flip_stub, monkeypatch):
    seen = {}
    from artoo import provenance as provenance_mod

    real = provenance_mod.flip_read.export_json

    def spy(nb_dir, *, include_private=False):
        seen["include_private"] = include_private
        return real(nb_dir, include_private=include_private)

    monkeypatch.setattr(provenance_mod.flip_read, "export_json", spy)
    flip_stub.set_export(SAMPLE_PROJECTION)
    nb = _make_notebook(tmp_path, visibility="internal")
    _add_draft(nb, "# Private\n\nBody.")
    out = tmp_path / "report"
    result = _invoke(nb, out, "--include-private")
    assert result.exit_code == 0, result.output
    assert seen["include_private"] is True
    m = manifest_mod.load(out)
    assert m.research_include_private is True


def test_notebook_binding_may_be_external(tmp_path, flip_stub):
    # The report artifact is a sibling of the notebook; the binding escapes the
    # artifact dir with ``..`` and the manifest accepts it (read direction).
    flip_stub.set_export(SAMPLE_PROJECTION)
    nb = _make_notebook(tmp_path)
    _add_draft(nb, "# R\n\nBody.")
    out = tmp_path / "report"
    _invoke(nb, out)
    m = manifest_mod.load(out)
    assert m.notebook.startswith("..")
    assert m.validate() == []


def test_rejects_non_notebook_dir(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    out = tmp_path / "report"
    result = _invoke(plain, out)
    assert result.exit_code != 0
    assert "not a flip notebook" in result.output
