"""`artoo skill install`: the contract as an agent skill."""

from click.testing import CliRunner

from artoo import docs, skill
from artoo.cli import main


def test_skill_markdown_advertises_itself_in_frontmatter():
    text = skill.skill_markdown()
    head, body = text.split("---\n", 2)[1:]
    assert "name: artoo" in head
    assert "description:" in head
    assert body.lstrip().startswith("# artoo")


def test_the_description_names_the_words_a_request_actually_uses():
    """The description is the only part read for every task; if it does not
    match how someone asks for an artifact, the skill never fires."""
    description = skill.DESCRIPTION.lower()
    for trigger in ("report", "explainer", "deck", "artifact.toml"):
        assert trigger in description


def test_install_writes_the_skill_and_its_references(tmp_path):
    result = skill.install(tmp_path / "artoo")
    assert (result.root / "SKILL.md").is_file()
    for topic in docs.topics():
        assert (result.root / "references" / f"{topic.name}.md").is_file()
    assert len(result.files) == len(docs.topics()) + 1


def test_references_carry_the_class_vocabulary_offline(tmp_path):
    """An agent that cannot run artoo still needs the vocabulary."""
    result = skill.install(tmp_path / "artoo")
    kit = (result.root / "references" / "artoo-kit.md").read_text()
    assert "`article-full`" in kit
    assert "## Class vocabulary" in kit


def test_install_is_idempotent(tmp_path):
    first = skill.install(tmp_path / "artoo")
    before = (first.root / "SKILL.md").read_text()
    second = skill.install(tmp_path / "artoo")
    assert (second.root / "SKILL.md").read_text() == before


def test_cli_install_reports_where_it_landed(tmp_path):
    target = tmp_path / "skills" / "artoo"
    result = CliRunner().invoke(main, ["skill", "install", "--dir", str(target)])
    assert result.exit_code == 0, result.output
    assert str(target) in result.output
    assert (target / "SKILL.md").is_file()


def test_cli_show_pipes_the_skill(tmp_path):
    result = CliRunner().invoke(main, ["skill", "show"])
    assert result.exit_code == 0
    assert result.output.startswith("---\n")


def test_default_locations_follow_the_conventional_layout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert skill.default_dir().parts[-3:] == (".claude", "skills", "artoo")
    assert skill.default_dir(user=True).is_relative_to(skill.Path.home())
