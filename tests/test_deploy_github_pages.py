import subprocess

from artoo import firewall, scaffold
from artoo.deploy.base import DeployContext
from artoo.deploy.github_pages import GitHubPagesDeployer, parse_owner_repo


def test_parse_owner_repo():
    assert parse_owner_repo("git@github.com:o/r.git") == ("o", "r")
    assert parse_owner_repo("https://github.com/o/r") == ("o", "r")
    assert parse_owner_repo("https://github.com/o/r.git") == ("o", "r")
    assert parse_owner_repo("https://example.com/o/r") is None


def _artifact_in(git_repo, monkeypatch):
    # No gh on PATH -> detection returns None -> explicit mode required.
    monkeypatch.setattr("artoo.deploy.github_pages.shutil.which", lambda _: None)
    m = scaffold.init_artifact(
        git_repo / "site" / "explainer", slug="fake-explainer",
        title="Fake explained", kind="explainer",
    )
    return m


def _ctx(m, tmp_path, config, dry_run=False):
    staged = tmp_path / "staged"
    firewall.stage(m, staged)
    return DeployContext(manifest=m, staged=staged, config=config, dry_run=dry_run)


def test_requires_mode_without_gh(git_repo, tmp_path, monkeypatch):
    m = _artifact_in(git_repo, monkeypatch)
    result = GitHubPagesDeployer().deploy(_ctx(m, tmp_path, {}))
    assert not result.ok
    assert "mode" in result.message


def test_docs_mode_places_site_and_commits(git_repo, tmp_path, monkeypatch):
    m = _artifact_in(git_repo, monkeypatch)
    config = {"mode": "docs", "subpath": "explainer"}
    result = GitHubPagesDeployer().deploy(_ctx(m, tmp_path, config))
    assert result.ok, result.message
    assert (git_repo / "docs" / "explainer" / "index.html").exists()
    assert (git_repo / "docs" / ".nojekyll").exists()
    log = subprocess.run(
        ["git", "log", "--oneline", "-1"], cwd=git_repo, capture_output=True, text=True
    ).stdout
    assert "artoo deploy: fake-explainer" in log
    # firewall held the manifest back
    assert not (git_repo / "docs" / "explainer" / "artifact.toml").exists()


def test_docs_mode_dry_run(git_repo, tmp_path, monkeypatch):
    m = _artifact_in(git_repo, monkeypatch)
    config = {"mode": "docs", "subpath": "explainer"}
    result = GitHubPagesDeployer().deploy(_ctx(m, tmp_path, config, dry_run=True))
    assert result.ok
    assert not (git_repo / "docs").exists()


def test_refuses_to_replace_whole_docs_tree(git_repo, tmp_path, monkeypatch):
    m = _artifact_in(git_repo, monkeypatch)
    (git_repo / "docs").mkdir()
    (git_repo / "docs" / "index.html").write_text("existing landing page")
    config = {"mode": "docs", "subpath": ""}
    result = GitHubPagesDeployer().deploy(_ctx(m, tmp_path, config))
    assert not result.ok
    assert "refusing" in result.message
    assert (git_repo / "docs" / "index.html").read_text() == "existing landing page"


def test_workflow_mode_requires_publish_dir(git_repo, tmp_path, monkeypatch):
    m = _artifact_in(git_repo, monkeypatch)
    result = GitHubPagesDeployer().deploy(_ctx(m, tmp_path, {"mode": "workflow"}))
    assert not result.ok
    assert "publish_dir" in result.message


def test_branch_mode_creates_branch(git_repo, tmp_path, monkeypatch):
    m = _artifact_in(git_repo, monkeypatch)
    config = {"mode": "branch", "branch": "gh-pages", "subpath": "explainer"}
    result = GitHubPagesDeployer().deploy(_ctx(m, tmp_path, config))
    assert result.ok, result.message
    files = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "gh-pages"],
        cwd=git_repo, capture_output=True, text=True,
    ).stdout
    assert "explainer/index.html" in files
    assert ".nojekyll" in files


def test_own_root_replaces_docs_tree(git_repo, tmp_path, monkeypatch):
    m = _artifact_in(git_repo, monkeypatch)
    (git_repo / "docs").mkdir()
    (git_repo / "docs" / "stale.html").write_text("old")
    config = {"mode": "docs", "subpath": "", "own_root": True}
    result = GitHubPagesDeployer().deploy(_ctx(m, tmp_path, config))
    assert result.ok, result.message
    assert (git_repo / "docs" / "index.html").exists()
    assert not (git_repo / "docs" / "stale.html").exists()
    assert (git_repo / "docs" / ".nojekyll").exists()


def test_in_place_artifact_commits_without_copying(git_repo, tmp_path, monkeypatch):
    """A site living exactly where Pages serves it (docs/<subpath>) is
    committed in place, never rmtree'd."""
    monkeypatch.setattr("artoo.deploy.github_pages.shutil.which", lambda _: None)
    m = scaffold.init_artifact(
        git_repo / "docs" / "reader", slug="chart-forms",
        title="Chart forms", kind="reference-guide",
    )
    # in-place layout: the artifact dir IS the served dir; site = "."
    import shutil as sh

    for child in (m.dir / "site").iterdir():
        sh.move(str(child), m.dir / child.name)
    (m.dir / "site").rmdir()
    m.site = "."
    m.save()

    config = {"mode": "docs", "subpath": "reader"}
    ctx = _ctx(m, tmp_path, config)
    result = GitHubPagesDeployer().deploy(ctx)
    assert result.ok, result.message
    assert (git_repo / "docs" / "reader" / "artifact.toml").exists()  # not destroyed
    assert (git_repo / "docs" / "reader" / "index.html").exists()
    assert any("in place" in a for a in result.actions)
    log = subprocess.run(
        ["git", "log", "--oneline", "-1"], cwd=git_repo, capture_output=True, text=True
    ).stdout
    assert "artoo deploy: chart-forms" in log
