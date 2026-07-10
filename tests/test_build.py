from artoo import build


def test_build_runs_commands(artifact):
    artifact.build_commands = ["echo hello > built.txt"]
    result = build.build(artifact)
    assert result.ok
    assert (artifact.dir / "built.txt").exists()


def test_build_reports_failure(artifact):
    artifact.build_commands = ["false"]
    result = build.build(artifact)
    assert not result.ok
    assert "failed" in result.problems[0]


def test_build_dry_run_runs_nothing(artifact):
    artifact.build_commands = ["echo hi > should-not-exist.txt"]
    result = build.build(artifact, dry_run=True)
    assert result.ok
    assert not (artifact.dir / "should-not-exist.txt").exists()


def test_build_fails_without_index(artifact):
    (artifact.site_dir / "index.html").unlink()
    result = build.build(artifact)
    assert not result.ok
