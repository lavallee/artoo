from pathlib import Path

import pytest

from artoo import manifest as m


def make():
    man = m.new("chart-forms", "Chart forms", kind="reference-guide", description="43 patterns")
    man.build_commands = ["echo hi"]
    man.deploy_target = "github-pages"
    man.deploy_config = {"subpath": "reader", "mode": "docs"}
    man.workers = {"analysis": "codex"}
    man.libraries = [{"name": "artoo-kit", "version": "0.1.0", "sha256": "abc"}]
    man.vendor = [{"name": "mermaid", "url": "https://x/m.js", "sha256": "def", "path": "site/lib/vendor/m.js"}]
    return man


def test_roundtrip():
    man = make()
    text = m.dumps(man)
    back = m.loads(text)
    assert back.slug == "chart-forms"
    assert back.kind == "reference-guide"
    assert back.build_commands == ["echo hi"]
    assert back.deploy_target == "github-pages"
    assert back.deploy_config == {"subpath": "reader", "mode": "docs"}
    assert back.workers == {"analysis": "codex"}
    assert back.libraries[0]["name"] == "artoo-kit"
    assert back.vendor[0]["path"] == "site/lib/vendor/m.js"


def test_dumps_stable():
    assert m.dumps(make()) == m.dumps(make())


def test_scalars_before_tables():
    text = m.dumps(make())
    assert text.index("[artifact]") < text.index("[build]") < text.index("[deploy]")


def test_validation_catches_problems():
    man = make()
    man.slug = "bad slug!"
    man.kind = "nonsense"
    man.status = "wat"
    man.site = "../evil"
    problems = man.validate()
    assert len(problems) == 4


def test_notebook_may_not_overlap_site():
    man = make()
    man.notebook = "site/notes"
    assert any("overlap" in p for p in man.validate())


def test_save_and_load(tmp_path: Path):
    man = make()
    saved = man.save(tmp_path)
    assert saved.name == "artifact.toml"
    loaded = m.load(tmp_path)
    assert loaded.title == "Chart forms"
    assert loaded.dir == tmp_path.resolve()


def test_load_missing(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        m.load(tmp_path)


def test_string_escaping():
    man = m.new("x", 'He said "hi"\nback', kind="note")
    assert m.loads(m.dumps(man)).title == 'He said "hi"\nback'
