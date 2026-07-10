from pathlib import Path

from artoo import firewall


def test_is_publishable():
    assert firewall.is_publishable(Path("index.html"))
    assert firewall.is_publishable(Path("lib/kit/tokens.css"))
    assert firewall.is_publishable(Path(".nojekyll"))
    assert not firewall.is_publishable(Path("_drafts/x.html"))
    assert not firewall.is_publishable(Path("a/_private/x.html"))
    assert not firewall.is_publishable(Path(".somm/calls.db"))
    assert not firewall.is_publishable(Path("notebook.md"))
    assert not firewall.is_publishable(Path("deep/notes.md"))
    assert not firewall.is_publishable(Path("artifact.toml"))


def test_stage_copies_only_publishable(artifact):
    site = artifact.site_dir
    (site / "_working").mkdir()
    (site / "_working" / "secret.html").write_text("x")
    (site / "notes.md").write_text("private")
    (site / "data.json").write_text("{}")

    dest = artifact.dir / "staged"
    staged = firewall.stage(artifact, dest)
    names = {str(p) for p in staged}
    assert "index.html" in names
    assert "data.json" in names
    assert not any("secret" in n or "notes.md" in n for n in names)
    assert (dest / "data.json").exists()
    assert not (dest / "_working").exists()


def test_check_flags_missing_index(artifact):
    (artifact.site_dir / "index.html").unlink()
    assert any("index.html" in p for p in firewall.check(artifact))


def test_check_flags_notebook_inside_site(artifact):
    nb = artifact.site_dir / "nb"
    nb.mkdir()
    artifact.notebook = "site/nb"
    assert any("would ship" in p for p in firewall.check(artifact))


def test_withheld_lists_denied_files(artifact):
    (artifact.site_dir / "notes.md").write_text("x")
    held = firewall.withheld(artifact.site_dir)
    assert Path("notes.md") in held
