from artoo import firewall
from artoo.deploy.base import DeployContext
from artoo.deploy.command import CommandDeployer


def _ctx(artifact, tmp_path, config, dry_run=False):
    staged = tmp_path / "staged"
    firewall.stage(artifact, staged)
    return DeployContext(manifest=artifact, staged=staged, config=config, dry_run=dry_run)


def test_requires_run(artifact, tmp_path):
    result = CommandDeployer().deploy(_ctx(artifact, tmp_path, {}))
    assert not result.ok
    assert "run" in result.message


def test_runs_with_environment(artifact, tmp_path):
    out = artifact.dir / "publish-log.txt"
    config = {"run": f'echo "$ARTOO_SLUG|$ARTOO_SITE_DIR" > {out}'}
    result = CommandDeployer().deploy(_ctx(artifact, tmp_path, config))
    assert result.ok
    slug, site_dir = out.read_text().strip().split("|")
    assert slug == artifact.slug
    assert site_dir.endswith("staged")


def test_dry_run_executes_nothing(artifact, tmp_path):
    out = artifact.dir / "publish-log.txt"
    config = {"run": f"echo hi > {out}"}
    result = CommandDeployer().deploy(_ctx(artifact, tmp_path, config, dry_run=True))
    assert result.ok
    assert not out.exists()


def test_failure_surfaces_exit_code(artifact, tmp_path):
    result = CommandDeployer().deploy(_ctx(artifact, tmp_path, {"run": "exit 3"}))
    assert not result.ok
    assert "3" in result.message
