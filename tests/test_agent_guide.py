"""AGENTS.md: the contract that travels with the artifact."""

from click.testing import CliRunner

from artoo import agent_guide, libraries, scaffold
from artoo import manifest as manifest_mod
from artoo.cli import main


def test_init_writes_the_guide(artifact):
    guide = artifact.dir / agent_guide.GUIDE_NAME
    assert guide.is_file()
    text = guide.read_text()
    assert artifact.title in text
    assert "artoo build" in text


def test_the_on_demand_reference_carries_the_vocabulary(artifact):
    text = (artifact.dir / agent_guide.REFERENCE_NAME).read_text()
    kit = libraries.available()["artoo-kit"]
    for cls, role in kit.classes.items():
        assert f"`{cls}`" in text
        assert role in text


def test_the_guide_names_the_namespaces_a_build_will_enforce(artifact):
    guide = (artifact.dir / agent_guide.GUIDE_NAME).read_text()
    text = (artifact.dir / agent_guide.REFERENCE_NAME).read_text()
    assert agent_guide.REFERENCE_NAME in guide
    assert "`article-`" in text
    assert "artoo docs artoo-kit" in text


def test_a_deck_gets_the_deck_vocabulary_and_not_the_kit_one(tmp_path):
    m = scaffold.init_artifact(tmp_path / "talk", title="Talk", kind="presentation")
    text = (m.dir / agent_guide.REFERENCE_NAME).read_text()
    assert "`deck-slide`" in text
    assert "`article-full`" not in text


def test_the_guide_describes_only_what_is_vendored(artifact):
    """An artifact renders from the bytes it carries; a table describing some
    other version would be worse than none."""
    text = (artifact.dir / agent_guide.REFERENCE_NAME).read_text()
    assert "artoo-deck" not in text


def test_regenerating_keeps_everything_outside_the_block(artifact):
    guide = artifact.dir / agent_guide.GUIDE_NAME
    guide.write_text(guide.read_text() + "\nThe reader is a budget officer.\n")

    agent_guide.write(manifest_mod.load(artifact.dir))

    text = guide.read_text()
    assert "The reader is a budget officer." in text
    assert text.count(agent_guide.BEGIN) == 1
    assert text.count(agent_guide.END) == 1


def test_a_hand_written_guide_is_appended_to_never_replaced(tmp_path):
    """Someone else's AGENTS.md is the more specific instruction. It keeps
    its position and its last word; artoo's block goes underneath."""
    path = tmp_path / "art"
    path.mkdir()
    (path / agent_guide.GUIDE_NAME).write_text("# House rules\n\nAlways cite the vintage.\n")
    scaffold.init_artifact(path, title="Report")

    text = (path / agent_guide.GUIDE_NAME).read_text()
    assert text.startswith("# House rules")
    assert "Always cite the vintage." in text
    assert agent_guide.BEGIN in text


def test_lib_update_refreshes_the_guide(artifact):
    guide = artifact.dir / agent_guide.GUIDE_NAME
    guide.write_text("# stale\n")
    result = CliRunner().invoke(
        main, ["lib", "update", "artoo-kit", "--artifact", str(artifact.dir)]
    )
    assert result.exit_code == 0, result.output
    assert "`article-full`" in (artifact.dir / agent_guide.REFERENCE_NAME).read_text()


def test_adding_a_library_adds_its_vocabulary(artifact):
    result = CliRunner().invoke(
        main, ["lib", "add", "artoo-deck", "--artifact", str(artifact.dir)]
    )
    assert result.exit_code == 0, result.output
    text = (artifact.dir / agent_guide.REFERENCE_NAME).read_text()
    assert "`deck-slide`" in text
    assert "`article-full`" in text


def test_the_guide_is_never_published(artifact):
    """It is repo-side instruction, not site content — the firewall covers it
    structurally by living outside site/, and this pins that."""
    from artoo import firewall

    staged = firewall.stage(artifact, artifact.dir / "_staged")
    assert not any(p.name == agent_guide.GUIDE_NAME for p in staged)
    assert not any(p.name == agent_guide.REFERENCE_NAME for p in staged)


def test_automatic_guide_stays_compact(artifact):
    text = (artifact.dir / agent_guide.GUIDE_NAME).read_text()
    assert len(text.split()) < 350
