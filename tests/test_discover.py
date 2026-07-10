import pytest

from artoo import discover, manifest


def test_find_artifacts(tmp_path):
    for rel in ("a", "deep/nested/b"):
        d = tmp_path / rel
        d.mkdir(parents=True)
        manifest.new(d.name, d.name).save(d)
    (tmp_path / "node_modules" / "c").mkdir(parents=True)
    manifest.new("c", "c").save(tmp_path / "node_modules" / "c")

    found = discover.find_artifacts(tmp_path)
    names = [p.name for p in found]
    assert names == ["a", "b"]  # node_modules skipped


def test_find_root_artifact(tmp_path):
    manifest.new("root", "root").save(tmp_path)
    assert discover.find_artifacts(tmp_path) == [tmp_path.resolve()]


def test_resolve_walks_up(tmp_path):
    manifest.new("a", "a").save(tmp_path)
    inner = tmp_path / "site" / "deep"
    inner.mkdir(parents=True)
    m = discover.resolve_artifact(inner)
    assert m.slug == "a"


def test_resolve_missing_lists_candidates(tmp_path):
    d = tmp_path / "somewhere" / "art"
    d.mkdir(parents=True)
    manifest.new("art", "art").save(d)
    with pytest.raises(FileNotFoundError) as exc:
        discover.resolve_artifact(tmp_path)
    assert "art" in str(exc.value)
